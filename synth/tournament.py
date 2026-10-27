"""Tournament orchestration: fixtures, title-decider logic and output writing."""

import csv
import datetime as dt
import json
import os
import random

from . import config as C
from .simulator import simulate_match
from .physical import generate_snapshots

MAX_TITLE_ATTEMPTS = 1200


def build_fixtures():
    """Double round-robin, 6 matchdays x 2 matches, 3 days apart (days 1, 4, 7,
    10, 13, 16) at one neutral venue. "Home" and "away" are only nominal. The two
    strongest teams (T1, T2) meet on matchday 1 (M01) and again in M12."""
    first_round = [
        [("T1", "T2"), ("T3", "T4")],
        [("T1", "T3"), ("T2", "T4")],
        [("T4", "T1"), ("T2", "T3")],
    ]
    second_round = [
        [("T3", "T1"), ("T4", "T2")],
        [("T1", "T4"), ("T3", "T2")],
        [("T4", "T3"), ("T2", "T1")],
    ]
    rounds = first_round + second_round
    start = dt.date.fromisoformat(C.TOURNAMENT_START)
    fixtures, day = [], start
    mid = 0
    for md, pairs in enumerate(rounds, start=1):
        for home, away in pairs:
            mid += 1
            fixtures.append(dict(match_id=f"M{mid:02d}", matchday=md, date=day.isoformat(), day_number=(day - start).days + 1,
                                 venue=C.VENUE, home_team_id=home, away_team_id=away))
        day += dt.timedelta(days=C.MATCHDAY_GAP_DAYS)
    return fixtures


def standings(results, team_ids):
    tbl = {t: dict(team_id=t, played=0, won=0, drawn=0, lost=0, gf=0, ga=0, points=0) for t in team_ids}
    for r in results:
        h, a, gh, ga = r["home_team_id"], r["away_team_id"], r["home_score"], r["away_score"]
        for t, f, g in ((h, gh, ga), (a, ga, gh)):
            row = tbl[t]
            row["played"] += 1
            row["gf"] += f
            row["ga"] += g
            if f > g:
                row["won"] += 1; row["points"] += 3
            elif f == g:
                row["drawn"] += 1; row["points"] += 1
            else:
                row["lost"] += 1
    rows = list(tbl.values())
    for r in rows:
        r["gd"] = r["gf"] - r["ga"]
    rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team_id"]))
    return rows


def title_open_before_last(results, fixtures):
    """True when M12 decides the title: the two M12 teams are 1st and 2nd after
    11 matches, at most 3 points apart, and nobody else can still finish first."""
    last = fixtures[-1]
    tbl = standings(results, [t["team_id"] for t in _teams_cache])
    top2 = {tbl[0]["team_id"], tbl[1]["team_id"]}
    if top2 != {last["home_team_id"], last["away_team_id"]}:
        return False
    if tbl[0]["points"] - tbl[1]["points"] > 3:
        return False
    if tbl[2]["points"] > tbl[1]["points"]:
        return False
    return True


_teams_cache = []


