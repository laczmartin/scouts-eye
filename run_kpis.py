#!/usr/bin/env python3
"""Phase 2 entry point: KPIs, profiles, team KPIs, reference pool and the M12 live run.

Usage:
    python run_kpis.py --seed 42 [--data data/synthetic] [--out data/kpi]
                       [--reference-seeds 1000-1049] [--skip-reference]

Outputs (data/kpi/):
    player_match_kpis.csv, player_tournament_kpis.csv, player_profiles.csv,
    team_match_kpis.csv            (baseline: M01-M11)
    final/...                      (M01-M12, after the live match)
    live/M12_moments.jsonl, live/M12_state_by_minute.jsonl
Nothing here reads ground_truth_abilities.csv.
"""

import argparse
import datetime as dt
import json
import os
import time

from kpi import aggregate as A
from kpi import definitions as D
from kpi.reference import build_reference
import live_engine


def parse_seeds(spec):
    a, b = spec.split("-")
    return list(range(int(a), int(b) + 1))


def run_batch(d, matches, pool, weights, out_dir, label):
    match_rows, team_rows = [], []
    for m in matches:
        mr, tr, _ = A.match_player_rows(d, m)
        match_rows.extend(mr)
        team_rows.extend(tr)
    agg = A.aggregate_player_position(match_rows)
    pbi = {p["player_id"]: p for p in d["players"]}
    t_rows = A.tournament_rows(agg, pool, pbi)
    profiles = A.build_profiles(t_rows, weights)
    A.write_csv(os.path.join(out_dir, "player_match_kpis.csv"), match_rows)
    A.write_csv(os.path.join(out_dir, "player_tournament_kpis.csv"), t_rows)
    A.write_csv(os.path.join(out_dir, "player_profiles.csv"), profiles)
    team_fields = ["match_id", "team_id", "opponent_id", "possession_pct", "field_tilt_pct", "ppda", "xg", "npxg", "shots", "goals",
                   "passes", "pass_accuracy_pct", "pressures", "duels", "duels_won_pct", "saves", "fouls", "possessions"]
    A.write_csv(os.path.join(out_dir, "team_match_kpis.csv"), team_rows, team_fields)
    print(f"  {label}: {len(match_rows)} player-match rows, {len(t_rows)} player-position rows, {len(profiles)} profiles -> {out_dir}")
    return profiles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--out", default="data/kpi")
    ap.add_argument("--reference", default="data/reference")
    ap.add_argument("--reference-seeds", default="1000-1049")
    ap.add_argument("--skip-reference", action="store_true", help="reuse an existing reference pool")
    args = ap.parse_args()
    t0 = time.time()
    seeds = parse_seeds(args.reference_seeds)
    ref_path = os.path.join(args.reference, "reference_player_kpis.csv")
    if args.skip_reference and os.path.exists(ref_path):
        print(f"Reference pool: reusing {ref_path}")
    else:
        print(f"Reference pool: generating {len(seeds)} fictional tournaments (seeds {seeds[0]}-{seeds[-1]})")
        build_reference(seeds, args.reference, log=lambda s: None)
    pool = A.ReferencePool(A.read_csv(ref_path))
    print("  pool size per position:", dict(sorted(pool.size.items())))
    with open("config/position_weights.json") as f:
        weights = json.load(f)
    d = A.load_dataset(args.data)
    baseline = [m for m in d["matches"] if m["live_flag"] != "True"]
    live = [m for m in d["matches"] if m["live_flag"] == "True"]
    print("Baseline (M01-M11):")
    run_batch(d, baseline, pool, weights, args.out, "baseline")
    print("Live match:")
    for m in live:
        live_engine.run_offline(d, m, pool, weights, baseline_dir=args.out, out_dir=os.path.join(args.out, "live"))
    print("Final (M01-M12):")
    run_batch(d, d["matches"], pool, weights, os.path.join(args.out, "final"), "final")
    meta = dict(seed=args.seed, data=args.data, reference_seeds=[seeds[0], seeds[-1]], shrink_k=D.SHRINK_K,
                generated_at=dt.datetime.now(dt.timezone.utc).isoformat(), weights_file="config/position_weights.json")
    with open(os.path.join(args.out, "kpi_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
