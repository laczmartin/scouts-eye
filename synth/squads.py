"""Teams, players and hidden ground-truth abilities."""

import datetime as dt
import random

from . import config as C
from .names import FIRST_NAMES, LAST_NAMES, TEAMS


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def generate_teams():
    teams = []
    for team_id, name, city in TEAMS:
        p = C.TEAM_PROFILES[team_id]
        teams.append(dict(team_id=team_id, team_name=name, city=city, **p))
    return teams


def _birth_date(rng, year):
    """Birth date in `year` with months skewed to Q1 (relative age effect)."""
    quarter = rng.choices([1, 2, 3, 4], weights=[35, 28, 22, 15])[0]
    month = (quarter - 1) * 3 + rng.randint(1, 3)
    day = rng.randint(1, 28)
    return dt.date(year, month, day)


def generate_players(rng, teams):
    """23 players per team.

    Age is year-based (tournament year minus birth year), as is customary in
    youth football. Eligibility: born on or after 2008-01-01 (U19). Most
    players are 18, then 17; at most two 16-year-olds per team and at most two
    15-year-olds in the whole tournament. One 15/16-year-old per team is the
    hidden gem (chosen in generate_abilities)."""
    start = dt.date.fromisoformat(C.TOURNAMENT_START)
    players = []
    used_names = set()
    # which teams get a 15-year-old gem (2 teams) vs a 16-year-old gem (2 teams)
    gem_years = {t["team_id"]: 2010 for t in teams}  # 16
    for tid in rng.sample([t["team_id"] for t in teams], 2):
        gem_years[tid] = 2011  # 15
    for team in teams:
        tid = team["team_id"]
        formation = C.FORMATIONS[team["formation"]]
        slots_by_group = {}
        for detail, group, _, _ in formation:
            slots_by_group.setdefault(group, []).append(detail)
        idx = 0
        team_players = []
        for group, count in C.SQUAD_COMPOSITION[tid].items():
            details = slots_by_group.get(group, [])
            default_detail = {"GK": "GK", "CB": "CB", "FB": "RB", "DM": "DM", "CM": "CM",
                              "AM": "AM", "W": "RW", "ST": "ST"}[group]
            for k in range(count):
                idx += 1
                while True:
                    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                    if name not in used_names:
                        used_names.add(name)
                        break
                year = rng.choices(list(C.AGE_YEAR_WEIGHTS), weights=list(C.AGE_YEAR_WEIGHTS.values()))[0]
                foot = rng.choices(["right", "left", "both"], weights=[75, 22, 3])[0]
                if group == "FB" and k % 2 == 0:
                    foot = "left" if rng.random() < 0.7 else foot
                detail = details[k % len(details)] if details else default_detail
                if group == "FB" and foot == "left" and detail.startswith("R"):
                    detail = "L" + detail[1:]
                team_players.append(dict(
                    player_id=f"{tid}P{idx:02d}", team_id=tid, name=name, birth_year=year,
                    position_group=group, position_detail=detail, preferred_foot=foot,
                ))
        for p in team_players:
            p["primary_position"] = p["position_group"]
            p["secondary_position"] = ""
        _assign_hybrids(rng, tid, team_players)
        # young players: the gem (15 or 16) plus, in ~half of the teams, one more 16-year-old
        outfield = [p for p in team_players if p["position_group"] != "GK"]
        gem = rng.choice([p for p in outfield if p["position_group"] in ("CM", "AM", "W", "ST", "FB", "DM")])
        gem["birth_year"] = gem_years[tid]
        gem["_gem"] = True
        if rng.random() < 0.5:
            other = rng.choice([p for p in outfield if p is not gem])
            other["birth_year"] = 2010
        for p in team_players:
            bd = _birth_date(rng, p["birth_year"])
            p["birth_date"] = bd.isoformat()
            p["age"] = start.year - bd.year
            height = int(round(rng.gauss(C.POSITION_HEIGHT_MEAN[p["position_group"]], 5.5)))
            p["height_cm"] = height - max(0, 17 - p["age"]) * 2
            del p["birth_year"]
        # shirt numbers: GKs get 1/12/23, others random from the rest
        gk_numbers = [1, 12, 23]
        others = [n for n in range(1, 24) if n not in gk_numbers]
        rng.shuffle(others)
        gk_i = 0
        for p in team_players:
            if p["position_group"] == "GK":
                p["shirt_number"] = gk_numbers[gk_i]
                gk_i += 1
            else:
                p["shirt_number"] = others.pop()
        players.extend(team_players)
    return players


def _assign_hybrids(rng, tid, team_players):
    """2-4 multi-positional players per team: 1 defensive, 1 midfield and 1-2
    attacking hybrids, using only pairings where both positions exist as
    slots in the team's formation (so the player can actually be used in both).
    In T3 (3-5-2) no wing-back is a hybrid and there are no winger slots, so
    T3 gets a second defensive hybrid instead of an attacking one."""
    formation = C.FORMATIONS[C.TEAM_PROFILES[tid]["formation"]]
    slot_groups = {g for _, g, _, _ in formation}

    def pick(kind, exclude_primary=()):
        pairs = [pr for pr in C.HYBRID_PAIRS[kind]
                 if pr[0] in slot_groups and pr[1] in slot_groups and pr[0] not in exclude_primary and pr[1] not in exclude_primary]
        rng.shuffle(pairs)
        for prim, sec in pairs:
            cands = [p for p in team_players if p["primary_position"] == prim and not p["secondary_position"]]
            if cands:
                p = rng.choice(cands)
                p["secondary_position"] = sec
                return p
        return None
    n = 0
    if tid == "T3":
        n += pick("defensive", exclude_primary=("FB",)) is not None   # wing-backs are never hybrids in T3
        n += pick("midfield") is not None
        n += pick("defensive", exclude_primary=("FB",)) is not None
    else:
        n += pick("defensive") is not None
        n += pick("midfield") is not None
        n += pick("attacking") is not None
        if n < 3 or rng.random() < 0.5:
            pick("attacking")


