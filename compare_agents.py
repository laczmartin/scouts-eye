#!/usr/bin/env python3
"""Single agent vs the five-agent pipeline on the same match segment.

    python compare_agents.py --run --budget-usd 1.2 --spent-usd 0.75   # one LLM call per text variant (paid), then scores
    python compare_agents.py                                          # scores the saved outputs again, no LLM

Arm 1, single agent: one gpt-4.1-mini agent on Microsoft Foundry (Agent Framework,
the same read-only function tools) gets exactly the facts the Match Analyst gets
(plus the Scout's facts for player-focus items) and writes the final text for one
variant directly: no insight card, no pre-check, no Verifier, no repair.
Arm 2, five agents, first drafts: the Narrator's first text in the committed run,
before the deterministic pre-check.
Arm 3, five agents, final: what the committed run shows on screen (verified text,
or the fact card where the text was rejected).

All three arms are scored by the same deterministic checks (agents/verify.py)
against the facts that arm was given. The five-agent pipeline uses these checks
internally, so its final output passes them by construction; the first drafts
show what the agents produce before the checks. Segment: the first half of M12
(all narration items of period 1, every persona / language / club view / focus).
"""

import argparse
import asyncio
import collections
import json
import os
import statistics
import time

from agents import verify as V
from agents.facts import FactStore
from agents.selection import load_config

OUT = "data/comparison"
SOLO = (
    "You are a single all-round football commentary agent. From the facts of one match moment (or of the match state) "
    "you write the on-screen texts for one persona and one language as JSON with keys: overlay (max 90 characters, no newline), "
    "commentary (max 2 sentences), detail (optional, max 3 sentences). Persona 'fan': plain language, emotion, at most ONE number "
    "per line, no metrics jargon. Persona 'analyst': metrics, percentiles, PPDA, field tilt, reliability labels. Write natively in "
    "the target language (hu = Hungarian, en = English), do not translate word for word. When a club view is given, frame the line "
    "from that club's perspective. When a focus player is given, make the player the subject and state the reliability label and "
    "the minutes; below 180 tournament minutes or 20 live minutes say 'low data' and avoid any ranking claim. Use only numbers "
    "present in the facts. JSON only.")


def key_of(item_id, v):
    return f"{item_id}|{v['persona']}|{v['lang']}|{v['club_view']}|{v['focus_player']}"


def load_committed():
    results = [json.loads(l) for l in open("data/narration/results_debug.jsonl", encoding="utf-8") if l.strip()]
    log = [json.loads(l) for l in open("data/narration/agent_log.jsonl", encoding="utf-8") if l.strip()]
    meta = json.load(open("data/narration/run_metadata.json"))
    return results, log, meta


def segment(results):
    return [r for r in results if r["period"] == 1]


def solo_payload(store, cfg, r, item):
    from agents.pipeline import build_facts, scout_facts
    facts, _ = build_facts(store, item)
    v = r["variant"]
    payload = dict(persona=v["persona"], language=v["lang"],
                   club_view=(store.team_name(v["club_view"]) if v["club_view"] != "neutral" else "neutral"),
                   focus_player=(store.player_name(v["focus_player"]) if v["focus_player"] else None), facts=facts)
    if v["focus_player"]:
        payload["focus_player_facts"] = scout_facts(store, item, cfg)
    return payload


def solo_prompt(store, cfg, r, item):
    return f"Write the texts.\nINPUT:\n{json.dumps(solo_payload(store, cfg, r, item), ensure_ascii=False)}"


