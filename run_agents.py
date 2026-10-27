#!/usr/bin/env python3
"""Phase 3 entry point: multi-agent narration of the live match.

    python run_agents.py --match M12 --mode batch            # whole match, writes data/narration/
    python run_agents.py --match M12 --mode live --speed 60  # subscribes to replay.py (stdin), narrates as it plays
    python run_agents.py --match M12 --mode offline --speed 60  # replays cached outputs, no Azure needed
    python run_agents.py --match M12 --mode rebuild           # re-writes overlays / fallbacks / reports from results_debug.jsonl, no LLM
    python run_agents.py --match M12 --mode batch --cache-only  # whole pipeline from the response cache only, no LLM, no cost

Batch and live need `az login` and the .env file (PROJECT_ENDPOINT, MODEL_DEPLOYMENT_NAME).
--cache-only and rebuild need neither; a cache miss in --cache-only counts as a failed call (fact card stays).
"""

import argparse
import asyncio
import collections
import json
import os
import sys
import time

from agents.facts import FactStore
from agents.selection import load_config, select_items
from agents import verify as V
from agents import outputs as O
from agents import factcards as FC


def build_items(store, cfg, modes=None, focus=None, limit=None):
    items = []
    for mode in modes or ("fan", "analyst", "focus"):
        if mode == "focus":
            for pid in (focus or cfg["focus_players"]):
                for it in select_items(store, cfg, "focus", pid):
                    items.append(dict(it, mode="focus", focus_player=pid))
        else:
            for it in select_items(store, cfg, mode):
                items.append(dict(it, mode=mode, focus_player=None))
    for i, it in enumerate(items):
        it["item_id"] = f"{store.match_id}-IT-{i:03d}"
    items.sort(key=lambda it: it["t_ms"])
    return items[:limit] if limit else items


async def checked_document(rt, agent, prompt, lang, meta, fallback=None, facts=None, store=None, max_repairs=1, previous=None):
    """Long-form outputs also pass the deterministic document checks (neutral venue, clock); one repair round.

    If the agent call still fails after its retries, the deterministic `fallback` text is used instead
    (failure isolation: one failing document does not stop the run). With `previous` (a committed text checked
    again after new checks) the agent only repairs that text: the repair round starts from it."""
    from agents.llm import AgentCallFailed
    try:
        check = lambda t: V.check_document(t, lang, store) + (V.check_recap(t, lang, facts, store) if facts is not None else
                                                        (V.check_scouting(t, lang, store) if store is not None else []))
        if previous is not None:
            text = previous
        else:
            text, _ = await rt.ask(agent, prompt, want_json=False, trace=rt.trace_id(), meta=meta)
        problems = check(text)
        rounds = 0
        while problems and rounds < max_repairs:
            rounds += 1
            fix = (prompt + f"\nYOUR PREVIOUS TEXT:\n{text}\nREPAIR REQUEST: your previous text had these problems: {json.dumps(problems, ensure_ascii=False)}. "
                   "Rewrite the whole text without them and keep everything else that was correct.")
            try:
                text2, _ = await rt.ask(agent, fix, want_json=False, trace=rt.trace_id(), meta=dict(meta, repair=True, round=rounds))
                text = text2
            except AgentCallFailed as f:
                rt.log.append(dict(agent="document_check", kind=meta.get("kind"), lang=lang, status="recovered",
                                   note=f"repair call failed ({f.kind}); kept the previous text"))
                break
            problems = check(text)
        if problems:
            rt.log.append(dict(agent="document_check", kind=meta.get("kind"), lang=lang, remaining_problems=problems))
            if facts is not None and fallback:
                rt.log.append(dict(agent="document_check", kind=meta.get("kind"), lang=lang, status="fallback",
                                   note="recap facts still wrong after the repair rounds; deterministic recap written"))
                return fallback.replace("{reason}", {"hu": "Az összefoglaló két javítás után sem ment át az ellenőrzésen", "en": "The recap did not pass the checks after two repair rounds"}[lang])
        elif rounds:
            rt.log.append(dict(agent="document_check", kind=meta.get("kind"), lang=lang, remaining_problems=[]))
        return text
    except AgentCallFailed as f:
        rt.log.append(dict(agent="document_check", kind=meta.get("kind"), lang=lang, status="fallback", failure=f.as_dict(),
                           note="agent unavailable; deterministic fallback text written"))
        return (fallback or "").replace("{reason}", {"hu": "Az összefoglaló ügynök nem volt elérhető", "en": "The recap agent was unavailable"}[lang])


