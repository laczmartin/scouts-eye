#!/usr/bin/env python3
"""Generate the synthetic U19 tournament dataset.

Usage:
    python generate.py --seed 42 [--out data/synthetic]

Everything is fictional. The same seed always produces identical output.
"""

import argparse
import random
import time

from synth import squads, tournament


def main():
    ap = argparse.ArgumentParser(description="Synthetic U19 tournament generator (Phase 1)")
    ap.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    ap.add_argument("--out", default="data/synthetic", help="output directory")
    args = ap.parse_args()

    t0 = time.time()
    rng = random.Random(args.seed)
    teams = squads.generate_teams()
    players = squads.generate_players(rng, teams)
    abilities, standouts = squads.generate_abilities(rng, teams, players)
    print(f"Squads: {len(teams)} teams, {len(players)} players")

    fixtures, events, lineups, phys, attempt, state = tournament.simulate_tournament(
        args.seed, teams, players, abilities, standouts)
    for fx in fixtures:
        flag = " (live)" if fx["live_flag"] else ""
        print(f"  {fx['match_id']} MD{fx['matchday']} {fx['date']}  {fx['home_team_id']} {fx['home_score']}-{fx['away_score']} {fx['away_team_id']}{flag}")
    n_events = sum(len(v) for v in events.values())
    tournament.write_outputs(args.out, args.seed, teams, players, abilities, standouts, fixtures, events, lineups, phys, attempt, state)
    for t, p, s, m in state.injury_log:
        print(f"  injury: {p} ({t}) {s} in {m}")
    print(f"Wrote {n_events} events, {len(lineups)} lineup rows, {len(phys)} physical rows to {args.out} "
          f"in {time.time() - t0:.1f}s (seed={args.seed}, title-decider attempt={attempt})")


if __name__ == "__main__":
    main()