async def run_single(store, cfg, seg, items_by_id, budget, spent, backend=None, rerun_tag=None):
    """One call per text variant. With rerun_tag, only the variants whose prompt is not in the cache (their facts changed)
    are called again; the other saved outputs, the timed call log and the one-pass run figures are kept, and the re-run
    is recorded in single_agent_run.json under "reruns"."""
    from dotenv import load_dotenv
    load_dotenv()
    from agent_framework import Agent
    from agents import llm
    from agents.cache import ResponseCache
    os.makedirs(OUT, exist_ok=True)
    rt = llm.LLMRuntime(store, cfg, ResponseCache(os.path.join(OUT, "cache")), os.path.join(OUT, "agent_log_single.jsonl"),
                        concurrency=cfg["llm_concurrency"], budget_usd=budget, spent_usd=spent, backend=backend)
    if rt.backend is None:
        rt.agents["solo"] = Agent(rt.client, name="solo", instructions=llm.SAFETY + SOLO, tools=store.make_tools())
    out = []
    t0 = time.time()
    todo = seg
    if rerun_tag:
        todo = [r for r in seg if rt.cache.get(rt.cache.key("solo", rt.model, solo_prompt(store, cfg, r, items_by_id[r["item_id"]]))) is None]
        rt.trace_prefix = f"solo-{rerun_tag}"

    async def one(r):
        item = items_by_id[r["item_id"]]
        payload = solo_payload(store, cfg, r, item)
        prompt = solo_prompt(store, cfg, r, item)
        v = r["variant"]
        t1 = time.time()
        try:
            text, raw = await rt.ask("solo", prompt, trace=rt.trace_id(), meta=dict(item_id=r["item_id"], persona=v["persona"], lang=v["lang"],
                                                                               club_view=v["club_view"], focus_player=v["focus_player"]))
            status = "ok" if text else "invalid_json"
        except llm.AgentCallFailed as f:
            text, status = None, f"failed:{f.kind}"
        out.append(dict(key=key_of(r["item_id"], v), item_id=r["item_id"], variant=v, minute=r["minute"], clock=r.get("clock"),
                        text=text or {}, status=status, latency_s=round(time.time() - t1, 2), input_facts=payload))
    await asyncio.gather(*(one(r) for r in todo))
    wall = time.time() - t0
    run = dict(wall_s=round(wall, 1), calls=rt.usage["calls"], cached=rt.usage["cached"], failed=rt.usage.get("failed", 0),
               tokens=dict(input=rt.usage["input"], output=rt.usage["output"]), cost_usd=round(rt.cost_usd(), 4), model=rt.model,
               budget_usd=budget, spent_before_usd=spent)
    rpath, lpath, mpath = (os.path.join(OUT, n) for n in ("single_agent_results.jsonl", "agent_log_single.jsonl", "single_agent_run.json"))
    if rerun_tag:
        prev = {x["key"]: x for x in (json.loads(l) for l in open(rpath, encoding="utf-8") if l.strip())}
        prev.update({x["key"]: dict(x, rerun=rerun_tag) for x in out})
        out = list(prev.values())
        with open(lpath, "a", encoding="utf-8") as f:
            for e in rt.log:
                f.write(json.dumps(dict(e, rerun=rerun_tag), ensure_ascii=False) + "\n")
        meta = json.load(open(mpath))
        meta["reruns"] = [x for x in meta.get("reruns", []) if x.get("tag") != rerun_tag] + [dict(run, tag=rerun_tag, texts=len(todo),
                          reason="the variants whose facts changed since the last single-agent run (their prompt was not in the cache)")]
        json.dump(meta, open(mpath, "w"), indent=2)
    else:
        rt.flush_log()
        json.dump(run, open(mpath, "w"), indent=2)
    out.sort(key=lambda x: x["key"])
    with open(rpath, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return run


CATS = ("goal", "clock", "venue", "language", "grammar", "player", "wording")


def semantic_categories(problems):
    c = collections.Counter()
    for p in problems:
        if p.startswith(("the goal is", "score ")):
            c["goal"] += 1
        elif "is wrong for this event" in p or p.startswith("minute ") or p.startswith("the event happened in the first half"):
            c["clock"] += 1
        elif p.startswith("neutral venue"):
            c["venue"] += 1
        elif "not in Hungarian" in p or "not in English" in p:
            c["language"] += 1
        elif p.startswith("English grammar"):
            c["grammar"] += 1
    return c


def score_text(store, cfg, rules, item, v, text_obj, facts, fact_card=False):
    text = " ".join(str(text_obj.get(k) or "") for k in ("overlay", "commentary", "detail"))
    if not text.strip():
        return dict(empty=True)
    ok_n, bad_n = V.check_numbers(text, facts, cfg["number_tolerance_relative"], cfg["number_tolerance_absolute"])
    ok_names, bad_names = V.check_names(text, facts, store)
    claims = V.check_claims(text, v["lang"], item, store, rules, player_id=v["focus_player"])
    # exactly the pre-check's text checks (agents/verify.py semantic_checks); a fact card is the match-state template, not a text about the player
    st = facts.get("state") or store.state_at_ms(item["t_ms"])
    core, player, wording = V.semantic_checks(text, text_obj, v["lang"], item, store, cfg, st, facts.get("moment"), None if fact_card else v["focus_player"])
    cats = semantic_categories(core)
    ranking = [p for p in player if "no ranking or elite claim" in p]
    player = [p for p in player if p not in ranking]
    return dict(empty=False, bad_numbers=bad_n, bad_names=bad_names, unsupported=[c["matched"] for c in claims if not c["supported"]] + ranking,
                semantic=core + player + wording, cats=dict(cats, player=len(player), wording=len(wording)), too_long=len(text_obj.get("overlay") or "") > cfg["overlay_max_chars"])


def summarize(scores):
    n = len(scores)
    ne = [s for s in scores if not s["empty"]]
    row = dict(texts=n, empty=n - len(ne),
               numbers=sum(1 for s in ne if s["bad_numbers"]), names=sum(1 for s in ne if s["bad_names"]),
               claims=sum(1 for s in ne if s["unsupported"]), too_long=sum(1 for s in ne if s["too_long"]))
    for c in CATS:
        row[c] = sum(1 for s in ne if s["cats"].get(c))
    row["any_error"] = sum(1 for s in ne if s["bad_numbers"] or s["bad_names"] or s["unsupported"] or s["semantic"] or s["too_long"]) + row["empty"]
    return row


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="call the single agent (paid); without it the saved outputs are scored")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--spent-usd", type=float, default=0.0)
    ap.add_argument("--out", default="data/comparison", help="output folder (default data/comparison)")
    ap.add_argument("--dry-run", action="store_true", help="with --run: a fake model answers (tests/test_failure_recovery.py), no Azure, no cost")
    ap.add_argument("--rerun-tag", default=None, help="with --run: only the variants whose facts changed (cache misses) are called again, recorded under this tag")
    args = ap.parse_args()
    OUT = args.out
    cfg = load_config()
    store = FactStore("M12")
    rules = V.load_rules()
    import run_agents
    items_by_id = {it["item_id"]: it for it in run_agents.build_items(store, cfg)}
    results, log, meta = load_committed()
    seg = segment(results)
    if args.run:
        backend = None
        if args.dry_run:
            import sys
            sys.path.insert(0, "tests")
            from test_failure_recovery import FakeBackend

            class SoloFake(FakeBackend):
                async def respond(self, agent, prompt, meta):
                    return await super().respond("narrator", prompt, meta)
            backend = SoloFake(store, list(items_by_id.values()))
        run = asyncio.run(run_single(store, cfg, seg, items_by_id, args.budget_usd, args.spent_usd, backend, args.rerun_tag))
        print("single agent run:", run)
    single = {x["key"]: x for x in (json.loads(l) for l in open(os.path.join(OUT, "single_agent_results.jsonl"), encoding="utf-8") if l.strip())}
    run = json.load(open(os.path.join(OUT, "single_agent_run.json")))
    S1, S2, S3, per_text = [], [], [], []
    for r in seg:
        item, v, k = items_by_id[r["item_id"]], r["variant"], key_of(r["item_id"], r["variant"])
        sx = single.get(k)
        s1 = score_text(store, cfg, rules, item, v, sx["text"] if sx else {}, sx["input_facts"] if sx else {})
        s2 = score_text(store, cfg, rules, item, v, r["attempts"][0]["text"], r["facts"]) if r["attempts"] else dict(empty=True)
        shown = r["final"] if r["final"] else ({"overlay": (r.get("fact_card") or {}).get("text", "")} if r.get("fact_card") else {})
        s3 = score_text(store, cfg, rules, item, v, shown, r["facts"], fact_card=not r["final"])
        S1.append(s1); S2.append(s2); S3.append(s3)
        per_text.append(dict(key=k, clock=r.get("clock"), single=sx["text"] if sx else None, single_score=s1,
                             first_draft=r["attempts"][0]["text"] if r["attempts"] else None, first_draft_score=s2,
                             final=shown, final_score=s3, status=r.get("status")))
    # cost / calls / time of the five agents on the same items (committed fresh run; recap and scouting excluded)
    seg_items = {r["item_id"] for r in seg}
    variants_per_item = collections.Counter(r["item_id"] for r in seg)
    # the five-agent cost and time of ONE pass: the fresh run; items re-run after the checker fixes are reported separately
    ent = [e for e in log if e.get("item_id") in seg_items and e.get("tokens") and not e.get("rerun")]
    rerun_ent = [e for e in log if e.get("item_id") in seg_items and e.get("tokens") and e.get("rerun") and not e.get("cached")]
    price = cfg["price_per_million_tokens_usd"]
    cost = lambda es: sum(e["tokens"]["input"] * price["input"] / 1e6 + e["tokens"]["output"] * price["output"] / 1e6 for e in es)
    # LLM time per text: the variant's own calls plus its share of the item-level calls (Analyst, Scout)
    t_by_key = collections.defaultdict(float)
    for e in ent:
        lat = e.get("call_latency_s") or 0.0
        if e["agent"] in ("analyst", "scout"):
            for r in seg:
                if r["item_id"] == e["item_id"]:
                    t_by_key[key_of(r["item_id"], r["variant"])] += lat / variants_per_item[e["item_id"]]
        else:
            vv = dict(persona=e.get("persona"), lang=e.get("lang"), club_view=e.get("club_view") or "neutral", focus_player=e.get("focus_player"))
            t_by_key[key_of(e["item_id"], vv)] += lat
    single_log = [json.loads(l) for l in open(os.path.join(OUT, "agent_log_single.jsonl"), encoding="utf-8") if l.strip()]
    # the calls that produced the scored single-agent texts: the latest uncached call per variant (a re-run replaces the first pass)
    latest = {}
    for e in single_log:
        if e.get("agent") == "solo" and e.get("status") != "failed" and not e.get("cached"):
            vv = dict(persona=e.get("persona"), lang=e.get("lang"), club_view=e.get("club_view") or "neutral", focus_player=e.get("focus_player"))
            latest[key_of(e["item_id"], vv)] = e
    used = [latest[k] for k in (key_of(r["item_id"], r["variant"]) for r in seg) if k in latest]
    single_t = [e.get("call_latency_s") or 0.0 for e in used]
    five_t = [t_by_key[key_of(r["item_id"], r["variant"])] for r in seg]
    rows = [
        dict(arm="single agent (1 call per text, no checks)", **summarize(S1), calls=len(used), tokens=sum(e["tokens"]["input"] + e["tokens"]["output"] for e in used),
             cost_usd=round(cost(used), 4), llm_s_per_text=round(statistics.median(single_t), 1) if single_t else None),
        dict(arm="five agents: Narrator first drafts (before the pre-check)", **summarize(S2), calls=None, tokens=None, cost_usd=None, llm_s_per_text=None),
        dict(arm="five agents: final on screen (verified text or fact card)", **summarize(S3), calls=len(ent), tokens=sum(e["tokens"]["input"] + e["tokens"]["output"] for e in ent),
             cost_usd=round(cost(ent), 4), llm_s_per_text=round(statistics.median(five_t), 1) if five_t else None),
    ]
    summary = dict(segment="M12 first half", items=len(seg_items), texts=len(seg), model=run["model"], rows=rows,
                   single_agent_wall_s=run["wall_s"], five_agent_full_match_wall_s=meta.get("elapsed_s"),
                   five_agent_status=dict(collections.Counter(r.get("status") for r in seg)),
                   five_agent_rerun=dict(items=sorted({r["item_id"] for r in seg if r.get("rerun")}), calls=len(rerun_ent), cost_usd=round(cost(rerun_ent), 4),
                                         note="first-half items run again after checker fixes (targeted re-runs, see run_metadata.json reruns); not part of the one-pass cost above"),
                   single_agent_rerun=[dict(tag=x["tag"], texts=x["texts"], calls=x["calls"], cost_usd=x["cost_usd"], reason=x["reason"]) for x in run.get("reruns", [])],
                   limits=["the same deterministic checks score all arms, and the five-agent pipeline uses them internally",
                           "one half of one match (one run per arm); LLM output varies between runs",
                           "each arm is scored against the facts it was given",
                           "the checks see only what they have a rule for (numbers, names, claim rules, goal direction, clock, venue, language, who is on the pitch, wording); the rest was read by hand"])
    json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=2, ensure_ascii=False)
    with open(os.path.join(OUT, "per_text.jsonl"), "w", encoding="utf-8") as f:
        for x in per_text:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    L = ["| arm | texts | unverified numbers | unknown names | unsupported claims | goal direction / score | clock | home/away wording | position / not in match / on the pitch | wording (terms, units, shares, metrics) | other (language, grammar, too long, empty) | LLM calls | cost USD | LLM s per text (median) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        other = r["language"] + r["grammar"] + r["too_long"] + r["empty"]
        L.append(f"| {r['arm']} | {r['texts']} | {r['numbers']} | {r['names']} | {r['claims']} | {r['goal']} | {r['clock']} | {r['venue']} | {r['player']} | {r['wording']} | {other} | "
                 f"{r['calls'] if r['calls'] is not None else '–'} | {r['cost_usd'] if r['cost_usd'] is not None else '–'} | {r['llm_s_per_text'] if r['llm_s_per_text'] is not None else '–'} |")
    md = "\n".join(L)
    open(os.path.join(OUT, "comparison.md"), "w", encoding="utf-8").write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
