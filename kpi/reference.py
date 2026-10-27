"""Build the reference pool: extra fictional tournaments (seeds 1000-1049) run
through the same generator (without the acceptance re-draw) and reduced to
per-player, per-position raw per-90 KPIs with at least 180 minutes."""

import datetime as dt
import json
import os
import random
import sys

from . import aggregate as A
from . import definitions as D


def build_reference(seeds, out_dir, log=print):
    sys.path.insert(0, os.getcwd())
    from synth import squads, tournament
    from synth.physical import generate_snapshots
    rows = []
    for seed in seeds:
        rng = random.Random(seed)
        teams = squads.generate_teams()
        players = squads.generate_players(rng, teams)
        abilities, standouts = squads.generate_abilities(rng, teams, players)
        gem_of = {tid: g for tid, g, _ in standouts}
        fixtures = tournament.build_fixtures()
        tournament._teams_cache = teams
        r = random.Random(seed * 7919)
        results, events, lineups, phys = [], {}, [], []
        state = tournament.TournamentState(teams, players, gem_of, r)
        for fx in fixtures:
            tournament._play(fx, teams, players, abilities, r, results, events, lineups, phys, state)
        for fx, res in zip(fixtures, results):
            fx.update(home_score=res["home_score"], away_score=res["away_score"], duration_ms=res["end_ms"])
        # dataset dict in the same shape as load_dataset (values typed like csv strings where needed)
        d = dict(players=players, matches=fixtures, events=events,
                 lineups=[dict(lu, on_ms="" if lu["on_ms"] is None else lu["on_ms"]) for lu in lineups],
                 physical=phys)
        match_rows = []
        for fx in fixtures:
            mr, _, _ = A.match_player_rows(d, fx)
            match_rows.extend(mr)
        agg = A.aggregate_player_position(match_rows)
        n = 0
        for (pid, pos), a in agg.items():
            if pos not in D.OUTFIELD_GROUPS or a["minutes"] < 180:
                continue
            raw = A.per90_values(a)
            row = dict(seed=seed, player_id=f"S{seed}-{pid}", position_group=pos, minutes=round(a["minutes"], 1))
            row.update({k: round(v, 4) for k, v in raw.items()})
            rows.append(row)
            n += 1
        log(f"  reference seed {seed}: {n} player-position rows")
    os.makedirs(out_dir, exist_ok=True)
    A.write_csv(os.path.join(out_dir, "reference_player_kpis.csv"), rows)
    meta = dict(seeds=list(seeds), tournaments=len(seeds), rows=len(rows), min_minutes=180,
                acceptance_loop=False, generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                note="Fictional reference tournaments from the same generator; raw per-90 KPIs per player and position only.")
    with open(os.path.join(out_dir, "reference_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return rows