def simulate_tournament(seed, teams, players, abilities, standouts, log=print):
    """Simulate all 12 matches with cross-match state (suspensions, injuries,
    fatigue load, rotation history, the gem's planned appearances).

    The whole tournament is re-drawn with a derived seed (seed * 7919 + attempt)
    until the acceptance criteria hold:
      * M12 is a title decider (see title_open_before_last),
      * 2-3 draws in 12 matches,
      * 3.4-3.9 goals per match on average, no match with more than 8 goals,
      * tournament goals / xG between 1.05 and 1.20,
      * the top scorer has 4-6 goals,
      * at least one tournament-ending (major) injury,
      * every team's young hidden gem plays 180-290 minutes (gems are never injured or booked)
        and is a top-3 talent of his position by the hidden ground-truth composite.
    The goals and goals / xG bands are the two generator design ranges of the
    README data statement; the other criteria are design choices.
    The attempt index is stored in generation_metadata.json, so the output is
    still fully reproducible from the seed alone."""
    global _teams_cache
    _teams_cache = teams
    fixtures = build_fixtures()
    gem_of = {tid: gem for tid, gem, _ in standouts}
    for attempt in range(MAX_TITLE_ATTEMPTS):
        rng = random.Random(seed * 7919 + attempt)
        results, all_events, all_lineups, all_phys, absences = [], {}, [], [], []
        state = TournamentState(teams, players, gem_of, rng)
        for fx in fixtures:
            _play(fx, teams, players, abilities, rng, results, all_events, all_lineups, all_phys, state)
        draws = sum(1 for r in results if r["home_score"] == r["away_score"])
        goals = sum(r["home_score"] + r["away_score"] for r in results)
        xg = sum(e["xg"] for evs in all_events.values() for e in evs if e["type"] == "shot")
        ratio = goals / xg if xg else 0.0
        title_open = title_open_before_last(results[:11], fixtures)
        max_goals = max(r["home_score"] + r["away_score"] for r in results)
        scorers = {}
        for evs in all_events.values():
            for e in evs:
                if e["type"] == "shot" and e["outcome"] == "goal":
                    scorers[e["player_id"]] = scorers.get(e["player_id"], 0) + 1
        top = max(scorers.values()) if scorers else 0
        majors = sum(1 for inj in state.injury_log if inj[2] == "major")
        gem_minutes = {}
        for lu in all_lineups:
            if lu["player_id"] in gem_of.values():
                gem_minutes[lu["player_id"]] = gem_minutes.get(lu["player_id"], 0.0) + lu["minutes_played"]
        gems_ok = all(180 <= m <= 290 for m in gem_minutes.values())
        from .squads import gem_composite_rank
        gems_ok = gems_ok and all(gem_composite_rank(next(p for p in players if p["player_id"] == g), players, abilities) <= 3
                                  for g in gem_of.values())
        if (title_open and 2 <= draws <= 3 and 41 <= goals <= 46 and 1.05 <= ratio <= 1.20
                and max_goals <= 8 and 4 <= top <= 6 and majors >= 1 and gems_ok):
            break
        log(f"  attempt {attempt}: not accepted (title open={title_open}, draws={draws}, goals={goals}, "
            f"goals/xG={ratio:.2f}, top scorer={top}, major injuries={majors}, gem minutes ok={gems_ok}); re-drawing")
    else:
        raise RuntimeError("Could not produce an accepted tournament; adjust team strengths or acceptance criteria")
    for fx, r in zip(fixtures, results):
        fx.update(home_score=r["home_score"], away_score=r["away_score"],
                  live_flag=(fx["match_id"] == "M12"), stoppage_first=r["st"][0], stoppage_second=r["st"][1],
                  duration_ms=r["end_ms"])
    return fixtures, all_events, all_lineups, all_phys, attempt, state


