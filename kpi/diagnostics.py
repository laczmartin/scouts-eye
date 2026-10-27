"""Diagnostics for the scouting signal (reads the ground truth; used only by
evaluate_scouting.py --diagnostics). Measures, never tunes.

a) sample-size curve: Spearman(position score, ground-truth composite) per
   position with 6, 12, 24 and 38 matches per team, on fresh fictional squads;
b) category scores vs the hidden abilities mapped to each category;
c) team effect: share of the position-score variance explained by the team.
"""

import collections
import random
import statistics

from . import aggregate as A
from . import definitions as D

# category -> hidden abilities it is supposed to reflect (documented in scouting_validation.md)
CATEGORY_ABILITIES = {
    "finishing": ["finishing"],
    "goal_contribution": ["finishing", "decision_making"],
    "chance_creation": ["passing", "decision_making"],
    "passing": ["passing", "decision_making"],
    "progression": ["passing", "ball_carrying"],
    "offensive_duels": ["ball_carrying", "pace"],
    "defensive_duels": ["tackling", "positioning"],
    "aerial_play": ["aerial"],
    "defensive_activity": ["tackling", "positioning", "pressing"],
    "pressing": ["pressing", "stamina"],
    "physical": ["stamina", "pace"],
}


def simulate_squad(seed, n_matches_per_team, log=None):
    """Fresh fictional squads from `seed`, then consecutive tournaments (fresh
    TournamentState each, so suspensions, loads and gem plans restart every
    6 matches) until every team has `n_matches_per_team` matches."""
    from synth import squads, tournament
    rng = random.Random(seed)
    teams = squads.generate_teams()
    players = squads.generate_players(rng, teams)
    abilities, standouts = squads.generate_abilities(rng, teams, players)
    gem_of = {tid: g for tid, g, _ in standouts}
    tournament._teams_cache = teams
    r = random.Random(seed * 7919 + 1)
    match_rows = []
    played = 0
    k = 0
    while played < n_matches_per_team:
        fixtures = tournament.build_fixtures()
        for fx in fixtures:
            fx["match_id"] = f"R{k}{fx['match_id']}"
        state = tournament.TournamentState(teams, players, gem_of, r)
        results, events, lineups, phys = [], {}, [], []
        n_rounds = min(6, n_matches_per_team - played)
        for fx in fixtures[: 2 * n_rounds]:
            tournament._play(fx, teams, players, abilities, r, results, events, lineups, phys, state)
        for fx, res in zip(fixtures, results):
            fx.update(home_score=res["home_score"], away_score=res["away_score"], duration_ms=res["end_ms"])
        d = dict(players=players, matches=fixtures[: 2 * n_rounds], events=events,
                 lineups=[dict(lu, on_ms="" if lu["on_ms"] is None else lu["on_ms"]) for lu in lineups], physical=phys)
        for fx in d["matches"]:
            mr, _, _ = A.match_player_rows(d, fx)
            match_rows.extend(mr)
        played += n_rounds
        k += 1
    return teams, players, abilities, match_rows


def profiles_from_rows(match_rows, players, pool, weights, settings):
    agg = A.aggregate_player_position(match_rows)
    pbi = {p["player_id"]: p for p in players}
    t_rows = A.tournament_rows(agg, pool, pbi)
    return A.build_profiles(t_rows, weights, settings)


def composite(ab, pos, comp_map):
    return statistics.fmean(ab[a] for a in comp_map[pos])


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for t in range(i, j + 1):
            r[order[t]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def r2_between_groups(values, groups):
    """Share of variance explained by group means (eta squared)."""
    if len(values) < 3:
        return None
    m = statistics.fmean(values)
    tot = sum((v - m) ** 2 for v in values)
    by = collections.defaultdict(list)
    for v, g in zip(values, groups):
        by[g].append(v)
    between = sum(len(v) * (statistics.fmean(v) - m) ** 2 for v in by.values())
    return between / tot if tot else None


def run_diagnostics(pool, weights, settings, comp_map, squad_seeds, sizes=(6, 12, 24, 38), log=print):
    """Returns a dict with the three diagnostic tables."""
    out = dict(curve={}, category={}, team={}, n_players={})
    data = {}  # (seed, size) -> (teams, players, abilities, profiles)
    for seed in squad_seeds:
        for n in sizes:
            teams, players, abilities, rows = simulate_squad(seed, n)
            profs = profiles_from_rows(rows, players, pool, weights, settings)
            data[(seed, n)] = (teams, players, abilities, profs)
            log(f"  diagnostics: squad seed {seed}, {n} matches per team -> {len(profs)} profiles")
    # a) sample-size curve, per position, pooled over squad seeds (only ranked primary profiles)
    for n in sizes:
        for pos in D.OUTFIELD_GROUPS:
            xs, ys = [], []
            for seed in squad_seeds:
                teams, players, abilities, profs = data[(seed, n)]
                for p in profs:
                    if p["profile_type"] == "primary" and p["ranking_status"] == "ranked" and p["position_group"] == pos:
                        xs.append(p["position_score"])
                        ys.append(composite(abilities[p["player_id"]], pos, comp_map))
            out["curve"][(n, pos)] = (spearman(xs, ys), len(xs))
    # b) category vs mapped abilities, at 6 and 38 matches
    for n in (sizes[0], sizes[-1]):
        for pos in D.OUTFIELD_GROUPS:
            for cat, abs_ in CATEGORY_ABILITIES.items():
                xs, ys = [], []
                for seed in squad_seeds:
                    teams, players, abilities, profs = data[(seed, n)]
                    for p in profs:
                        if p["profile_type"] == "primary" and p["ranking_status"] == "ranked" and p["position_group"] == pos:
                            xs.append(p[f"cat_{cat}"])
                            ys.append(statistics.fmean(abilities[p["player_id"]][a] for a in abs_))
                out["category"][(n, pos, cat)] = (spearman(xs, ys), len(xs))
    # c) team effect at 6 and 38 matches: eta^2 of team id on the position score, correlation with team strength,
    #    and the within-team Spearman (team means removed)
    for n in (sizes[0], sizes[-1]):
        for pos in D.OUTFIELD_GROUPS:
            vals, groups, strengths, comps = [], [], [], []
            for seed in squad_seeds:
                teams, players, abilities, profs = data[(seed, n)]
                st = {t["team_id"]: t["strength"] for t in teams}
                for p in profs:
                    if p["profile_type"] == "primary" and p["ranking_status"] == "ranked" and p["position_group"] == pos:
                        vals.append(p["position_score"]); groups.append((seed, p["team_id"]))
                        strengths.append(st[p["team_id"]]); comps.append(composite(abilities[p["player_id"]], pos, comp_map))
            eta = r2_between_groups(vals, groups)
            rho_strength = spearman(vals, strengths)
            # within-team: subtract team means from both score and composite
            by = collections.defaultdict(list)
            for v, g, c in zip(vals, groups, comps):
                by[g].append((v, c))
            wx, wy = [], []
            for g, lst in by.items():
                if len(lst) < 2:
                    continue
                mv, mc = statistics.fmean(v for v, _ in lst), statistics.fmean(c for _, c in lst)
                for v, c in lst:
                    wx.append(v - mv); wy.append(c - mc)
            out["team"][(n, pos)] = (eta, rho_strength, spearman(wx, wy), len(vals))
    return out
