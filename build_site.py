#!/usr/bin/env python3
"""Export the offline outputs into site/data/ for the static web UI (Phase 4, part A).

Standard library only. Everything the site shows comes from data/synthetic/,
data/kpi/ and data/narration/; the site never calls Azure.
"""

import collections
import csv
import json
import os
import re
import datetime


def dt_now():
    return datetime.datetime.now().strftime('%Y%m%d%H%M%S')

OUT = "site/data"
MATCH = "M12"


def read_csv(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def dump(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def clock(minute, period):
    if period == 1 and minute > 45:
        return f"45+{minute - 45}'"
    if period == 2 and minute > 90:
        return f"90+{minute - 90}'"
    return f"{minute}'"


def standings(matches, teams):
    tbl = {t: dict(team_id=t, team=teams[t]["team_name"], played=0, won=0, drawn=0, lost=0, gf=0, ga=0, points=0) for t in teams}
    for m in matches:
        h, a, gh, ga = m["home_team_id"], m["away_team_id"], int(m["home_score"]), int(m["away_score"])
        for t, f, g in ((h, gh, ga), (a, ga, gh)):
            r = tbl[t]; r["played"] += 1; r["gf"] += f; r["ga"] += g
            if f > g: r["won"] += 1; r["points"] += 3
            elif f == g: r["drawn"] += 1; r["points"] += 1
            else: r["lost"] += 1
    rows = sorted(tbl.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["team_id"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1; r["gd"] = r["gf"] - r["ga"]
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    sizes = {}
    teams = {t["team_id"]: t for t in read_csv("data/synthetic/teams.csv")}
    players = read_csv("data/synthetic/players.csv")
    matches = read_csv("data/synthetic/matches.csv")
    match = next(m for m in matches if m["match_id"] == MATCH)
    lineups = [l for l in read_csv("data/synthetic/lineups.csv") if l["match_id"] == MATCH]
    before = standings([m for m in matches if m["match_id"] < MATCH], teams)
    after = standings(matches, teams)
    pos = {r["team_id"]: r for r in before}
    a, b = pos[match["home_team_id"]], pos[match["away_team_id"]]
    leader, chaser = (a, b) if a["rank"] < b["rank"] else (b, a)
    meta = dict(project="Scout's Eye – Explainable U19 Match Intelligence", match_id=MATCH, date=match["date"], venue=match["venue"],
                teams=[match["home_team_id"], match["away_team_id"]], team_names={t: teams[t]["team_name"] for t in teams},
                team_short={t: teams[t]["team_name"].replace(" U19", "") for t in teams}, formations={t: teams[t]["formation"] for t in teams},
                score=[int(match["home_score"]), int(match["away_score"])], duration_ms=int(match["duration_ms"]),
                stoppage=[int(match["stoppage_first"]), int(match["stoppage_second"])],
                standings_before=before, standings_after=after, winner=after[0]["team_id"],
                stake={"en": f"Title decider – {leader['team'].replace(' U19', '')} {leader['points']} pts, {chaser['team'].replace(' U19', '')} {chaser['points']} pts before kick-off",
                       "hu": f"Címdöntő – {leader['team'].replace(' U19', '')} {leader['points']} pont, {chaser['team'].replace(' U19', '')} {chaser['points']} pont a kezdés előtt"},
                lineups=[dict(player_id=l["player_id"], team_id=l["team_id"], status=l["status"], position=l["position_detail"], group=l["position_group_played"],
                              on_ms=l["on_ms"], off_ms=l["off_ms"], minutes=l["minutes_played"]) for l in lineups])
    sizes["match.json"] = dump("match.json", meta)
    # events: compact columns
    cols = ["event_id", "timestamp_ms", "period", "minute", "second", "type", "outcome", "team_id", "player_id", "x", "y", "end_x", "end_y",
            "xg", "score_home", "score_away", "recipient_id", "is_penalty", "card_type", "sub_player_in_id", "related_event_id",
            "ball_speed_kmh", "body_part", "under_pressure", "pass_height", "pass_length_m", "pass_difficulty", "line_breaking", "pass_direction"]
    evs = read_jsonl(f"data/synthetic/events/{MATCH}.jsonl")
    import sys as _s0
    _s0.path.insert(0, ".")
    from kpi import event_metrics as EM
    for e in evs:      # deterministic event metrics (kpi/event_metrics.py)
        pm = EM.pass_metrics(e)
        if pm:
            e["pass_difficulty"], e["line_breaking"], e["pass_direction"] = pm["difficulty"], pm["line_breaking"], pm["direction"]
    sizes["events.json"] = dump("events.json", dict(columns=cols, rows=[[e.get(c) for c in cols] for e in evs]))
    # moments and states
    moments = read_jsonl(f"data/kpi/live/{MATCH}_moments.jsonl")
    for i, m in enumerate(moments):
        m["moment_id"] = f"{MATCH}-MOM-{i:03d}"; m["clock"] = clock(m["minute"], m["period"])
    sizes["moments.json"] = dump("moments.json", moments)
    states = []
    for s in read_jsonl(f"data/kpi/live/{MATCH}_state_by_minute.jsonl"):
        states.append(dict(minute=s["minute"], period=s["period"], t_ms=s["t_ms"], clock=clock(s["minute"], s["period"]), score=s["score"],
                           regime=s["regime"], control_index=s["control_index"], teams=s["teams"], top_players=s["top_players"],
                           players=[dict(player_id=p["player_id"], minutes=p["minutes"], score=p.get("live_position_score"),
                                         totals=p.get("totals", {}), ranking_status=p.get("ranking_status")) for p in s["players"]]))
    sizes["states.json"] = dump("states.json", states)
    # overlays + agent trace
    overlays = read_jsonl(f"data/narration/{MATCH}_overlays.jsonl")
    if not os.path.exists("data/narration/results_debug.jsonl"):
        raise SystemExit("data/narration/results_debug.jsonl is missing: it holds the agent trace. "
                         "Run `python3 run_agents.py --match M12 --mode batch` (needs Azure) or use the committed file.")
    results = read_jsonl("data/narration/results_debug.jsonl")
    log = read_jsonl("data/narration/agent_log.jsonl")
    log_by_trace = collections.defaultdict(list)
    for e in log:
        if e.get("trace_id"):
            log_by_trace[e["trace_id"]].append(dict(agent=e["agent"], cached=e["cached"], latency_s=e["latency_s"], tokens=e["tokens"],
                                                    call_latency_s=e.get("call_latency_s"), retries_429=e.get("retries_429", 0), wait_429_s=e.get("wait_429_s", 0), queue_wait_s=e.get("queue_wait_s", 0),
                                                    retry_kinds=e.get("retry_kinds", []), status=e.get("status") or ("ok" if e.get("ok", True) else "invalid_json"),
                                                    failure=e.get("failure"),
                                                    persona=e.get("persona"), lang=e.get("lang"), club_view=e.get("club_view"), focus=e.get("focus_player"), repair=e.get("repair", False)))
    # the claims of every shown text checked again with the current rules (config/claim_rules.json): the evidence panel shows
    # these; the trace keeps the run's own pre-check findings (rules may have changed since a text was written)
    from agents.facts import FactStore
    from agents.selection import load_config
    from agents import verify as V
    import run_agents
    store, rules = FactStore(MATCH), V.load_rules()
    items = {it["item_id"]: it for it in run_agents.build_items(store, load_config())}
    def claims_now(r):
        if not r.get("final") or r["item_id"] not in items:
            return None
        text = " ".join(str(r["final"].get(k) or "") for k in ("overlay", "commentary", "detail"))
        return [dict(rule=c["rule"], matched=c["matched"], supported=c["supported"], evidence=c["evidence"])
                for c in V.check_claims(text, r["variant"]["lang"], items[r["item_id"]], store, rules, player_id=r["variant"]["focus_player"])]
    trace = {}
    for r in results:
        v = r["variant"]
        key = f"{r['item_id']}|{v['persona']}|{v['lang']}|{v['club_view']}|{v['focus_player']}"
        trace[key] = dict(item_id=r["item_id"], mode=r["mode"], kind=r["kind"], clock=r.get("clock"), minute=r["minute"], verdict=r["verdict"], reasons=r["reasons"],
                          card=dict(type=r["card"].get("type"), headline_facts=r["card"].get("headline_facts"), why=r["card"].get("why_it_matters"),
                                    data=r["card"].get("data"), evidence=r["card"].get("evidence_event_ids"), source_fields=r["card"].get("source_fields")),
                          attempts=[dict(stage=a["stage"], text=a["text"], passed=a["precheck"]["passed"], bad_numbers=a["precheck"]["bad_numbers"],
                                         bad_names=a["precheck"]["bad_names"], semantic=a["precheck"].get("semantic", []), too_long=a["precheck"]["overlay_too_long"],
                                         claims=[dict(rule=c["rule"], matched=c["matched"], supported=c["supported"], evidence=c["evidence"]) for c in a["precheck"]["claims"]])
                                    for a in r["attempts"]],
                          final=r["final"], trace_id=r["trace"], calls=log_by_trace.get(r["trace"], []),
                          facts_read=sorted(k for k in (r.get("facts") or {}).keys()), fact_card=r.get("fact_card"),
                          status=r.get("status", "verified"), recovery=r.get("recovery", []), claims_now=claims_now(r), edited=r.get("edited"))
    # failure recovery: where no verified text exists, the fact card stays on screen (run_agents.py writes these rows)
    fb_path = f"data/narration/{MATCH}_fallbacks.jsonl"
    fallbacks = [x for x in read_jsonl(fb_path) if x.get("text")] if os.path.exists(fb_path) else []
    overlays += fallbacks
    for o in overlays:
        o["trace_key"] = f"{o['item_id']}|{o['persona']}|{o['lang']}|{o['club_view']}|{o['focus_player']}"
    sizes["overlays.json"] = dump("overlays.json", overlays)
    sizes["trace.json"] = dump("trace.json", trace)
    # profiles, players
    prof = read_csv("data/kpi/final/player_profiles.csv")
    cats = [k for k in prof[0] if k.startswith("cat_")]
    pbi = {p["player_id"]: p for p in players}
    profiles = []
    for p in prof:
        profiles.append(dict(player_id=p["player_id"], name=p["name"], team_id=p["team_id"], age=int(p["age"]), position=p["position_group"], profile_type=p["profile_type"],
                             minutes=float(p["minutes"]), matches=int(p["matches"]), reliability=p["reliability"], ranking_status=p["ranking_status"],
                             score=float(p["position_score"]), cats={k[4:]: float(p[k]) for k in cats}, strengths=p["strengths"], weaknesses=p["weaknesses"],
                             fouls=p["fouls"], yellow=p["yellow_cards"], red=p["red_cards"]))
    # rank within position among ranked primary profiles
    by_pos = collections.defaultdict(list)
    for p in profiles:
        if p["profile_type"] == "primary" and p["ranking_status"] == "ranked":
            by_pos[p["position"]].append(p)
    for pos_, lst in by_pos.items():
        lst.sort(key=lambda p: -p["score"])
        for i, p in enumerate(lst):
            p["rank"] = i + 1; p["rank_of"] = len(lst)
    # validation only: the hidden ground-truth rank of the four planted talents (never used by the model)
    gt = {r["player_id"]: r for r in read_csv("data/synthetic/ground_truth_abilities.csv")}
    import sys as _sys
    _sys.path.insert(0, ".")
    from synth.config import GT_COMPOSITE
    comp = lambda pid, pos_: sum(int(gt[pid][a]) for a in GT_COMPOSITE[pos_]) / len(GT_COMPOSITE[pos_])
    for pos_, lst in by_pos.items():
        order = sorted(lst, key=lambda p: -comp(p["player_id"], pos_))
        for i, p in enumerate(order):
            if gt[p["player_id"]]["standout"] == "young_gem":
                p["gt_rank"] = i + 1
    # the profile before the live match (M01-M11): what the agents used during M12 (agents/facts.py FactStore.profiles)
    before = {(p["player_id"], p["profile_type"]): p for p in read_csv("data/kpi/player_profiles.csv")}
    for p in profiles:
        q = before.get((p["player_id"], p["profile_type"]))
        if q:
            p["before"] = dict(minutes=float(q["minutes"]), matches=int(q["matches"]), reliability=q["reliability"],
                               ranking_status=q["ranking_status"], score=float(q["position_score"]))
    sizes["profiles.json"] = dump("profiles.json", profiles)
    sizes["players.json"] = dump("players.json", [dict(player_id=p["player_id"], name=p["name"], team_id=p["team_id"], age=int(p["age"]), shirt=int(p["shirt_number"]),
                                                      position=p["primary_position"], secondary=p["secondary_position"], detail=p["position_detail"], foot=p["preferred_foot"], height=int(p["height_cm"])) for p in players])
    with open("config/narration.json") as f:
        ncfg = json.load(f)
    with open("config/claim_rules.json") as f:
        rules = json.load(f)
    texts = {}
    for name in os.listdir("data/narration"):
        if name.endswith(".md"):
            with open(os.path.join("data/narration", name), encoding="utf-8") as f:
                texts[name[:-3]] = f.read()
    with open("data/narration/run_metadata.json") as f:
        run_meta = json.load(f)
    # a targeted fix is shown only while the text still carries it (a regenerated recap drops it)
    run_meta["targeted_edits"] = [e for e in run_meta.get("targeted_edits", [])
                                  if e["new"] in texts.get(os.path.basename(e["file"])[:-3], "") and e["old"] not in texts.get(os.path.basename(e["file"])[:-3], "")]
    live_summary = None
    if os.path.exists("data/narration/live_run_summary.json"):
        with open("data/narration/live_run_summary.json") as f:
            live_summary = json.load(f)
    if live_summary is not None and os.path.exists("data/narration/factcard_latency.json"):
        with open("data/narration/factcard_latency.json") as f:
            live_summary["fact_card_benchmark"] = json.load(f)   # measure_factcards.py: many offline runs, no LLM
    # agent-level latency statistics from the agent log (uncached calls only)
    agent_stats = {}
    for e in log:
        if e.get("cached") or not e.get("agent") or not e.get("tokens") or "latency_s" not in e or e.get("rerun"):
            continue   # per-agent statistics of the fresh run only (no document checks, no re-runs)
        a = agent_stats.setdefault(e["agent"], dict(calls=0, latency=0.0, call_latency=0.0, wait_429=0.0, retries=0, tokens=0))
        a["calls"] += 1; a["latency"] += e["latency_s"]; a["call_latency"] += e.get("call_latency_s") or 0; a["wait_429"] += e.get("wait_429_s") or 0
        a["retries"] += len(e.get("retry_kinds") or []) or (e.get("retries_429") or 0); a["tokens"] += e["tokens"]["total"]
    for a in agent_stats.values():
        a["mean_latency_s"] = round(a["latency"] / a["calls"], 2); a["mean_call_latency_s"] = round(a["call_latency"] / a["calls"], 2)
        a["mean_tokens"] = round(a["tokens"] / a["calls"])
    # verifier stats from results
    stats = dict(items=len(results), ok=sum(r["verdict"] == "ok" for r in results), repaired=sum(r["verdict"] == "repaired" for r in results),
                 rejected=sum(r["verdict"] == "reject" for r in results), precheck_failed=sum(not r["attempts"][0]["precheck"]["passed"] for r in results if r["attempts"]),
                 call_failed=sum(r["verdict"] == "fallback" for r in results),
                 status=dict(collections.Counter(r.get("status", "verified") for r in results)),
                 claims=collections.Counter(), claims_unsupported=collections.Counter(), semantic_failures=0)
    for r in results:
        if not r["attempts"]:
            continue
        a0 = r["attempts"][0]["precheck"]
        for c in a0["claims"]:
            stats["claims"][c["rule"]] += 1
            if not c["supported"]:
                stats["claims_unsupported"][c["rule"]] += 1
        stats["semantic_failures"] += bool(a0.get("semantic"))
    stats["claims"] = dict(stats["claims"]); stats["claims_unsupported"] = dict(stats["claims_unsupported"])
    # failure recovery: policy, the committed run, and the fault-injection test (tests/test_failure_recovery.py, no LLM)
    recovery = dict(timeout_s=ncfg.get("llm_timeout_s", 60), backoff_scale=ncfg.get("llm_backoff_scale", 1.0),
                    run=run_meta.get("failure_recovery"), fallbacks_shown=len(fallbacks), test=None)
    if os.path.exists("data/narration/failure_recovery_test.json"):
        with open("data/narration/failure_recovery_test.json", encoding="utf-8") as f:
            ft = json.load(f)
        recovery["test"] = dict(passed=ft["passed"], total=ft["total"], timeout_s=ft["timeout_s"], backoff_scale=ft["backoff_scale"],
                                rows=[dict(scenario=r["scenario"], fault=r["injected_fault"], expected=r["expected"], affected=r["affected_status"],
                                           others=r["other_status"], marks=r["trace_marks"], fact_card=r["fact_card_in_place"], passed=r["passed"]) for r in ft["rows"]])
    # player tags at thresholds (kpi/event_metrics.py; deterministic, no LLM)
    from agents.facts import FactStore as _FS
    _store = _FS(MATCH)
    tags = [dict(t_ms=t["t_ms"], minute=t["minute"], period=t["period"], clock=clock(t["minute"], t["period"]), player_id=t["player_id"],
                 team_id=t["team_id"], kind=t["kind"], value=t["value"], event_id=t["event_id"], text_en=t["text_en"], text_hu=t["text_hu"])
            for t in _store.tags]
    tag_rules = dict(pass_difficulty=EM.TAG_PASS_DIFFICULTY, shot_kmh=EM.TAG_SHOT_KMH, top_speed_kmh=EM.TAG_TOP_SPEED_KMH,
                     weights=dict(length=EM.W_LENGTH, forward=EM.W_FORWARD, pressure=EM.W_PRESSURE, height=EM.W_HEIGHT, line_breaking=EM.W_LINE),
                     sources=EM.SOURCES)
    # single agent vs five agents (compare_agents.py), if it was run
    comparison = None
    if os.path.exists("data/comparison/summary.json"):
        with open("data/comparison/summary.json", encoding="utf-8") as f:
            comparison = json.load(f)
        if os.path.exists("data/comparison/manual_review.json"):
            with open("data/comparison/manual_review.json", encoding="utf-8") as f:
                comparison["manual_review"] = json.load(f)
    sizes["narration.json"] = dump("narration.json", dict(focus_players=ncfg["focus_players"], modes=ncfg["modes"], languages=ncfg["languages"],
                                                          claim_rules=[dict(id=r["id"], description=r["description"]) for r in rules["rules"]],
                                                          texts=texts, run=run_meta, verifier=stats, live=live_summary, agent_stats=agent_stats, recovery=recovery,
                                                          comparison=comparison, tags=tags, tag_rules=tag_rules,
                                                          gt_note={"hu": "kísérletben elrejtett tehetség – a modell nem tudja, ki az", "en": "talent planted for validation – the model does not know who it is"}))
    # cache-busting version stamp for the browser (app.js / styles.css)
    stamp = dt_now()
    with open("site/index.html", encoding="utf-8") as f:
        html = f.read()
    html = re.sub(r'(styles\.css|app\.js)\?v=[^"]*', lambda m: f"{m.group(1)}?v={stamp}", html)
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    total = sum(sizes.values())
    print("site/data:", {k: f"{v / 1024:.0f} KB" for k, v in sizes.items()}, f"total {total / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
