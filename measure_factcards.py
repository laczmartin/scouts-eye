#!/usr/bin/env python3
"""Measure the deterministic fact-card latency of live mode (no LLM, no Azure, free).

Replays the M12 event stream through the same code path as `run_agents.py --mode live`
(live engine update -> facts mirrored into the store -> batch selection rules -> fact
card templates with the clock / score / venue checks), for moment and state cards, and measures the time from an
event's arrival to the finished fact cards it triggers. Repeated several times.

Usage: python3 measure_factcards.py [--runs 5]
"""

import argparse
import json
import os
import statistics
import time

from agents import factcards as FC
from agents.facts import FactStore
from agents.selection import load_config, select_items
from kpi import aggregate as A
import live_engine


def one_run(cfg):
    d = A.load_dataset("data/synthetic")
    match = next(m for m in d["matches"] if m["match_id"] == "M12")
    pool = A.ReferencePool(A.read_csv("data/reference/reference_player_kpis.csv"))
    with open("config/position_weights.json") as f:
        weights = json.load(f)
    state = live_engine.make_state(d, match, pool, weights, "data/kpi")
    store = FactStore("M12")
    store.moments, store.states, store.by_id = [], [], {}
    done, lat = set(), []
    for e in d["events"]["M12"]:
        t0 = time.perf_counter()
        new = live_engine.update(state, e)
        new_snapshot = len(state.snapshots) > len(store.states)
        if new_snapshot:
            store.states = [json.loads(json.dumps(s)) for s in state.snapshots]
        for m in new:
            m = json.loads(json.dumps(m))
            m["moment_id"] = f"M12-MOM-{len(store.moments):03d}"
            store.moments.append(m); store.by_id[m["moment_id"]] = m; store.annotate_moment(m)
        if not new and not new_snapshot:
            continue
        cards = 0
        for mode in ("fan", "analyst"):
            for it in select_items(store, cfg, mode):
                key = (mode, it["kind"], it["t_ms"])
                if key in done:
                    continue
                done.add(key)
                for lang in cfg["languages"]:
                    if FC.checked_fact_card(store, dict(it, mode=mode), lang, cfg):
                        cards += 1
        if cards:
            lat.append(time.perf_counter() - t0)
    return lat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()
    cfg = load_config()
    all_lat, per_run = [], []
    for i in range(args.runs):
        lat = one_run(cfg)
        all_lat += lat
        per_run.append(dict(run=i + 1, n=len(lat), mean_ms=round(1000 * statistics.fmean(lat), 2), max_ms=round(1000 * max(lat), 2)))
        print(f"run {i + 1}: n={len(lat)} mean {1000 * statistics.fmean(lat):.1f} ms max {1000 * max(lat):.1f} ms")
    q = sorted(all_lat)
    summary = dict(what="time from an event's arrival to its finished fact cards (live-mode code path, no LLM)",
                   runs=args.runs, n=len(q), mean_ms=round(1000 * statistics.fmean(q), 2), median_ms=round(1000 * statistics.median(q), 2),
                   p95_ms=round(1000 * q[int(0.95 * (len(q) - 1))], 2), max_ms=round(1000 * q[-1], 2), per_run=per_run,
                   machine="author's laptop (macOS), Python " + ".".join(map(str, __import__("sys").version_info[:3])))
    with open("data/narration/factcard_latency.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_run"}))


if __name__ == "__main__":
    main()
