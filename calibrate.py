#!/usr/bin/env python3
"""Large-sample realism check against the PUBLISHED benchmarks (benchmarks.py).

Simulates many matches (default 60) with the current parameters, prints the
published benchmark checks, and lists the other statistics as descriptive
values without a target (no licensed or unpublished targets are used).

Usage: python calibrate.py [--matches 60] [--seed 2024]
"""
import argparse
import random
import statistics

import benchmarks as B
import validate as V
from synth import simulator, squads

ap = argparse.ArgumentParser()
ap.add_argument("--matches", type=int, default=60)
ap.add_argument("--seed", type=int, default=2024)
args = ap.parse_args()
rng = random.Random(args.seed)
teams = squads.generate_teams(); players = squads.generate_players(rng, teams); ab, _ = squads.generate_abilities(rng, teams, players)
pairs = [("T1", "T2"), ("T3", "T4"), ("T4", "T1"), ("T2", "T3"), ("T1", "T3"), ("T4", "T2")]
team_rows, match_rows = [], []
for i in range(args.matches):
    h, a = pairs[i % 6]
    ev, *_ = simulator.simulate_match(dict(match_id="X", home_team_id=h, away_team_id=a), teams, players, ab, rng)
    match_rows.append(V.match_metrics(ev))
    for tid in (h, a):
        m = V.team_match_metrics(ev, tid); m["team_id"] = tid; team_rows.append(m)

goals = statistics.fmean(x["goals"] for x in match_rows)
passes = statistics.fmean(t["passes"] for t in team_rows)
print(f"{args.matches} simulated matches\n\nPublished benchmarks:")
for name, value, (lo, hi) in [("goals per match (UEFA Youth League)", goals, B.GOALS_PER_MATCH),
                              ("passes per team per match (Šrámková 2024, assumed per team per match)", passes, B.PASSES_PER_TEAM)]:
    print(f"  {'OK  ' if lo <= value <= hi else 'WARN'} {name:44s} {value:8.2f}   [{lo}-{hi}]")
print("\nDescriptive statistics (no external target):")
for key in ("pass_accuracy", "long_passes", "shots", "shots_on_target_pct", "xg", "defensive_duels", "aerial_duels", "interceptions", "ppda", "corners", "fouls", "yellow_cards"):
    print(f"  {key:22s} {statistics.fmean(t[key] for t in team_rows):8.2f}  per team per match")
for key in ("total_events", "passes", "shots", "mean_xg_per_shot", "pressures"):
    print(f"  {key:22s} {statistics.fmean(x[key] for x in match_rows):8.2f}  per match")
print(f"  {'goals / xG':22s} {sum(x['goals'] for x in match_rows) / sum(x['xg'] for x in match_rows):8.2f}")
print("  shots per team:", {t: round(statistics.fmean(r["shots"] for r in team_rows if r["team_id"] == t), 1) for t in sorted({r["team_id"] for r in team_rows})})