def fallback_recap(store, lang):
    """Deterministic recap used only when the Recap agent is unavailable: final score and goals, nothing else."""
    h, a = store.final_score()
    head = {"hu": "# Összefoglaló (tartalék, ügynök nélkül)", "en": "# Recap (fallback, no agent)"}[lang]
    note = {"hu": "{reason}; ez a szöveg csak a tényeket mutatja.", "en": "{reason}; this text shows the facts only."}[lang]
    L = [head, "", f"**{store.team_name(store.home)} {h}–{a} {store.team_name(store.away)}**", "", note, ""]
    for m in store.moments:
        if m["type"] == "goal":
            L.append(f"* {m['clock']} – {m['fact']['scorer']} ({m['fact']['score']})")
    return "\n".join(L)


def committed_doc(path):
    """A committed recap / scouting note without its sources line (the text the agent wrote, as shown)."""
    return open(path, encoding="utf-8").read().split("\n\n<sub>Source")[0].strip()


def build_recap_facts(store, results):
    """The facts the Recap writer gets (also used by the checks of apply_targeted_edits.py and the tests; no LLM)."""
    from agents.facts import slim_state
    h, a = store.final_score()
    goals = [dict(clock=m["clock"], half=m["half"], team=store.team_name(m["team_id"]), fact=m["fact"],
                  shot_speed_kmh=((store.moment_ball_metrics(m) or {}).get("shot") or {}).get("shot_speed_kmh"),
                  body_part=((store.moment_ball_metrics(m) or {}).get("shot") or {}).get("body_part"),
                  shot_distance_m=((store.moment_ball_metrics(m) or {}).get("shot") or {}).get("distance_m")) for m in store.moments if m["type"] == "goal"]
    top = sorted(store.moments, key=lambda m: -m["importance"])[:8]
    team_kpis = [r for r in store.team_kpis if r["match_id"] == store.match_id]
    cards = [dict(clock=r.get("clock"), type=r["card"].get("type"), headline_facts=r["card"].get("headline_facts"), why=r["card"].get("why_it_matters"))
             for r in results if r["verdict"] not in ("reject", "fallback") and r["variant"]["persona"] == "analyst" and r["variant"]["lang"] == "en" and not r["variant"]["focus_player"]][:30]
    tc = store.tournament
    facts = dict(match=f"{store.team_name(store.home)} {h}-{a} {store.team_name(store.away)}", teams=[store.team_name(store.home), store.team_name(store.away)],
                 match_team_ids=[store.home, store.away],
                 venue=tc["venue"], neutral_venue=True, clock_rule="first-half stoppage time is 45+N', second-half 90+N'",
                 tournament=dict(stake_before_the_match=tc["stake"], standings_before=[dict(rank=r["rank"], team=r["team"], points=r["points"], gd=r["gd"]) for r in tc["standings_before"]],
                                 final_standings=[dict(rank=r["rank"], team=r["team"], points=r["points"], won=r["won"], drawn=r["drawn"], lost=r["lost"], gf=r["gf"], ga=r["ga"]) for r in tc["standings_after"]],
                                 tournament_winner=tc["tournament_winner"]),
                 goals=goals, top_moments=[dict(clock=m["clock"], half=m["half"], type=m["type"], team=store.team_name(m["team_id"]) if m.get("team_id") else None, fact=m["fact"], importance=m["importance"]) for m in top],
                 team_kpis=team_kpis, verified_cards=cards, final_state=slim_state(store.states[-1]))
    # positions of every player the recap is likely to name (scorers, assists, top moments): facts, not guesses
    named = {v for g in goals for k, v in g["fact"].items() if k in ("scorer", "assist_by") and v} | \
            {m["fact"].get(k) for m in top for k in ("scorer", "player", "shooter") if m["fact"].get(k)}
    by_name = {p["name"]: pid for pid, p in store.players.items()}
    facts["player_positions"] = {n: V.position_label(by_name[n], store, "en") for n in sorted(named) if n in by_name}
    facts["shots_note"] = "team_kpis give shots, not shots on target; never write a number of shots on target"
    return facts