class TournamentState:
    """Carries suspensions, injuries, fatigue load and rotation history between matches."""

    def __init__(self, teams, players, gem_of, rng):
        self.rng = rng
        self.players = players
        self.gem_of = gem_of
        self.yellows = {}          # player_id -> accumulated yellow cards (reset after a ban)
        self.ban_matches = {}      # player_id -> matches still to serve
        self.injured_until = {}    # player_id -> matchday index until which the player is out (None = tournament)
        self.load = {p["player_id"]: 0.0 for p in players}
        self.recent_full = {p["player_id"]: 0 for p in players}
        self.injury_log = []       # (team_id, player_id, severity, match_id)
        self.played = {t["team_id"]: 0 for t in teams}
        self.groups_played = {p["player_id"]: set() for p in players}  # positions actually played so far
        self.hybrids = {p["player_id"]: p["secondary_position"] for p in players if p.get("secondary_position")}
        self.primary = {p["player_id"]: p["position_group"] for p in players}
        # gem plan: starts in 2 of the 6 matches, comes on as a sub in 3 others
        self.gem_plan = {}
        for tid, gem in gem_of.items():
            idx = list(range(6))
            starts = set(rng.sample(idx, 2))
            rest = [i for i in idx if i not in starts]
            subs = set(rng.sample(rest, 3))
            self.gem_plan[tid] = (starts, subs)

    def context_for(self, tid, matchday):
        unavailable = {}
        for p in self.players:
            if p["team_id"] != tid:
                continue
            pid = p["player_id"]
            if self.ban_matches.get(pid, 0) > 0:
                unavailable[pid] = "suspended"
            elif pid in self.injured_until and (self.injured_until[pid] is None or matchday <= self.injured_until[pid]):
                unavailable[pid] = "injured"
        k = self.played[tid]
        starts, subs = self.gem_plan[tid]
        need_position = {}
        for pid, sec in self.hybrids.items():
            if pid[:2] != tid:
                continue
            missing = {self.primary[pid], sec} - self.groups_played[pid]
            if missing:
                need_position[pid] = missing
        return dict(unavailable=unavailable, load=self.load, gem_id=self.gem_of[tid],
                    gem_starts=(k in starts), gem_sub_in=(k in subs), recent_full=self.recent_full,
                    need_position=need_position, matchday=matchday)

    def after_match(self, fx, events, lineups, injuries, end_ms):
        matchday = fx["matchday"]
        for tid in (fx["home_team_id"], fx["away_team_id"]):
            self.played[tid] += 1
        # serve bans
        for pid in list(self.ban_matches):
            tid = pid[:2]
            if tid in (fx["home_team_id"], fx["away_team_id"]) and self.ban_matches[pid] > 0:
                self.ban_matches[pid] -= 1
        # new cards
        for e in events:
            if e["type"] != "card":
                continue
            pid = e["player_id"]
            if e["card_type"] == "yellow":
                self.yellows[pid] = self.yellows.get(pid, 0) + 1
            elif e["card_type"] == "second_yellow":
                self.yellows[pid] = max(0, self.yellows.get(pid, 0) - 1)  # the first yellow of this match does not accumulate
                self.ban_matches[pid] = self.ban_matches.get(pid, 0) + 1
            elif e["card_type"] == "straight_red":
                self.ban_matches[pid] = self.ban_matches.get(pid, 0) + 2
        for pid, n in list(self.yellows.items()):
            if n >= 2:
                self.yellows[pid] = 0
                self.ban_matches[pid] = self.ban_matches.get(pid, 0) + 1
        # injuries
        for tid, pid, sev in injuries:
            self.injury_log.append((tid, pid, sev, fx["match_id"]))
            self.injured_until[pid] = None if sev == "major" else matchday + 1
        # load and rotation history
        full_ms = end_ms
        for lu in lineups:
            pid = lu["player_id"]
            mins = lu["minutes_played"]
            if lu.get("position_group_played"):
                self.groups_played[pid].add(lu["position_group_played"])
            self.load[pid] = self.load[pid] * C.SIM["load_recovery"] + mins / 90.0
            if lu["on_ms"] is not None and lu["on_ms"] == 0 and mins >= 0.85 * full_ms / 60000.0:
                self.recent_full[pid] = self.recent_full.get(pid, 0) + 1
            else:
                self.recent_full[pid] = 0


def _play(fx, teams, players, abilities, rng, results, all_events, all_lineups, all_phys, state):
    context = {tid: state.context_for(tid, fx["matchday"]) for tid in (fx["home_team_id"], fx["away_team_id"])}
    loads_before = dict(state.load)
    events, lineups, gh, ga, st, end_ms, injuries = simulate_match(fx, teams, players, abilities, rng, context)
    results.append(dict(match_id=fx["match_id"], home_team_id=fx["home_team_id"], away_team_id=fx["away_team_id"],
                        home_score=gh, away_score=ga, st=st, end_ms=end_ms))
    all_events[fx["match_id"]] = events
    all_lineups.extend(lineups)
    pbi = {p["player_id"]: p for p in players}
    all_phys.extend(generate_snapshots(rng, fx["match_id"], lineups, pbi, abilities, end_ms, loads_before))
    state.after_match(fx, events, lineups, injuries, end_ms)


