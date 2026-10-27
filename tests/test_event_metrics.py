#!/usr/bin/env python3
"""Tests for kpi/event_metrics.py: pass distance, direction, difficulty, line-breaking proxy, ball and shot speed,
player tags, and the facts the Match Analyst gets. No AI, no network.

    python3 tests/test_event_metrics.py     # standard library; the Analyst-facts cases also need agent-framework
"""

import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kpi import event_metrics as EM   # noqa: E402

RESULTS = []


def case(name, ok, detail=""):
    RESULTS.append(dict(case=name, passed=bool(ok), detail=str(detail)))


def base_pass(**kw):
    e = dict(type="pass", outcome="success", x=40.0, y=50.0, end_x=55.0, end_y=50.0, under_pressure=False, pass_height="ground", ball_speed_kmh=50.0)
    e.update(kw)
    return e


def main():
    events = [json.loads(l) for f in sorted(glob.glob("data/synthetic/events/M*.jsonl")) for l in open(f, encoding="utf-8")]
    passes = [(e, EM.pass_metrics(e)) for e in events if e["type"] == "pass"]
    passes = [(e, m) for e, m in passes if m]
    # distance: the formula reproduces the generator's pass_length_m
    worst = max(abs(m["distance_m"] - e["pass_length_m"]) for e, m in passes if e.get("pass_length_m") is not None)
    case("pass distance from the coordinates equals pass_length_m (all tournament passes)", worst <= 0.2, f"largest difference {worst:.2f} m")
    case("difficulty is between 0 and 1 for every pass", all(0 <= m["difficulty"] <= 1 for _, m in passes))
    short, long_ = EM.pass_metrics(base_pass(end_x=48)), EM.pass_metrics(base_pass(end_x=78))
    case("a longer pass is harder", long_["difficulty"] > short["difficulty"], f"{short['difficulty']} < {long_['difficulty']}")
    free, pressed = EM.pass_metrics(base_pass()), EM.pass_metrics(base_pass(under_pressure=True))
    case("a pass under pressure is harder (+0.20)", abs(pressed["difficulty"] - free["difficulty"] - 0.20) < 1e-9)
    fwd, back = EM.pass_metrics(base_pass(x=50, end_x=65)), EM.pass_metrics(base_pass(x=50, end_x=35))
    case("a forward pass is harder than a backward pass of the same length", fwd["difficulty"] > back["difficulty"] and fwd["direction"] == "forward" and back["direction"] == "backward")
    lb = EM.pass_metrics(base_pass(x=60, end_x=72))
    case("a forward pass of 12.6 m from 60 to 72 crosses into the final third: line-breaking", lb["line_breaking"] and lb["forward_m"] >= 10)
    nolb = EM.pass_metrics(base_pass(x=40, end_x=48))
    case("a short pass inside the middle third is not line-breaking", not nolb["line_breaking"])
    box = EM.pass_metrics(base_pass(x=75, y=50, end_x=88, end_y=50))
    case("a pass into the penalty area from outside is line-breaking and into_box", box["line_breaking"] and box["into_box"])
    # the formula is not fitted, but harder passes must be completed less often (validation on the whole tournament)
    bins = [(0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 0.8), (0.8, 1.01)]
    rates = []
    for a, b in bins:
        s = [m for _, m in passes if a <= m["difficulty"] < b]
        rates.append(round(100 * sum(x["completed"] for x in s) / len(s), 1))
    case("completion falls with every difficulty band (6 bands, all tournament passes)", all(rates[i] > rates[i + 1] for i in range(len(rates) - 1)), rates)
    # ball speed and shot speed are plausible for U19 (Rađa et al. 2019: maximal U19 instep kick about 107-111 km/h in a test)
    foot = [e["ball_speed_kmh"] for e in events if e["type"] == "shot" and e["body_part"] in ("right_foot", "left_foot")]
    head = [e["ball_speed_kmh"] for e in events if e["type"] == "shot" and e["body_part"] == "head"]
    case("foot shots 55-115 km/h (match shots are at most the maximal test speed)", min(foot) >= 55 and max(foot) <= 115, f"{min(foot)}-{max(foot)}")
    case("median foot shot 75-95 km/h", 75 <= sorted(foot)[len(foot) // 2] <= 95, sorted(foot)[len(foot) // 2])
    case("headers are slower: 25-70 km/h", min(head) >= 25 and max(head) <= 70, f"{min(head)}-{max(head)}")
    pspeed = [m["ball_speed_kmh"] for _, m in passes if m["ball_speed_kmh"]]
    case("pass ball speed 15-90 km/h", min(pspeed) >= 15 and max(pspeed) <= 90, f"{min(pspeed)}-{max(pspeed)}")
    # player tags
    names = {r["player_id"]: r["name"] for r in csv.DictReader(open("data/synthetic/players.csv", encoding="utf-8"))}
    m12 = [e for e in events if e["match_id"] == "M12"]
    tags = EM.match_tags(m12, EM.read_snapshots("M12"), lambda p: names.get(p, p))
    kinds = {t["kind"] for t in tags}
    case("M12 tags: three kinds (difficult pass, fast shot, fastest run so far)", kinds == {"difficult_pass", "fast_shot", "top_speed"}, sorted(kinds))
    case("every difficult-pass tag is a completed pass at or above the threshold",
         all(t["value"] >= EM.TAG_PASS_DIFFICULTY for t in tags if t["kind"] == "difficult_pass"))
    case("every fast-shot tag is at or above 100 km/h", all(t["value"] >= EM.TAG_SHOT_KMH for t in tags if t["kind"] == "fast_shot"))
    tops = [t["value"] for t in tags if t["kind"] == "top_speed"]
    case("'fastest run so far' tags only go up", all(tops[i] < tops[i + 1] for i in range(len(tops) - 1)), tops)
    case("tags are in time order and carry a name", all(tags[i]["t_ms"] <= tags[i + 1]["t_ms"] for i in range(len(tags) - 1)) and all(names[t["player_id"]] in t["text_en"] for t in tags))
    case("M12 has a handful of tags, not a flood (5-20)", 5 <= len(tags) <= 20, len(tags))
    # the Match Analyst gets the metrics as facts (needs the pipeline, i.e. agent-framework)
    try:
        import agent_framework  # noqa: F401
        from agents.facts import FactStore
        from agents.pipeline import build_facts
        from agents.selection import load_config
        import run_agents
        store, cfg = FactStore("M12"), load_config()
        items = run_agents.build_items(store, cfg)
        goal = next(it for it in items if it["kind"] == "moment" and it["moment"]["type"] == "goal")
        f, _ = build_facts(store, goal)
        case("a goal item's facts carry the shot speed", f["moment"].get("ball_metrics", {}).get("shot", {}).get("shot_speed_kmh") is not None,
             f["moment"].get("ball_metrics"))
        with_tags = [(it, build_facts(store, it)[0]) for it in items]
        with_tags = [(it, f) for it, f in with_tags if f["state"].get("player_tags_last_5min")]
        case("some items get the player tags of the last 5 minutes", len(with_tags) > 0, len(with_tags))
        future = [it["item_id"] for it, f in with_tags for t in store.tags_between(it["t_ms"] - 300000, it["t_ms"]) if t["t_ms"] > it["t_ms"]]
        case("no item gets a tag from its future", not future)
    except ImportError:
        case("Analyst facts (skipped: agent-framework not installed)", True)
    for r in RESULTS:
        print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['case']}" + (f"  ({r['detail']})" if r["detail"] else ""))
    n = sum(r["passed"] for r in RESULTS)
    print(f"\n{n}/{len(RESULTS)} cases passed")
    json.dump(dict(note="tests/test_event_metrics.py", passed=n, total=len(RESULTS), rows=RESULTS),
              open("data/narration/event_metrics_test.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