async def recap_and_scouting(rt, store, results, cfg, out_dir, docs=("recap", "scouting"), repair=None):
    """repair: (persona, lang) pairs whose committed recap is checked again and only repaired (the other documents stay)."""
    h, a = store.final_score()
    facts = build_recap_facts(store, results)
    goals = facts["goals"]
    for persona in (cfg["personas"] if "recap" in docs or repair else []):
        for lang in cfg["languages"]:
            if repair is not None and (persona, lang) not in repair:
                continue
            prompt = (f"Write the post-match recap. persona={persona}, language={lang} ({'Hungarian' if lang == 'hu' else 'English'}). "
                      f"Sections: headline (must say who won the tournament and why this match decided it), how it unfolded, 'Top 3 moments' (with the clock strings), "
                      f"numbers that mattered ({'few' if persona == 'fan' else 'with metric names'}), final standings. Neutral venue: no home/away wording "
                      f"(never 'home side', 'visitors', 'hazai', 'vendég', 'vendégcsapat').\nFACTS:\n{json.dumps(facts, ensure_ascii=False)}")
            path = os.path.join(out_dir, f"{store.match_id}_recap_{persona}_{lang}.md")
            text = await checked_document(rt, "recap", prompt, lang, meta=dict(kind="recap", persona=persona, lang=lang), fallback=fallback_recap(store, lang),
                                          facts=facts, store=store, max_repairs=2, previous=committed_doc(path) if repair is not None else None)
            with open(os.path.join(out_dir, f"{store.match_id}_recap_{persona}_{lang}.md"), "w", encoding="utf-8") as f:
                f.write(O.shown(text.strip(), lang) + "\n\n<sub>Sources: moments feed, state by minute, team_match_kpis.csv, verified insight cards.</sub>\n")
    # scouting notes: the 4 hidden talents + top 3 per position from the FINAL profiles (no ground truth)
    talents = []
    for pid in cfg["focus_players"]:
        p = store.profiles_final.get(pid)
        if p:
            talents.append(dict(player_id=pid, name=store.player_name(pid), age=store.players[pid]["age"], team=store.team_name(p["team_id"]), profile=p))
    by_pos = collections.defaultdict(list)
    for p in store.profiles_final.values():
        if p["ranking_status"] == "ranked":
            by_pos[p["position_group"]].append(p)
    top3 = {pos: [dict(player_id=q["player_id"], name=store.player_name(q["player_id"]), age=store.players[q["player_id"]]["age"], position_score=q["position_score"],
                       minutes=q["minutes"], reliability=q["reliability"], strengths=q["strengths"]) for q in sorted(lst, key=lambda q: -float(q["position_score"]))[:3]]
            for pos, lst in sorted(by_pos.items())}
    low_data = [dict(player_id=p["player_id"], name=store.player_name(p["player_id"]), minutes=p["minutes"]) for p in store.profiles_final.values() if p["ranking_status"] != "ranked"]
    sfacts = dict(young_players_in_focus=talents, top3_per_position=top3, low_data_players=low_data,
                  rules=dict(low_data_minutes=cfg["low_data_minutes_tournament"], note="Rankings include only players with >= 180 minutes; others are 'low data'."))
    for lang in (cfg["languages"] if "scouting" in docs and repair is None else []):
        prompt = (f"Write the scouting notes in {'Hungarian' if lang == 'hu' else 'English'} as Markdown: (1) one cautious paragraph per young player in focus "
                  f"(position, minutes, reliability label, position score, strengths/weaknesses with category scores, 'low data' if under {cfg['low_data_minutes_tournament']} minutes, "
                  f"no hype, no future predictions), (2) top 3 per position as a table, (3) a short note on the low-data players. Use only the given numbers.\nFACTS:\n{json.dumps(sfacts, ensure_ascii=False)}")
        fb = {"hu": "# Scouting jegyzet (tartalék)\n\nA scouting ügynök nem volt elérhető. A számok a Scouting fülön, a profilokból látszanak.",
              "en": "# Scouting notes (fallback)\n\nThe scouting agent was unavailable. The numbers are shown in the Scouting tab, from the profiles."}[lang]
        text = await checked_document(rt, "recap", prompt, lang, meta=dict(kind="scouting", lang=lang), fallback=fb, store=store)
        with open(os.path.join(out_dir, f"scouting_notes_{lang}.md"), "w", encoding="utf-8") as f:
            f.write(O.shown(text.strip(), lang) + "\n\n<sub>Source: data/kpi/final/player_profiles.csv (events only, no ground truth).</sub>\n")