# ------------------------------------------------------------------ outputs
def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def write_outputs(out_dir, seed, teams, players, abilities, standouts, fixtures, events, lineups, phys, attempt, state=None):
    os.makedirs(os.path.join(out_dir, "events"), exist_ok=True)
    write_csv(os.path.join(out_dir, "teams.csv"), teams,
              ["team_id", "team_name", "city", "formation", "strength", "style_possession", "style_pressing", "style_directness"])
    write_csv(os.path.join(out_dir, "players.csv"), players,
              ["player_id", "team_id", "name", "shirt_number", "birth_date", "age", "position_group", "position_detail",
               "primary_position", "secondary_position", "preferred_foot", "height_cm", "squad_role"])
    gt_rows = []
    standout_map = {}
    for tid, gem, others in standouts:
        standout_map[gem] = "young_gem"
        for o in others:
            standout_map[o] = "standout"
    team_strength = {t["team_id"]: t["strength"] for t in teams}
    secondary = abilities.get("_secondary", {})
    for p in players:
        row = dict(player_id=p["player_id"], team_id=p["team_id"], team_strength=team_strength[p["team_id"]],
                   standout=standout_map.get(p["player_id"], ""))
        row.update(abilities[p["player_id"]])
        row["overall"] = round(sum(abilities[p["player_id"]].values()) / len(C.ABILITY_NAMES), 1)
        sec = secondary.get(p["player_id"])
        row["secondary_position"] = sec["position"] if sec else ""
        row["secondary_penalty"] = sec["penalty"] if sec else ""
        row["secondary_key_abilities"] = ";".join(f"{k}:{max(5, abilities[p['player_id']][k] - sec['penalty'])}" for k in sec["key_abilities"]) if sec else ""
        gt_rows.append(row)
    write_csv(os.path.join(out_dir, "ground_truth_abilities.csv"), gt_rows,
              ["player_id", "team_id", "team_strength", "standout"] + C.ABILITY_NAMES + ["overall",
               "secondary_position", "secondary_penalty", "secondary_key_abilities"])
    write_csv(os.path.join(out_dir, "matches.csv"), fixtures,
              ["match_id", "matchday", "date", "day_number", "venue", "home_team_id", "away_team_id", "home_score", "away_score",
               "live_flag", "stoppage_first", "stoppage_second", "duration_ms"])
    for mid, evs in events.items():
        with open(os.path.join(out_dir, "events", f"{mid}.jsonl"), "w", encoding="utf-8") as f:
            for e in evs:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
    write_csv(os.path.join(out_dir, "lineups.csv"), lineups,
              ["match_id", "team_id", "player_id", "status", "position_detail", "position_group_played", "on_ms", "off_ms",
               "minutes_played", "end_reason"])
    write_csv(os.path.join(out_dir, "physical_snapshots.csv"), phys,
              ["match_id", "team_id", "player_id", "window_index", "window_start_min", "minutes_in_window", "distance_m",
               "high_speed_distance_m", "sprint_distance_m", "sprints", "top_speed_kmh"])
    from . import __version__
    meta = dict(seed=seed, generator_version=__version__, generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                tournament_start=C.TOURNAMENT_START, title_decider_attempt=attempt,
                team_profiles=C.TEAM_PROFILES, simulation_parameters=C.SIM,
                pitch_m=[C.PITCH_LENGTH_M, C.PITCH_WIDTH_M], venue=C.VENUE,
                injuries=[dict(team_id=t, player_id=p, severity=s, match_id=m) for t, p, s, m in (state.injury_log if state else [])],
                rules=dict(suspension_two_yellows=1, suspension_second_yellow=1, suspension_straight_red=2,
                           minor_injury_matches_missed=1, major_injury="rest of tournament", squad_size=23,
                           substitutions="5 per match in at most 3 windows", eligibility_born_from=C.ELIGIBLE_BORN_FROM),
                note="All teams, players and events are fictional and synthetic.")
    with open(os.path.join(out_dir, "generation_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