def generate_abilities(rng, teams, players):
    """Hidden 0-100 abilities. Depend on team strength, position and age, with
    large individual spread. 2 older standouts + 1 young gem per team."""
    team_strength = {t["team_id"]: t["strength"] for t in teams}
    abilities = {}
    for p in players:
        base = C.POSITION_ABILITY_MEANS[p["position_group"]]
        team_adj = (team_strength[p["team_id"]] - 68) * 0.55
        age_adj = (p["age"] - 17.5) * 1.6
        player_noise = rng.gauss(0, 5.0)  # overall talent level of the player
        vals = {}
        for name, mean in zip(C.ABILITY_NAMES, base):
            v = mean + team_adj + age_adj + player_noise + rng.gauss(0, 6.5)
            if name == "stamina":
                v += (p["age"] - 17.5) * 1.2
            vals[name] = int(round(_clamp(v, 5, 99)))
        abilities[p["player_id"]] = vals
    # multi-positional players: a small penalty on the key abilities of the secondary position
    secondary = {}
    for p in players:
        if p.get("secondary_position"):
            pen = rng.randint(*C.SECONDARY_PENALTY)
            secondary[p["player_id"]] = dict(position=p["secondary_position"], penalty=pen,
                                              key_abilities=_key_abilities(p["secondary_position"]))
    abilities["_secondary"] = secondary

    # squad roles: rank within team & position group by mean ability
    for t in teams:
        tid = t["team_id"]
        formation = C.FORMATIONS[t["formation"]]
        need = {}
        for _, group, _, _ in formation:
            need[group] = need.get(group, 0) + 1
        tp = [p for p in players if p["team_id"] == tid]
        by_group = {}
        for p in tp:
            by_group.setdefault(p["position_group"], []).append(p)
        for group, lst in by_group.items():
            lst.sort(key=lambda p: -sum(abilities[p["player_id"]].values()))
            if group == "W" and tid == "T3":
                continue
            n_start = need.get(group, 0)
            for i, p in enumerate(lst):
                if i < n_start:
                    p["squad_role"] = "starter"
                elif i < n_start + (2 if group in ("CB", "CM", "W", "FB") else 1):
                    p["squad_role"] = "rotation"
                else:
                    p["squad_role"] = "fringe"

    # standouts: 2 older standouts + the young hidden gem per team
    standouts = []
    for t in teams:
        tid = t["team_id"]
        tp = [p for p in players if p["team_id"] == tid and p["position_group"] != "GK"]
        gem = [p for p in tp if p.get("_gem")][0]
        older = [p for p in tp if p["age"] >= 17]
        picks = [gem] + rng.sample(older, 2)
        for p in picks:
            key = _key_abilities(p["position_group"])
            for name in C.ABILITY_NAMES:
                bump = 12 if name in key else 6
                if name == "finishing":
                    bump = min(bump, 4)  # keep goal tallies realistic
                abilities[p["player_id"]][name] = int(_clamp(abilities[p["player_id"]][name] + bump, 5, 99))
        # the gem is a rotation player: good enough to play, not an automatic starter
        gem["squad_role"] = "rotation"
        standouts.append((tid, gem["player_id"], [x["player_id"] for x in picks[1:]]))
    # every gem must be a top-3 talent of his position by the ground-truth composite (all four teams)
    for tid, gem_id, _ in standouts:
        gem = next(p for p in players if p["player_id"] == gem_id)
        while gem_composite_rank(gem, players, abilities) > 3:
            for name in C.ABILITY_NAMES:
                abilities[gem_id][name] = int(_clamp(abilities[gem_id][name] + (2 if name in C.GT_COMPOSITE[gem["position_group"]] else 1), 5, 99))
    for p in players:
        p.pop("_gem", None)
    return abilities, standouts


def composite(ab, pos):
    return sum(ab[a] for a in C.GT_COMPOSITE[pos]) / len(C.GT_COMPOSITE[pos])


def gem_composite_rank(gem, players, abilities):
    pos = gem["position_group"]
    group = [p for p in players if p["position_group"] == pos]
    scores = sorted((composite(abilities[p["player_id"]], pos) for p in group), reverse=True)
    return scores.index(composite(abilities[gem["player_id"]], pos)) + 1


def _key_abilities(group):
    return {
        "GK": ["positioning", "decision_making"],
        "CB": ["aerial", "tackling", "positioning"],
        "FB": ["pace", "tackling", "ball_carrying"],
        "DM": ["tackling", "passing", "positioning"],
        "CM": ["passing", "decision_making", "stamina"],
        "AM": ["passing", "ball_carrying", "decision_making"],
        "W": ["ball_carrying", "pace", "finishing"],
        "ST": ["finishing", "positioning", "aerial"],
    }[group]