async def run_batch(args):
    from dotenv import load_dotenv
    load_dotenv()
    from agents.cache import ResponseCache
    from agents.llm import LLMRuntime
    from agents.pipeline import run_items
    cfg = load_config()
    store = FactStore(args.match)
    rules = V.load_rules()
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    # --cache-only replays the committed run: the timed call log and the run metadata of the real run are kept
    log_name = "agent_log_replay.jsonl" if args.cache_only else "agent_log.jsonl"
    rt = LLMRuntime(store, cfg, ResponseCache(args.cache), os.path.join(out_dir, log_name), concurrency=cfg["llm_concurrency"], cache_only=args.cache_only,
                    budget_usd=args.budget_usd, spent_usd=args.spent_usd)
    items = build_items(store, cfg, modes=args.modes.split(",") if args.modes else None, limit=args.limit)
    print(f"{len(items)} narration items: {dict(collections.Counter(it['mode'] for it in items))}")
    t0 = time.time()
    done = [0]

    def progress(it, recs):
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(items):
            print(f"  {done[0]}/{len(items)} items, {rt.usage['calls']} LLM calls, {rt.usage['cached']} cached, {time.time() - t0:.0f}s", flush=True)
    results, verify = await run_items(rt, store, rules, items, cfg, progress)
    # deterministic layer: the fact card every item would show first in live mode (0 LLM calls)
    for rec in results:
        it = next(i for i in items if i["item_id"] == rec["item_id"])
        rec["fact_card"] = FC.checked_fact_card(store, it, rec["variant"]["lang"], cfg)
    if not args.limit:
        await recap_and_scouting(rt, store, results, cfg, out_dir)
    elapsed = time.time() - t0
    prev_path = os.path.join(out_dir, "results_debug.jsonl")
    if args.cache_only and os.path.exists(prev_path):
        # keep the trace ids and latencies of the timed run, so that agent_log.jsonl still matches the traces
        prev = {(r["item_id"], r["variant"]["persona"], r["variant"]["lang"], r["variant"]["club_view"], str(r["variant"]["focus_player"])): r
                for r in (json.loads(l) for l in open(prev_path, encoding="utf-8") if l.strip())}
        for r in results:
            old = prev.get((r["item_id"], r["variant"]["persona"], r["variant"]["lang"], r["variant"]["club_view"], str(r["variant"]["focus_player"])))
            if old:
                r["trace"], r["item_latency_s"] = old["trace"], old["item_latency_s"]
    rt.flush_log()
    rows = O.write_overlays(results, os.path.join(out_dir, f"{args.match}_overlays.jsonl"), cfg)
    fallbacks = O.write_fallbacks(results, os.path.join(out_dir, f"{args.match}_fallbacks.jsonl"), cfg)
    O.write_commentary(results, out_dir, store, cfg)
    summary = O.write_verifier_report(results, os.path.join(out_dir, "verifier_report.md"), cfg)
    with open(prev_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lat = [r["item_latency_s"] for r in results]
    meta = dict(match=args.match, items=len(items), text_variants=len(results), overlays=len(rows), verifier=summary, llm_calls=rt.usage["calls"],
                cached_calls=rt.usage["cached"], tokens=dict(input=rt.usage["input"], output=rt.usage["output"], total=rt.usage["total"]),
                cost_usd=round(rt.cost_usd(), 4),
                tokens_full_run=dict(input=rt.usage["input"] + rt.usage.get("cached_input", 0), output=rt.usage["output"] + rt.usage.get("cached_output", 0),
                                     total=rt.usage["total"] + rt.usage.get("cached_total", 0), note="this run's calls plus the cached responses it reused = cost of one full uncached run"),
                cost_usd_full_run=round(rt.cost_usd(include_cached=True), 4), retries_429=rt.usage.get("retries", 0),
                budget_usd=args.budget_usd, failed_calls=rt.usage.get("failed", 0),
                model=rt.model, elapsed_s=round(elapsed, 1), mean_item_latency_s=round(sum(lat) / len(lat), 2) if lat else None,
                overlays_by_mode=dict(collections.Counter(r["mode"] for r in rows)), overlays_by_persona=dict(collections.Counter(r["persona"] for r in rows)),
                items_by_mode=dict(collections.Counter(it["mode"] for it in items)))
    meta["failure_recovery"] = recovery_summary(results, fallbacks, rt)
    meta_path = os.path.join(out_dir, "run_metadata.json")
    if args.cache_only:
        timed = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                timed = json.load(f)
        replay = dict(llm_calls=rt.usage["calls"], cache_hits=rt.usage["cached"], failed_calls=rt.usage["failed"], elapsed_s=meta["elapsed_s"])
        meta = dict(timed, overlays=meta["overlays"], verifier=meta["verifier"], failure_recovery=meta["failure_recovery"], replayed_from_cache=replay) if timed else dict(meta, replayed_from_cache=replay)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(meta, indent=1))


def recovery_summary(results, fallbacks, rt=None):
    s = dict(status=dict(collections.Counter(r.get("status", "verified") for r in results)),
             recovery=dict(collections.Counter(f"{x.get('agent')}:{x.get('kind')}" for r in results for x in r.get("recovery", []))),
             fact_card_fallbacks_shown=sum(1 for x in fallbacks if x["text"]), fallbacks_without_fact_card=sum(1 for x in fallbacks if not x["text"]))
    if rt is not None:
        s.update(failed_calls=rt.usage.get("failed", 0), retries=rt.usage.get("retries", 0), timeout_s=rt.timeout_s)
    return s


async def run_rerun(args):
    """Re-run only the given items (and the recaps) with the current code; every other result stays as it is.

    Unchanged prompts are answered from the cache; the new calls are logged with their own trace ids and appended
    to agent_log.jsonl; run_metadata.json keeps the full-run figures and records the re-run separately."""
    from dotenv import load_dotenv
    load_dotenv(".env")
    from agents.cache import ResponseCache
    from agents.llm import LLMRuntime
    from agents.pipeline import run_items
    cfg = load_config()
    store = FactStore(args.match)
    rules = V.load_rules()
    out_dir = args.out
    rpath, lpath, mpath = (os.path.join(out_dir, n) for n in ("results_debug.jsonl", "agent_log.jsonl", "run_metadata.json"))
    from agents.pipeline import variant_key
    old = [json.loads(l) for l in open(rpath, encoding="utf-8") if l.strip()]
    ids = set(args.items.split(",")) if args.items else set()
    only = collections.defaultdict(set)     # --variants ITEM|lang|club_view|focus: only these variants of the item are run again
    for x in (args.variants.split(",") if args.variants else []):
        iid, key = x.split("|", 1)
        only[iid].add(key)
    items = [it for it in build_items(store, cfg) if it["item_id"] in ids] + \
            [dict(it, only_variants=sorted(only[it["item_id"]])) for it in build_items(store, cfg) if it["item_id"] in only and it["item_id"] not in ids]
    tag = args.rerun_tag
    rt = LLMRuntime(store, cfg, ResponseCache(args.cache), os.path.join(out_dir, f"agent_log_{tag}.jsonl"), concurrency=cfg["llm_concurrency"],
                    budget_usd=args.budget_usd, spent_usd=args.spent_usd)
    rt.trace_prefix = f"tr-{tag}"
    t0 = time.time()
    new, _ = await run_items(rt, store, rules, items, cfg) if items else ([], None)
    for rec in new:
        it = next(i for i in items if i["item_id"] == rec["item_id"])
        rec["fact_card"] = FC.checked_fact_card(store, it, rec["variant"]["lang"], cfg)
        rec["rerun"] = tag
    redone = {(r["item_id"], variant_key(r["variant"])) for r in new}
    results = [r for r in old if r["item_id"] not in ids and (r["item_id"], variant_key(r["variant"])) not in redone] + new
    results.sort(key=lambda r: (r["t_ms"], r["mode"], r["variant"]["persona"], r["variant"]["lang"], r["variant"]["club_view"], str(r["variant"]["focus_player"])))
    if args.recaps or args.scouting:
        await recap_and_scouting(rt, store, results, cfg, out_dir, docs=(("recap",) if args.recaps else ()) + (("scouting",) if args.scouting else ()))
    if args.repair_recaps:
        await recap_and_scouting(rt, store, results, cfg, out_dir, docs=(), repair={tuple(x.split(":")) for x in args.repair_recaps.split(",")})
    elapsed = time.time() - t0
    with open(lpath, "a", encoding="utf-8") as f:
        for e in rt.log:
            f.write(json.dumps(dict(e, rerun=tag), ensure_ascii=False) + "\n")
    rows = O.write_overlays(results, os.path.join(out_dir, f"{args.match}_overlays.jsonl"), cfg)
    fallbacks = O.write_fallbacks(results, os.path.join(out_dir, f"{args.match}_fallbacks.jsonl"), cfg)
    O.write_commentary(results, out_dir, store, cfg)
    summary = O.write_verifier_report(results, os.path.join(out_dir, "verifier_report.md"), cfg)
    with open(rpath, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(mpath) as f:
        meta = json.load(f)
    run = dict(tag=tag, reason=args.rerun_reason, items=sorted(ids), variants=sorted(args.variants.split(",")) if args.variants else [],
               recaps=bool(args.recaps), scouting=bool(args.scouting), repaired_recaps=args.repair_recaps.split(",") if args.repair_recaps else [],
               text_variants=len(new), llm_calls=rt.usage["calls"],
               cached_calls=rt.usage["cached"], failed_calls=rt.usage.get("failed", 0), retries=rt.usage.get("retries", 0),
               tokens=dict(input=rt.usage["input"], output=rt.usage["output"], total=rt.usage["total"]), cost_usd=round(rt.cost_usd(), 4), elapsed_s=round(elapsed, 1))
    meta["reruns"] = [x for x in meta.get("reruns", []) if x.get("tag") != tag] + [run]
    meta.update(overlays=len(rows), verifier=summary, failure_recovery=dict(recovery_summary(results, fallbacks, None), timeout_s=cfg.get("llm_timeout_s", 60)),
                overlays_by_mode=dict(collections.Counter(r["mode"] for r in rows)), overlays_by_persona=dict(collections.Counter(r["persona"] for r in rows)),
                cost_usd_with_reruns=round(meta["cost_usd"] + sum(x["cost_usd"] for x in meta["reruns"]), 4))
    with open(mpath, "w") as f:
        json.dump(meta, f, indent=2)
    print(json.dumps(run, indent=1))


def run_rebuild(args):
    """Re-write overlays, fact-card fallbacks, commentary and the verifier report from results_debug.jsonl (no LLM).

    Records written before the failure-recovery fields existed get `status` / `recovery` from their own
    verdict and the agent log (agents/outputs.py annotate_status). Fact cards are deterministic, so every
    record's fact card is rebuilt from the current templates. The timed run metadata is kept."""
    cfg = load_config()
    store = FactStore(args.match)
    out_dir = args.out
    rpath = os.path.join(out_dir, "results_debug.jsonl")
    if not os.path.exists(rpath):
        raise SystemExit(f"{rpath} is missing; run the batch mode first.")
    results = [json.loads(l) for l in open(rpath, encoding="utf-8") if l.strip()]
    log = [json.loads(l) for l in open(os.path.join(out_dir, "agent_log.jsonl"), encoding="utf-8") if l.strip()]
    by_trace = collections.defaultdict(list)
    for e in log:
        if e.get("trace_id"):
            by_trace[e["trace_id"]].append(e)
    items = {it["item_id"]: it for it in build_items(store, cfg)}
    for r in results:
        O.annotate_status(r, by_trace.get(r["trace"], []))
        if r["item_id"] in items:
            r["fact_card"] = FC.checked_fact_card(store, items[r["item_id"]], r["variant"]["lang"], cfg)
    rows = O.write_overlays(results, os.path.join(out_dir, f"{args.match}_overlays.jsonl"), cfg)
    fallbacks = O.write_fallbacks(results, os.path.join(out_dir, f"{args.match}_fallbacks.jsonl"), cfg)
    O.write_commentary(results, out_dir, store, cfg)
    summary = O.write_verifier_report(results, os.path.join(out_dir, "verifier_report.md"), cfg)
    with open(rpath, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta_path = os.path.join(out_dir, "run_metadata.json")
    with open(meta_path) as f:
        meta = json.load(f)
    meta.update(overlays=len(rows), verifier=summary, failure_recovery=recovery_summary(results, fallbacks))
    meta["failure_recovery"]["timeout_s"] = cfg.get("llm_timeout_s", 60)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"rebuilt from {rpath}: {len(rows)} verified overlays, {len(fallbacks)} fact-card fallbacks; status {meta['failure_recovery']['status']}")


def run_offline(args):
    """Replay the cached overlays on the match clock, no Azure needed."""
    path = os.path.join(args.out, f"{args.match}_overlays.jsonl")
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    fb_path = os.path.join(args.out, f"{args.match}_fallbacks.jsonl")
    if os.path.exists(fb_path):   # where no verified text exists, the fact card stays (failure recovery)
        with open(fb_path, encoding="utf-8") as f:
            rows += [dict(r, layout="fact card") for r in (json.loads(l) for l in f if l.strip()) if r.get("text")]
    rows = [r for r in rows if (not args.persona or r["persona"] == args.persona) and (not args.lang or r["lang"] == args.lang)
            and r["club_view"] == (args.club or "neutral") and (r["focus_player"] == args.focus)]
    rows.sort(key=lambda r: r["t_ms"])
    print(f"offline replay: {len(rows)} overlays (persona={args.persona or 'all'}, lang={args.lang or 'all'}, club={args.club or 'neutral'}, focus={args.focus}) at x{args.speed}")
    start = time.monotonic()
    for r in rows:
        delay = start + r["t_ms"] / 1000.0 / args.speed - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        print(f"[{r['minute']:02d}'] {r['persona']}/{r['lang']} {r['layout']:<13} {r['text']}" + ("   (fallback: no verified agent text)" if r.get("fallback") else ""))
        sys.stdout.flush()


async def run_live(args):
    """Subscribe to replay.py (events on stdin), run the live engine and narrate new moments as they appear."""
    from dotenv import load_dotenv
    load_dotenv()
    from agents.cache import ResponseCache
    from agents.llm import LLMRuntime
    from agents.pipeline import run_items
    from kpi import aggregate as A
    import live_engine
    cfg = load_config()
    rules = V.load_rules()
    d = A.load_dataset("data/synthetic")
    match = next(m for m in d["matches"] if m["match_id"] == args.match)
    pool = A.ReferencePool(A.read_csv("data/reference/reference_player_kpis.csv"))
    with open("config/position_weights.json") as f:
        weights = json.load(f)
    state = live_engine.make_state(d, match, pool, weights, "data/kpi")
    store = FactStore(args.match)           # fact index for profiles / teams; moments and states are replaced live
    store.moments, store.states, store.by_id = [], [], {}
    out_dir = args.out
    rt = LLMRuntime(store, cfg, ResponseCache(args.cache), os.path.join(out_dir, "agent_log_live.jsonl"), concurrency=cfg["llm_concurrency"], cache_only=args.cache_only)
    tasks, results, n_item = [], [], [0]
    latencies = []
    narrated = set()   # (mode, kind, t_ms, focus) already sent to the agents
    n_snap = [0]

    fact_latencies, upgrade_latencies = [], []

    async def narrate_item(it, received_at):
        # step 1: deterministic fact card, immediately (no LLM)
        cards = {}
        for lang in cfg["languages"]:
            c = FC.checked_fact_card(store, it, lang, cfg)
            if c and not c["problems"]:
                cards[lang] = c
        fact_latency = round(time.monotonic() - received_at, 3)
        if cards:
            fact_latencies.append(fact_latency)
            for lang, c in cards.items():
                if lang == "hu" and it["mode"] != "focus":
                    print(f"[{it.get('clock', it['minute'])}] FACT CARD/{lang} {c['text']}  (+{fact_latency}s)", flush=True)
        # step 2: the agents; the verified text replaces the card with the same item id
        res, _ = await run_items(rt, store, rules, [it], cfg)
        for r in res:
            r["live_latency_s"] = round(time.monotonic() - received_at, 2)
            r["fact_card"] = cards.get(r["variant"]["lang"])
            r["fact_card_latency_s"] = fact_latency
            r["upgraded_from_fact_card"] = bool(r["fact_card"]) and O.is_shown(r)
            if r["upgraded_from_fact_card"]:
                upgrade_latencies.append(r["live_latency_s"])
            latencies.append(r["live_latency_s"])
            if not O.is_shown(r) and r["variant"]["club_view"] == "neutral" and not r["variant"]["focus_player"] and r["variant"]["lang"] == "hu":
                print(f"[{r.get('clock')}] {r['variant']['persona']}/{r['variant']['lang']} FALLBACK – fact card stays ({'; '.join(map(str, r['reasons']))[:80]})", flush=True)
            if O.is_shown(r) and r["variant"]["club_view"] == "neutral" and not r["variant"]["focus_player"]:
                print(f"[{r.get('clock')}] {r['variant']['persona']}/{r['variant']['lang']} {'UPGRADED ' if r['upgraded_from_fact_card'] else ''}{r['final']['overlay']}  (+{r['live_latency_s']}s)", flush=True)
        results.extend(res)

    def dispatch(received):
        """Apply exactly the batch selection rules to the facts known so far and narrate what is new."""
        for mode in ("fan", "analyst"):
            for it in select_items(store, cfg, mode):
                key = (mode, it["kind"], it["t_ms"], None)
                if key not in narrated:
                    narrated.add(key)
                    n_item[0] += 1
                    tasks.append(asyncio.create_task(narrate_item(dict(it, mode=mode, focus_player=None, item_id=f"{args.match}-LIVE-{n_item[0]:03d}"), received)))
        for pid in cfg["focus_players"]:
            for it in select_items(store, cfg, "focus", pid):
                key = ("focus", it["kind"], it["t_ms"], pid)
                if key not in narrated:
                    narrated.add(key)
                    n_item[0] += 1
                    tasks.append(asyncio.create_task(narrate_item(dict(it, mode="focus", focus_player=pid, item_id=f"{args.match}-LIVE-{n_item[0]:03d}"), received)))

    loop = asyncio.get_running_loop()
    while True:
        # read stdin in a worker thread so that the narration tasks keep running between events (real tempo)
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        if not line.strip():
            continue
        e = json.loads(line)
        received = time.monotonic()
        new_moments = live_engine.update(state, e)
        # mirror the live engine's facts into the store
        # mirror the live engine's facts into the store through a JSON round trip, so that the prompts are
        # byte-identical to the batch prompts built from the files (cache hits, no second LLM cost)
        if len(state.snapshots) > len(store.states):
            store.states = [json.loads(json.dumps(s)) for s in state.snapshots]
        for m in new_moments:
            m = json.loads(json.dumps(m))
            m["moment_id"] = f"{args.match}-MOM-{len(store.moments):03d}"
            store.moments.append(m)
            store.by_id[m["moment_id"]] = m
            store.annotate_moment(m)
        if new_moments or len(state.snapshots) != n_snap[0]:
            n_snap[0] = len(state.snapshots)
            dispatch(received)
        await asyncio.sleep(0)
    await asyncio.gather(*tasks)
    rt.flush_log()
    O.write_overlays(results, os.path.join(out_dir, f"{args.match}_overlays_live.jsonl"), cfg)
    import statistics as _st
    summary = dict(text_variants=len(results), mean_latency_s=round(sum(latencies) / len(latencies), 2) if latencies else None,
                   fact_card_latency_s=dict(mean=round(_st.fmean(fact_latencies), 3), max=round(max(fact_latencies), 3), n=len(fact_latencies)) if fact_latencies else None,
                   upgrade_latency_s=dict(mean=round(_st.fmean(upgrade_latencies), 2), median=round(_st.median(upgrade_latencies), 2), max=round(max(upgrade_latencies), 2), n=len(upgrade_latencies)) if upgrade_latencies else None,
                   llm_calls=rt.usage["calls"], cached=rt.usage["cached"], tokens=rt.usage["total"], retries_429=rt.usage.get("retries", 0),
                   status=dict(collections.Counter(r.get("status", "verified") for r in results)), failed_calls=rt.usage.get("failed", 0))
    with open(os.path.join(out_dir, "live_run_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"live run: {json.dumps(summary)}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="M12")
    ap.add_argument("--mode", choices=["batch", "live", "offline", "rebuild", "rerun"], default="batch")
    ap.add_argument("--items", default=None, help="rerun: comma list of item ids to run again with the current code")
    ap.add_argument("--variants", default=None, help="rerun: comma list of single variants ITEM|lang|club_view|focus_player to run again (the item's other variants stay)")
    ap.add_argument("--recaps", action="store_true", help="rerun: also write the four recaps again (with the recap checks)")
    ap.add_argument("--scouting", action="store_true", help="rerun: also write the two scouting notes again (with the scouting checks)")
    ap.add_argument("--repair-recaps", default=None, help="rerun: persona:lang list (e.g. fan:en,analyst:hu) whose committed recap is checked again and only repaired")
    ap.add_argument("--rerun-tag", default="r1", help="rerun: tag for the trace ids and the metadata entry")
    ap.add_argument("--rerun-reason", default="", help="rerun: why these items are run again")
    ap.add_argument("--cache-only", action="store_true", help="batch/live: answer every agent call from the response cache only (no LLM, no cost)")
    ap.add_argument("--budget-usd", type=float, default=None, help="spending limit: no new LLM call once spent + this run would exceed it")
    ap.add_argument("--spent-usd", type=float, default=0.0, help="already spent before this run (counts against --budget-usd)")
    ap.add_argument("--out", default="data/narration")
    ap.add_argument("--cache", default="data/narration/cache", help="shared LLM response cache (same for batch and live, so live hits the batch cache)")
    ap.add_argument("--speed", type=float, default=60.0)
    ap.add_argument("--limit", type=int, default=None, help="batch: only the first N items (testing)")
    ap.add_argument("--modes", default=None, help="batch: comma list of fan,analyst,focus")
    ap.add_argument("--persona", default=None)
    ap.add_argument("--lang", default=None)
    ap.add_argument("--club", default=None)
    ap.add_argument("--focus", default=None)
    args = ap.parse_args()
    if args.mode == "batch":
        asyncio.run(run_batch(args))
    elif args.mode == "live":
        asyncio.run(run_live(args))
    elif args.mode == "rebuild":
        run_rebuild(args)
    elif args.mode == "rerun":
        asyncio.run(run_rerun(args))
    else:
        run_offline(args)


if __name__ == "__main__":
    main()
