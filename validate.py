#!/usr/bin/env python3
"""Validate the synthetic dataset and write validation_report.md.

Checks (data consistency plus tournament rules):
  * consistency: scores vs goal events, players on pitch, lineup minutes vs
    substitutions, unique event ids, monotonic timestamps, coordinates in pitch;
  * rules: suspended / injured players do not play (recomputed from card and
    injury events), ten men after a red card, 5 substitutions in at most 3
    windows, rotation (only the goalkeeper and centre-backs may play every
    minute), age composition, top scorer at most 7 goals, hidden gem minutes;
  * realism: published benchmarks only (benchmarks.py, public sources), OK/WARN
    with a 12-match band of one standard error; every other metric is reported
    as a descriptive statistic without a target;
  * tournament summary: table, top scorers, minutes, ages, birth quarters,
    absences, ten-men spells.

This script reads ground_truth_abilities.csv only to identify the hidden gems
for the minutes check; no metric is derived from the hidden abilities.
"""

import argparse
import collections
import csv
import json
import os
import statistics

POSSESSION_TEAM = "T4"  # the Danish-like possession profile (see teams.csv style_possession)


# ------------------------------------------------------------------ loading
def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(data_dir):
    d = {}
    d["teams"] = read_csv(os.path.join(data_dir, "teams.csv"))
    d["players"] = read_csv(os.path.join(data_dir, "players.csv"))
    d["matches"] = read_csv(os.path.join(data_dir, "matches.csv"))
    d["lineups"] = read_csv(os.path.join(data_dir, "lineups.csv"))
    d["physical"] = read_csv(os.path.join(data_dir, "physical_snapshots.csv"))
    d["events"] = {}
    for m in d["matches"]:
        path = os.path.join(data_dir, "events", f"{m['match_id']}.jsonl")
        with open(path, encoding="utf-8") as f:
            d["events"][m["match_id"]] = [json.loads(line) for line in f if line.strip()]
    return d


# ------------------------------------------------------------- consistency
def consistency_checks(d):
    results = []  # (name, passed, detail)

    # 1. scores equal goal events
    bad = []
    for m in d["matches"]:
        evs = d["events"][m["match_id"]]
        gh = sum(1 for e in evs if e["type"] == "shot" and e["outcome"] == "goal" and e["team_id"] == m["home_team_id"])
        ga = sum(1 for e in evs if e["type"] == "shot" and e["outcome"] == "goal" and e["team_id"] == m["away_team_id"])
        if (gh, ga) != (int(m["home_score"]), int(m["away_score"])):
            bad.append(f"{m['match_id']}: csv {m['home_score']}-{m['away_score']} vs events {gh}-{ga}")
    results.append(("Scores in matches.csv equal goal events", not bad, "; ".join(bad) or "all 12 matches match"))

    # 2. every event's player was on the pitch
    on_pitch = collections.defaultdict(list)
    for lu in d["lineups"]:
        if lu["on_ms"] != "":
            on_pitch[(lu["match_id"], lu["player_id"])].append((int(lu["on_ms"]), int(lu["off_ms"])))
    d["on_pitch"] = on_pitch
    bad, n = [], 0
    for mid, evs in d["events"].items():
        for e in evs:
            if e["player_id"] is None:
                continue
            n += 1
            ok = any(a <= e["timestamp_ms"] <= b for a, b in on_pitch.get((mid, e["player_id"]), []))
            if not ok:
                bad.append(f"{e['event_id']} {e['player_id']} at {e['timestamp_ms']}")
            if e.get("sub_player_in_id"):
                ok2 = any(a == e["timestamp_ms"] for a, b in on_pitch.get((mid, e["sub_player_in_id"]), []))
                if not ok2:
                    bad.append(f"{e['event_id']} sub-in {e['sub_player_in_id']}")
    results.append(("Every event's player was on the pitch", not bad, f"{n} player events checked" + (f"; first problems: {bad[:3]}" if bad else "")))

    # 3. lineup minutes match substitution events
    bad = []
    subs_per_team = collections.Counter()
    for mid, evs in d["events"].items():
        for e in evs:
            if e["type"] != "substitution":
                continue
            subs_per_team[(mid, e["team_id"])] += 1
            out_iv = on_pitch.get((mid, e["player_id"]), [])
            in_iv = on_pitch.get((mid, e["sub_player_in_id"]), [])
            if not any(b == e["timestamp_ms"] for a, b in out_iv):
                bad.append(f"{e['event_id']}: outgoing {e['player_id']} off_ms mismatch")
            if not any(a == e["timestamp_ms"] for a, b in in_iv):
                bad.append(f"{e['event_id']}: incoming {e['sub_player_in_id']} on_ms mismatch")
    for lu in d["lineups"]:
        if lu["on_ms"] == "":
            if float(lu["minutes_played"]) != 0 or lu["status"] not in ("rotated", "suspended", "injured"):
                bad.append(f"{lu['match_id']} {lu['player_id']} absent row inconsistent")
            continue
        expected = round((int(lu["off_ms"]) - int(lu["on_ms"])) / 60000.0, 1)
        if abs(float(lu["minutes_played"]) - expected) > 0.11:
            bad.append(f"{lu['match_id']} {lu['player_id']} minutes {lu['minutes_played']} vs {expected}")
    too_many = [k for k, v in subs_per_team.items() if v > 5]
    if too_many:
        bad.append(f"more than 5 substitutions: {too_many}")
    # lineups: exactly 11 starters per team per match
    starters = collections.Counter((lu["match_id"], lu["team_id"]) for lu in d["lineups"] if lu["status"] == "started")
    if any(v != 11 for v in starters.values()):
        bad.append("a team does not have 11 starters")
    results.append(("Lineup minutes match substitution events", not bad, f"{sum(subs_per_team.values())} substitutions checked" + (f"; {bad[:3]}" if bad else "")))

    # 4. unique event ids
    ids = [e["event_id"] for evs in d["events"].values() for e in evs]
    dup = len(ids) - len(set(ids))
    results.append(("No duplicate event_ids", dup == 0, f"{len(ids)} events, {dup} duplicates"))

    # 5. timestamps increasing within each match
    bad = []
    for mid, evs in d["events"].items():
        for a, b in zip(evs, evs[1:]):
            if b["timestamp_ms"] < a["timestamp_ms"]:
                bad.append(f"{b['event_id']}")
                break
    results.append(("Timestamps non-decreasing within each match", not bad, "; ".join(bad) or "ok"))

    # 6. coordinates inside the pitch
    bad = 0
    for evs in d["events"].values():
        for e in evs:
            for k in ("x", "y", "end_x", "end_y"):
                v = e.get(k)
                if v is not None and not (0 <= v <= 100):
                    bad += 1
    results.append(("Coordinates inside the pitch (0-100)", bad == 0, f"{bad} out-of-pitch coordinates"))
    # 6b. penalties are flagged explicitly and consistently (flag <=> shot from the spot after a penalty free kick)
    bad, n_pen = [], 0
    for mid, evs in d["events"].items():
        prev = None
        for e in evs:
            if e["type"] == "shot":
                flagged = bool(e.get("is_penalty"))
                from_spot = prev is not None and prev["type"] == "free_kick" and prev.get("is_penalty") and prev["player_id"] == e["player_id"]
                if flagged != from_spot:
                    bad.append(e["event_id"])
                n_pen += flagged
            if e["type"] not in ("pressure",):
                prev = e
    results.append(("Penalties flagged explicitly (is_penalty) and consistently", not bad, f"{n_pen} penalties" + (f"; inconsistent: {bad[:3]}" if bad else "")))
    results.extend(rule_checks(d))
    return results


def expected_absences(d):
    """Recompute suspensions and injury absences from events, applying the rules:
    2 accumulated yellows = 1 match, second yellow = 1 match, straight red = 2,
    minor injury = next match missed, major injury = rest of the tournament."""
    matches = sorted(d["matches"], key=lambda m: m["match_id"])
    yellows, bans, injured_until = {}, {}, {}
    expected = {}  # (match_id, player_id) -> reason
    for m in matches:
        mid = m["match_id"]
        md = int(m["matchday"])
        teams = (m["home_team_id"], m["away_team_id"])
        for p in d["players"]:
            if p["team_id"] not in teams:
                continue
            pid = p["player_id"]
            if bans.get(pid, 0) > 0:
                expected[(mid, pid)] = "suspended"
            elif pid in injured_until and (injured_until[pid] is None or md <= injured_until[pid]):
                expected[(mid, pid)] = "injured"
        # serve bans for the teams that played
        for pid in list(bans):
            if pid[:2] in teams and bans[pid] > 0:
                bans[pid] -= 1
        for e in d["events"][mid]:
            if e["type"] == "card":
                pid = e["player_id"]
                if e["card_type"] == "yellow":
                    yellows[pid] = yellows.get(pid, 0) + 1
                elif e["card_type"] == "second_yellow":
                    yellows[pid] = max(0, yellows.get(pid, 0) - 1)
                    bans[pid] = bans.get(pid, 0) + 1
                elif e["card_type"] == "straight_red":
                    bans[pid] = bans.get(pid, 0) + 2
            elif e["type"] == "injury":
                injured_until[e["player_id"]] = None if e["outcome"] == "major" else md + 1
        for pid, n in list(yellows.items()):
            if n >= 2:
                yellows[pid] = 0
                bans[pid] = bans.get(pid, 0) + 1
    return expected


def rule_checks(d):
    results = []
    lineup_by = {(lu["match_id"], lu["player_id"]): lu for lu in d["lineups"]}
    on_pitch = d["on_pitch"]

    # 7. suspended / injured players do not play, and the reasons in lineups.csv match the rules
    expected = expected_absences(d)
    bad = []
    for (mid, pid), reason in expected.items():
        lu = lineup_by.get((mid, pid))
        if lu is None or lu["status"] != reason:
            bad.append(f"{mid} {pid}: expected {reason}, lineups says {lu['status'] if lu else 'missing'}")
        if on_pitch.get((mid, pid)):
            bad.append(f"{mid} {pid}: {reason} but played")
    for lu in d["lineups"]:
        if lu["status"] in ("suspended", "injured") and (lu["match_id"], lu["player_id"]) not in expected:
            bad.append(f"{lu['match_id']} {lu['player_id']}: marked {lu['status']} without a rule reason")
    n_susp = sum(1 for r in expected.values() if r == "suspended")
    n_inj = sum(1 for r in expected.values() if r == "injured")
    results.append(("Suspended / injured players do not play (recomputed from cards and injuries)", not bad,
                    f"{n_susp} suspension and {n_inj} injury absences expected; " + ("all match lineups.csv" if not bad else str(bad[:3]))))

    # 8. every squad player has a lineup row per match of their team (23 per team)
    counts = collections.Counter((lu["match_id"], lu["team_id"]) for lu in d["lineups"])
    bad = [k for k, v in counts.items() if v != 23]
    results.append(("Every squad player has one lineups.csv row per match (23 per team)", not bad, f"{len(counts)} team-matches checked"))

    # 9. ten men after a red card: the number of players on the pitch drops to 10 and stays there
    bad, spells = [], []
    for m in d["matches"]:
        mid = m["match_id"]
        for e in d["events"][mid]:
            if e["type"] == "card" and e["outcome"] == "red":
                t_red = e["timestamp_ms"]
                end = int(m["duration_ms"])
                probe = min(end - 1, t_red + 60000)
                n_on = sum(1 for (mm, pid), ivs in on_pitch.items() if mm == mid and pid[:2] == e["team_id"]
                           and any(a <= probe < b for a, b in ivs))
                if n_on > 10:
                    bad.append(f"{mid} {e['player_id']}: {n_on} players on pitch after red card")
                spells.append((mid, e["team_id"], e["player_id"], e["minute"], round((end - t_red) / 60000.0)))
    d["red_spells"] = spells
    results.append(("Team plays with ten men after a red card", not bad, f"{len(spells)} sending-offs checked" + (f"; {bad}" if bad else "")))

    # 10. substitutions: at most 5 per team per match, in at most 3 windows (same timestamp = one window)
    bad = []
    for m in d["matches"]:
        mid = m["match_id"]
        for tid in (m["home_team_id"], m["away_team_id"]):
            subs = [e for e in d["events"][mid] if e["type"] == "substitution" and e["team_id"] == tid]
            windows = len(set(e["timestamp_ms"] for e in subs))
            if len(subs) > 5 or windows > 3:
                bad.append(f"{mid} {tid}: {len(subs)} subs in {windows} windows")
    all_subs = [e for evs in d["events"].values() for e in evs if e["type"] == "substitution"]
    results.append(("At most 5 substitutions in at most 3 windows per team per match", not bad,
                    f"{len(all_subs)} substitutions, {len(all_subs) / 24:.1f} per team-match" + (f"; {bad[:3]}" if bad else "")))

    # 11. rotation: only the goalkeeper and centre-backs may play every minute of every match
    pbi = {p["player_id"]: p for p in d["players"]}
    full = collections.Counter()
    played = collections.Counter()
    for lu in d["lineups"]:
        if lu["on_ms"] == "":
            continue
        played[lu["player_id"]] += 1
        m = next(x for x in d["matches"] if x["match_id"] == lu["match_id"])
        if int(lu["on_ms"]) == 0 and int(lu["off_ms"]) >= int(m["duration_ms"]):
            full[lu["player_id"]] += 1
    bad = [pid for pid, n in full.items() if n == 6 and pbi[pid]["position_group"] not in ("GK", "CB")]
    ever_full = sorted(pid for pid, n in full.items() if n == 6)
    results.append(("Rotation: only GK / CB play every minute of all six matches", not bad,
                    f"players with 6 full matches: {', '.join(ever_full) or 'none'}" + (f"; violations {bad}" if bad else "")))

    # 12. age composition
    bad = []
    born_from = "2008-01-01"
    too_old = [p["player_id"] for p in d["players"] if p["birth_date"] < born_from]
    if too_old:
        bad.append(f"born before {born_from}: {too_old}")
    ages = collections.Counter(int(p["age"]) for p in d["players"])
    if ages[18] <= len(d["players"]) / 2:
        bad.append(f"18-year-olds are not the majority ({ages[18]})")
    if ages[15] > 2:
        bad.append(f"{ages[15]} fifteen-year-olds (max 2)")
    per_team16 = collections.Counter(p["team_id"] for p in d["players"] if int(p["age"]) == 16)
    if any(n > 2 for n in per_team16.values()):
        bad.append(f"more than two 16-year-olds in a team: {dict(per_team16)}")
    results.append(("Age composition (U19: born >= 2008-01-01; majority 18; <= 2 aged 15; <= 2 aged 16 per team)", not bad,
                    f"ages {dict(sorted(ages.items()))}, 16-year-olds per team {dict(sorted(per_team16.items()))}" + (f"; {bad}" if bad else "")))

    # 13. top scorer at most 7 goals
    goals = collections.Counter(e["player_id"] for evs in d["events"].values() for e in evs if e["type"] == "shot" and e["outcome"] == "goal")
    top_pid, top_n = goals.most_common(1)[0]
    results.append(("Top scorer has 4-6 goals", 4 <= top_n <= 6, f"{pbi[top_pid]['name']} ({top_pid}) {top_n} goals"))

    # 14. hidden gem minutes (youngest standout per team, aged 15-16, rotation role): about 150-250 minutes
    mins = collections.Counter()
    for lu in d["lineups"]:
        mins[lu["player_id"]] += float(lu["minutes_played"])
    # The gem's identity comes from ground_truth_abilities.csv (standout = young_gem).
    # This is the only place the validator touches the hidden file, and only for this check.
    gems = []
    gt_path = os.path.join(d["dir"], "ground_truth_abilities.csv")
    gem_ids = [r["player_id"] for r in read_csv(gt_path) if r["standout"] == "young_gem"]
    for pid in sorted(gem_ids):
        gems.append((pid[:2], pid, pbi[pid]["age"], mins[pid]))
    bad = [g for g in gems if not (180 <= g[3] <= 290)]
    results.append(("Young hidden gem (15-16) plays at least 180 minutes (180-290) per team", not bad,
                    "; ".join(f"{t} {pid} (age {a}) {m:.0f} min" for t, pid, a, m in gems)))
    d["gems"] = gems
    results.extend(squad_checks(d))
    return results


# squad design: composition per team (23 players)
SQUAD_COMPOSITION = {
    "T1": {"GK": 3, "CB": 4, "FB": 4, "DM": 2, "CM": 4, "AM": 0, "W": 4, "ST": 2},
    "T2": {"GK": 3, "CB": 4, "FB": 4, "DM": 4, "CM": 0, "AM": 3, "W": 3, "ST": 2},
    "T3": {"GK": 3, "CB": 5, "FB": 4, "DM": 2, "CM": 5, "AM": 0, "W": 0, "ST": 4},
    "T4": {"GK": 3, "CB": 4, "FB": 4, "DM": 0, "CM": 5, "AM": 0, "W": 4, "ST": 3},
}
FORMATION_SLOTS = {"4-3-3": {"GK", "FB", "CB", "DM", "CM", "W", "ST"}, "4-2-3-1": {"GK", "FB", "CB", "DM", "W", "AM", "ST"},
                   "4-4-2": {"GK", "FB", "CB", "CM", "W", "ST"}, "3-5-2": {"GK", "CB", "FB", "DM", "CM", "ST"}}
HYBRID_PAIRS = {("CB", "FB"), ("CB", "DM"), ("CM", "DM"), ("AM", "W"), ("W", "FB"), ("W", "ST")}


def squad_checks(d):
    results = []
    pbi = {p["player_id"]: p for p in d["players"]}
    # 15. squad composition equals the squad design table
    bad = []
    comp = {}
    for tid, expected in SQUAD_COMPOSITION.items():
        actual = collections.Counter(p["primary_position"] for p in d["players"] if p["team_id"] == tid)
        comp[tid] = actual
        for g, n in expected.items():
            if actual.get(g, 0) != n:
                bad.append(f"{tid} {g}: {actual.get(g, 0)} vs {n}")
    totals = collections.Counter(p["primary_position"] for p in d["players"])
    if totals["ST"] < 9:
        bad.append(f"totals ST={totals['ST']} (min 9)")
    formation_of = {t["team_id"]: t["formation"] for t in d["teams"]}
    for p in d["players"]:
        if p["primary_position"] not in FORMATION_SLOTS[formation_of[p["team_id"]]]:
            bad.append(f"{p['player_id']} primary {p['primary_position']} has no slot in {formation_of[p['team_id']]}")
    d["composition"] = comp
    results.append(("Squad composition per team equals the squad design table; every primary position exists in the formation (3 GK, >= 9 ST)", not bad,
                    f"ST {totals['ST']}, 23 players per team" + (f"; {bad[:3]}" if bad else "")))

    # 16. 2-4 multi-positional players per team with realistic pairings
    hybrids = [p for p in d["players"] if p["secondary_position"]]
    per_team = collections.Counter(p["team_id"] for p in hybrids)
    bad = [f"{tid}: {n}" for tid, n in per_team.items() if not 2 <= n <= 4]
    bad += [f"{tid}: none" for tid in SQUAD_COMPOSITION if tid not in per_team]
    for p in hybrids:
        pair = (p["primary_position"], p["secondary_position"])
        if pair not in HYBRID_PAIRS and pair[::-1] not in HYBRID_PAIRS:
            bad.append(f"{p['player_id']} unrealistic pairing {pair}")
    results.append(("2-4 multi-positional players per team with realistic pairings", not bad,
                    ", ".join(f"{tid} {per_team[tid]}" for tid in sorted(per_team)) + (f"; {bad}" if bad else "")))

    # 17. each hybrid played both positions at least once (unless unavailable or the formation has no such slot)
    played = collections.defaultdict(lambda: collections.defaultdict(list))  # pid -> group -> [match ids]
    for lu in d["lineups"]:
        if lu["position_group_played"]:
            played[lu["player_id"]][lu["position_group_played"]].append(lu["match_id"])
    formation_of = {t["team_id"]: t["formation"] for t in d["teams"]}
    rows, bad, notes = [], [], []
    for p in sorted(hybrids, key=lambda p: p["player_id"]):
        pid = p["player_id"]
        prim, sec = p["primary_position"], p["secondary_position"]
        groups = played[pid]
        extra = sorted(g for g in groups if g not in (prim, sec))
        slots = FORMATION_SLOTS[formation_of[p["team_id"]]]
        if prim not in slots or sec not in slots:
            status = f"position without a slot in {formation_of[p['team_id']]}"
            bad.append(f"{pid}: {status}")
        elif p["team_id"] == "T3" and prim == "FB":
            status = "T3 wing-back must not be a hybrid"
            bad.append(f"{pid}: {status}")
        elif prim in groups and sec in groups:
            status = "both positions played"
        else:
            avail = sum(1 for lu in d["lineups"] if lu["player_id"] == pid and lu["status"] in ("started", "sub_in", "rotated"))
            missing = [g for g in (prim, sec) if g not in groups]
            status = f"missing {missing} (available in {avail} matches)"
            if avail <= 3:
                notes.append(f"{pid}: {status} - unavailable most of the tournament, reported")
            else:
                bad.append(f"{pid}: {status}")
        rows.append((pid, p["name"], p["team_id"], prim, sec,
                     "; ".join(f"{g}: {', '.join(ms)}" for g, ms in sorted(groups.items())), status + (f"; emergency cover at {extra}" if extra else "")))
    d["hybrid_rows"] = rows
    results.append(("Every multi-positional player has both positions in his formation and played both at least once", not bad,
                    f"{len(hybrids)} hybrids; " + ("all played both positions" if not (bad or notes) else "") + (f"reported: {'; '.join(notes)}" if notes else "") + (f"; violations: {bad}" if bad else "")))

    # 18. no position change within a match: one lineup row and one position per player per match
    bad = []
    seen = collections.Counter((lu["match_id"], lu["player_id"]) for lu in d["lineups"])
    bad += [f"{k}" for k, n in seen.items() if n != 1]
    for lu in d["lineups"]:
        if lu["on_ms"] != "" and not lu["position_group_played"]:
            bad.append(f"{lu['match_id']} {lu['player_id']} played without a position")
    subs_wrong = 0
    for mid, evs in d["events"].items():
        lu_by = {lu["player_id"]: lu for lu in d["lineups"] if lu["match_id"] == mid}
        for e in evs:
            if e["type"] == "substitution":
                if lu_by[e["player_id"]]["position_detail"] != lu_by[e["sub_player_in_id"]]["position_detail"]:
                    subs_wrong += 1
    if subs_wrong:
        bad.append(f"{subs_wrong} substitutes entered in a different slot than the player they replaced")
    results.append(("No position change within a match (one position per player per match; substitutes take the vacated slot)", not bad,
                    f"{len(seen)} player-matches checked" + (f"; {bad[:3]}" if bad else "")))
    return results


# ------------------------------------------------------------------ metrics
def is_def_action(e):
    return e["type"] in ("tackle", "interception", "foul") or (e["type"] == "ground_duel" and e.get("duel_role") == "defensive")


def team_match_metrics(evs, tid):
    """Per team per match metrics using common event-data definitions (see README)."""
    te = [e for e in evs if e["team_id"] == tid]
    oe = [e for e in evs if e["team_id"] not in (tid, None)]
    passes = [e for e in te if e["type"] == "pass"]
    longp = [e for e in passes if e["pass_length_m"] is not None and e["pass_length_m"] > 30]
    shots = [e for e in te if e["type"] == "shot"]
    dd = [e for e in te if e["type"] == "tackle" or (e["type"] == "ground_duel" and e.get("duel_role") == "defensive")]
    aer = [e for e in te if e["type"] == "aerial_duel"]
    opp_passes_own_half = sum(1 for e in oe if e["type"] == "pass" and e["x"] < 50)
    def_actions_opp_half = sum(1 for e in te if is_def_action(e) and e["x"] > 50)
    on_ball = sum(1 for e in te if e["type"] in ("pass", "carry", "dribble", "shot"))
    on_ball_opp = sum(1 for e in oe if e["type"] in ("pass", "carry", "dribble", "shot"))
    pct = lambda n, d: (100.0 * n / d) if d else 0.0
    return dict(
        passes=len(passes),
        pass_accuracy=pct(sum(e["outcome"] == "success" for e in passes), len(passes)),
        long_passes=len(longp),
        long_pass_accuracy=pct(sum(e["outcome"] == "success" for e in longp), len(longp)),
        shots=len(shots),
        shots_on_target_pct=pct(sum(e["outcome"] in ("goal", "saved") for e in shots), len(shots)),
        xg=sum(e["xg"] for e in shots),
        goals=sum(e["outcome"] == "goal" for e in shots),
        defensive_duels=len(dd),
        defensive_duels_won_pct=pct(sum(e["outcome"] == "success" for e in dd), len(dd)),
        aerial_duels=len(aer),
        aerial_duels_won_pct=pct(sum(e["outcome"] == "success" for e in aer), len(aer)),
        interceptions=sum(e["type"] == "interception" for e in te),
        ppda=(opp_passes_own_half / def_actions_opp_half) if def_actions_opp_half else 0.0,
        corners=sum(e["type"] == "corner" for e in te),
        fouls=sum(e["type"] == "foul" for e in te),
        yellow_cards=sum(e["type"] == "card" and e.get("card_type") == "yellow" for e in te),
        possession_pct=pct(on_ball, on_ball + on_ball_opp),
    )


def match_metrics(evs):
    shots = [e for e in evs if e["type"] == "shot"]
    return dict(
        total_events=len(evs),
        passes=sum(e["type"] == "pass" for e in evs),
        goals=sum(e["outcome"] == "goal" for e in shots),
        shots=len(shots),
        xg=sum(e["xg"] for e in shots),
        mean_xg_per_shot=(sum(e["xg"] for e in shots) / len(shots)) if shots else 0.0,
        ground_duel_contests=sum(e["type"] in ("tackle", "dribble") for e in evs),
        aerial_duel_contests=sum(e["type"] == "aerial_duel" for e in evs) / 2.0,
        pressures=sum(e["type"] == "pressure" for e in evs),
    )


def mean(xs):
    return statistics.fmean(xs) if xs else 0.0


def realism_rows(d):
    """Published benchmarks (OK / WARN) and descriptive statistics (no external target).

    Returns (bench_rows, desc_rows, per_team, dist_by, hsr_by):
      bench_rows: (section, metric, actual, published benchmark, 12-match band, status, source id)
      desc_rows:  (section, metric, actual)
    Benchmarks come only from benchmarks.py (public, published sources). For a tournament
    mean the band is the benchmark widened by one standard error of that mean, computed from
    the synthetic matches themselves (12 matches or 24 team-matches)."""
    import benchmarks as B
    bench, desc = [], []
    per_team = collections.defaultdict(list)  # kind -> list of metric dicts
    per_match = []
    poss_splits = []
    for m in d["matches"]:
        evs = d["events"][m["match_id"]]
        per_match.append(match_metrics(evs))
        for tid in (m["home_team_id"], m["away_team_id"]):
            tm = team_match_metrics(evs, tid)
            per_team["possession" if tid == POSSESSION_TEAM else "direct"].append(tm)
            per_team["all"].append(tm)
        poss_splits.append(team_match_metrics(evs, m["home_team_id"])["possession_pct"])

    def se(values):
        return statistics.stdev(values) / len(values) ** 0.5 if len(values) > 1 else 0.0

    def check(section, metric, values, lo, hi, source, fmt="{:.1f}", use_se=True):
        value = mean(values)
        tol = se(values) if use_se else 0.0
        ok = lo - tol <= value <= hi + tol
        band = f"{fmt.format(lo - tol)}–{fmt.format(hi + tol)}" if tol else "as benchmark"
        bench.append((section, metric, fmt.format(value), f"{fmt.format(lo)}–{fmt.format(hi)}", band, "OK" if ok else "WARN", source))

    def info(section, metric, value, fmt="{:.1f}"):
        desc.append((section, metric, fmt.format(value) if isinstance(value, (int, float)) else str(value)))

    def avg(kind, key):
        return mean([t[key] for t in per_team[kind]])

    # ---------------- published benchmarks
    check("Per match", "goals per match (tournament mean)", [x["goals"] for x in per_match], *B.GOALS_PER_MATCH, "uyl", "{:.2f}")
    check("Per team, per match", "passes (all teams)", [t["passes"] for t in per_team["all"]], *B.PASSES_PER_TEAM, "sramkova2024", "{:.0f}", use_se=False)

    # ---------------- descriptive statistics (no external target)
    s = "Per team, per match"
    for label, kind, key, fmt in [("passes (direct-style teams)", "direct", "passes", "{:.0f}"), ("passes (possession team)", "possession", "passes", "{:.0f}"),
                                  ("pass accuracy % (direct-style)", "direct", "pass_accuracy", "{:.1f}"), ("pass accuracy % (possession)", "possession", "pass_accuracy", "{:.1f}"),
                                  ("long passes (> 30 m)", "all", "long_passes", "{:.1f}"), ("long pass accuracy %", "all", "long_pass_accuracy", "{:.1f}"),
                                  ("shots", "all", "shots", "{:.1f}"), ("shots (possession team)", "possession", "shots", "{:.1f}"),
                                  ("shots on target %", "all", "shots_on_target_pct", "{:.1f}"), ("xG", "all", "xg", "{:.2f}"), ("goals", "all", "goals", "{:.2f}"),
                                  ("defensive duels", "all", "defensive_duels", "{:.1f}"), ("defensive duels won %", "all", "defensive_duels_won_pct", "{:.1f}"),
                                  ("aerial duels", "all", "aerial_duels", "{:.1f}"), ("aerial duels won %", "all", "aerial_duels_won_pct", "{:.1f}"),
                                  ("interceptions", "all", "interceptions", "{:.1f}"), ("PPDA (direct-style teams)", "direct", "ppda", "{:.2f}"),
                                  ("PPDA (possession team)", "possession", "ppda", "{:.2f}"), ("corners", "all", "corners", "{:.1f}"),
                                  ("fouls", "all", "fouls", "{:.1f}"), ("yellow cards", "all", "yellow_cards", "{:.2f}")]:
        info(s, label, avg(kind, key), fmt)
    s = "Per match, both teams"
    mm = lambda k: mean([x[k] for x in per_match])
    goals_list = [x["goals"] for x in per_match]
    draws = sum(1 for m in d["matches"] if m["home_score"] == m["away_score"])
    tot_goals, tot_xg = sum(goals_list), sum(x["xg"] for x in per_match)
    info(s, "total events", mm("total_events"), "{:.0f}")
    info(s, "passes", mm("passes"), "{:.0f}")
    info(s, "goals in a single match (min / max)", f"{min(goals_list)} / {max(goals_list)}")
    info(s, "draws across 12 matches", draws, "{:.0f}")
    info(s, "shots", mm("shots"))
    info(s, "mean xG per shot", mm("mean_xg_per_shot"), "{:.3f}")
    info(s, "goals / xG (tournament)", tot_goals / tot_xg if tot_xg else 0, "{:.2f}")
    info(s, "ground duel contests", mm("ground_duel_contests"), "{:.0f}")
    info(s, "aerial duel contests", mm("aerial_duel_contests"))
    info(s, "pressures", mm("pressures"), "{:.0f}")
    info(s, "possession split (most lopsided share, %)", max(max(poss_splits), 100 - min(poss_splits)), "{:.0f}")

    # ---------------- physical per 90 (outfield players with >= 60 minutes)
    s = "Physical (outfield, per 90)"
    pbi = {p["player_id"]: p for p in d["players"]}
    per_pm = collections.defaultdict(lambda: dict(dist=0.0, hsr=0.0, spr=0.0, top=0.0, mins=0.0))
    for r in d["physical"]:
        k = (r["match_id"], r["player_id"])
        a = per_pm[k]
        a["dist"] += float(r["distance_m"]); a["hsr"] += float(r["high_speed_distance_m"])
        a["spr"] += float(r["sprint_distance_m"]); a["mins"] += float(r["minutes_in_window"])
        a["top"] = max(a["top"], float(r["top_speed_kmh"]))
    by_group = collections.defaultdict(lambda: collections.defaultdict(list))
    for (mid, pid), a in per_pm.items():
        g = pbi[pid]["position_group"]
        if g == "GK" or a["mins"] < 60:
            continue
        f = 90.0 / a["mins"]
        for key, val in (("dist", a["dist"] * f / 1000.0), ("hsr", a["hsr"] * f), ("spr", a["spr"] * f), ("top", a["top"])):
            by_group[g][key].append(val)
            by_group["ALL"][key].append(val)
        by_group["young" if int(pbi[pid]["age"]) <= 16 else "older"]["top"].append(a["top"])
    check(s, "total distance km", by_group["ALL"]["dist"], *B.DISTANCE_KM_PER_90, "sportjournal_review", "{:.2f}", use_se=False)
    dist_by = {g: mean(by_group[g]["dist"]) for g in ("CB", "FB", "DM", "CM", "AM", "W", "ST") if by_group[g]["dist"]}
    hsr_by = {g: mean(by_group[g]["hsr"]) for g in ("CB", "FB", "DM", "CM", "AM", "W", "ST") if by_group[g]["hsr"]}
    top_d, top_h = max(dist_by, key=dist_by.get), max(hsr_by, key=hsr_by.get)
    bench.append((s, "position with the highest total distance", top_d, "CM", "as benchmark", "OK" if top_d in B.HIGHEST_DISTANCE_POSITIONS else "WARN", "causevic2025"))
    bench.append((s, f"position with the most high-speed running (≥ {B.HSR_THRESHOLD_KMH} km/h)", top_h, "FB or W", "as benchmark",
                  "OK" if top_h in B.HIGHEST_HSR_POSITIONS else "WARN", "causevic2025, unisr_u19"))
    info(s, f"high-speed running m (≥ {B.HSR_THRESHOLD_KMH} km/h)", mean(by_group["ALL"]["hsr"]), "{:.0f}")
    info(s, f"sprint distance m (≥ {B.SPRINT_THRESHOLD_KMH} km/h)", mean(by_group["ALL"]["spr"]), "{:.0f}")
    info(s, "top speed km/h (match max, mean over players)", mean(by_group["ALL"]["top"]))
    # fatigue across matches: fresh vs players who played >= 60 min three days earlier (internal model property)
    fresh, loaded = [], []
    by_match = collections.defaultdict(list)
    for lu in d["lineups"]:
        by_match[lu["match_id"]].append(lu)
    prev_minutes = {}
    for m in sorted(d["matches"], key=lambda x: x["match_id"]):
        for lu in by_match[m["match_id"]]:
            a = per_pm.get((m["match_id"], lu["player_id"]))
            if a and a["mins"] >= 60 and pbi[lu["player_id"]]["position_group"] != "GK":
                (loaded if prev_minutes.get(lu["player_id"], 0) >= 60 else fresh).append(a["dist"] * 90.0 / a["mins"] / 1000.0)
        for lu in by_match[m["match_id"]]:
            prev_minutes[lu["player_id"]] = float(lu["minutes_played"])
    d["fatigue_phys"] = (mean(fresh), mean(loaded), len(fresh), len(loaded))
    info(s, "distance km: fresh minus loaded players", mean(fresh) - mean(loaded), "{:.2f}")
    info(s, "top speed gap: age 17+ minus age 15–16 (km/h)", mean(by_group["older"]["top"]) - mean(by_group["young"]["top"]))
    return bench, desc, per_team, dist_by, hsr_by


# ---------------------------------------------------------------- summary
def standings(matches):
    tbl = collections.OrderedDict()
    for m in matches:
        for t in (m["home_team_id"], m["away_team_id"]):
            tbl.setdefault(t, dict(team_id=t, P=0, W=0, D=0, L=0, GF=0, GA=0, Pts=0))
    for m in matches:
        h, a, gh, ga = m["home_team_id"], m["away_team_id"], int(m["home_score"]), int(m["away_score"])
        for t, f, g in ((h, gh, ga), (a, ga, gh)):
            r = tbl[t]
            r["P"] += 1; r["GF"] += f; r["GA"] += g
            if f > g: r["W"] += 1; r["Pts"] += 3
            elif f == g: r["D"] += 1; r["Pts"] += 1
            else: r["L"] += 1
    rows = list(tbl.values())
    for r in rows:
        r["GD"] = r["GF"] - r["GA"]
    rows.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"]))
    return rows


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def build_report(d, checks, realism, per_team, dist_by, hsr_by):
    L = []
    L.append("# Validation report – synthetic U19 tournament\n")
    meta_path = os.path.join(d["dir"], "generation_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        L.append(f"Seed: **{meta['seed']}**, generator version {meta['generator_version']}, generated {meta['generated_at']}\n")
    all_ok = all(ok for _, ok, _ in checks)
    L.append(f"## 1. Consistency checks – {'ALL PASSED' if all_ok else 'FAILURES'}\n")
    L.append(md_table(["check", "result", "detail"], [(n, "PASS" if ok else "FAIL", det) for n, ok, det in checks]))
    L.append("")
    import benchmarks as B
    bench, desc = realism
    n_warn = sum(1 for r in bench if r[5] == "WARN")
    L.append(f"## 2. Realism – published benchmarks: {len(bench) - n_warn} OK, {n_warn} WARN\n")
    L.append("Only benchmarks from public, published sources are checked (`benchmarks.py`). For a tournament mean the band is the "
             "benchmark widened by one standard error of that mean, computed from the synthetic matches themselves.\n")
    L.append(md_table(["section", "metric", "actual", "published benchmark", "12-match band", "status", "source"], bench))
    L.append("")
    L.append("Sources:\n")
    for key, src in B.SOURCES.items():
        L.append(f"* `{key}` – {src['label']}. " + " · ".join(src["urls"]))
    L.append("")
    L.append("### Descriptive statistics (no external target)\n")
    L.append("These values are reported for transparency only; no public benchmark is used for them.\n")
    L.append(md_table(["section", "metric", "actual"], desc))
    L.append("")
    L.append("Per-position physical averages (per 90, players with >= 60 min): distance km / high-speed m")
    L.append(md_table(["position", "distance km", "high-speed m"],
                      [(g, f"{dist_by[g]:.2f}", f"{hsr_by[g]:.0f}") for g in ("CB", "FB", "DM", "CM", "AM", "W", "ST") if g in dist_by]))
    L.append("")
    team_names = {t["team_id"]: t["team_name"] for t in d["teams"]}
    formation_of_ = {t["team_id"]: t["formation"] for t in d["teams"]}
    L.append("Per-team averages (per match):")
    per_tid = collections.defaultdict(list)
    for m in d["matches"]:
        evs = d["events"][m["match_id"]]
        for tid in (m["home_team_id"], m["away_team_id"]):
            per_tid[tid].append(team_match_metrics(evs, tid))
    L.append(md_table(["team", "passes", "pass acc %", "shots", "xG", "goals", "def. duels", "PPDA", "possession %"],
                      [(f"{tid} {team_names[tid]}", f"{mean([x['passes'] for x in v]):.0f}", f"{mean([x['pass_accuracy'] for x in v]):.1f}",
                        f"{mean([x['shots'] for x in v]):.1f}", f"{mean([x['xg'] for x in v]):.2f}", f"{mean([x['goals'] for x in v]):.2f}",
                        f"{mean([x['defensive_duels'] for x in v]):.0f}", f"{mean([x['ppda'] for x in v]):.1f}", f"{mean([x['possession_pct'] for x in v]):.0f}")
                       for tid, v in sorted(per_tid.items())]))
    L.append("")
    L.append("## 3. Tournament summary\n")
    L.append("### Results\n")
    L.append(f"All matches at {d['matches'][0]['venue']}; matchdays every {int(d['matches'][2]['day_number']) - int(d['matches'][0]['day_number'])} days (day {d['matches'][0]['day_number']} to day {d['matches'][-1]['day_number']}).\n")
    L.append(md_table(["match", "MD", "day", "date", "home", "score", "away", "live"],
                      [(m["match_id"], m["matchday"], m["day_number"], m["date"], team_names[m["home_team_id"]], f"{m['home_score']}–{m['away_score']}",
                        team_names[m["away_team_id"]], "yes" if m["live_flag"] == "True" else "") for m in d["matches"]]))
    L.append("")
    L.append("### Final table\n")
    tbl = standings(d["matches"])
    L.append(md_table(["#", "team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"],
                      [(i + 1, f"{r['team_id']} {team_names[r['team_id']]}", r["P"], r["W"], r["D"], r["L"], r["GF"], r["GA"], r["GD"], r["Pts"]) for i, r in enumerate(tbl)]))
    before = standings(d["matches"][:11])
    L.append(f"\nTable before the last match (M12): " + ", ".join(f"{r['team_id']} {r['Pts']} pts" for r in before) + "\n")
    L.append("### Top scorers\n")
    pbi = {p["player_id"]: p for p in d["players"]}
    goals = collections.Counter(e["player_id"] for evs in d["events"].values() for e in evs if e["type"] == "shot" and e["outcome"] == "goal")
    L.append(md_table(["player", "team", "age", "position", "goals"],
                      [(pbi[pid]["name"], pid[:2], pbi[pid]["age"], pbi[pid]["position_detail"], n) for pid, n in goals.most_common(10)]))
    L.append("")
    L.append("### Cards, suspensions, injuries\n")
    cards = collections.Counter(e["card_type"] for evs in d["events"].values() for e in evs if e["type"] == "card")
    L.append(f"Yellow cards: {cards['yellow']}, second yellows: {cards['second_yellow']}, straight reds: {cards['straight_red']}.\n")
    absences = [lu for lu in d["lineups"] if lu["status"] in ("suspended", "injured")]
    L.append(md_table(["match", "team", "player", "reason"],
                      [(lu["match_id"], lu["team_id"], f"{pbi[lu['player_id']]['name']} ({lu['player_id']})", lu["status"]) for lu in absences]))
    injuries = [e for evs in d["events"].values() for e in evs if e["type"] == "injury"]
    L.append("\nInjury events: " + ", ".join(f"{e['match_id']} {e['player_id']} ({e['outcome']})" for e in injuries) + "\n")
    L.append("### Ten-men spells\n")
    spells = d.get("red_spells", [])
    if spells:
        rows_ = []
        for mid, tid, pid, minute, mins_left in spells:
            evs = d["events"][mid]
            t_red = next(e["timestamp_ms"] for e in evs if e["type"] == "card" and e["player_id"] == pid and e["outcome"] == "red")
            def share(sub):
                own = sum(1 for e in sub if e["team_id"] == tid and e["type"] in ("pass", "carry", "dribble", "shot"))
                opp = sum(1 for e in sub if e["team_id"] not in (tid, None) and e["type"] in ("pass", "carry", "dribble", "shot"))
                return 100.0 * own / (own + opp) if own + opp else 0.0
            before = [e for e in evs if e["timestamp_ms"] < t_red]
            after = [e for e in evs if e["timestamp_ms"] >= t_red]
            shots_b = sum(1 for e in before if e["team_id"] == tid and e["type"] == "shot")
            shots_a = sum(1 for e in after if e["team_id"] == tid and e["type"] == "shot")
            rows_.append((mid, tid, pid, f"{minute}'", mins_left, f"{share(before):.0f}% → {share(after):.0f}%", f"{shots_b} → {shots_a}"))
        L.append(md_table(["match", "team", "player", "red card", "minutes with 10", "possession before → after", "shots before → after"], rows_))
    else:
        L.append("No sending-offs in this tournament.")
    L.append("")
    L.append("### Squad composition (primary positions)\n")
    groups = ["GK", "CB", "FB", "DM", "CM", "AM", "W", "ST"]
    comp = d.get("composition", {})
    L.append(md_table(["team", "formation"] + groups + ["total"],
                      [(tid, formation_of_[tid]) + tuple(comp[tid].get(g, 0) for g in groups) + (sum(comp[tid].values()),) for tid in sorted(comp)]
                      + [("total", "") + tuple(sum(comp[t].get(g, 0) for t in comp) for g in groups) + (sum(sum(c.values()) for c in comp.values()),)]))
    L.append("")
    L.append("### Multi-positional players\n")
    L.append("Position changes happen only between matches. `position_group_played` in lineups.csv is the slot actually filled in that match; abilities in the secondary position carry a small hidden penalty (ground truth only).\n")
    L.append(md_table(["player", "name", "team", "primary", "secondary", "matches by position played", "status"], d.get("hybrid_rows", [])))
    L.append("")
    L.append("### Hidden gems (youngest standouts) and fatigue\n")
    L.append(md_table(["team", "player", "age", "minutes"], [(t, f"{pbi[pid]['name']} ({pid})", a, f"{m:.0f}") for t, pid, a, m in d.get("gems", [])]))
    fp = d.get("fatigue_phys")
    if fp:
        L.append(f"\nDistance per 90 (outfield, >= 60 min): fresh players {fp[0]:.2f} km (n={fp[2]}) vs players who played >= 60 min three days earlier {fp[1]:.2f} km (n={fp[3]}).\n")
    L.append("### Minutes distribution (per player, whole tournament)\n")
    mins = collections.Counter()
    for lu in d["lineups"]:
        mins[lu["player_id"]] += float(lu["minutes_played"])
    buckets = [(0, 0), (1, 89), (90, 179), (180, 299), (300, 449), (450, 700)]
    counts = []
    for lo, hi in buckets:
        c = sum(1 for p in d["players"] if lo <= mins.get(p["player_id"], 0) <= hi)
        counts.append((f"{lo}–{hi} min", c))
    L.append(md_table(["minutes", "players"], counts))
    L.append(f"\nPlayers used: {sum(1 for p in d['players'] if mins.get(p['player_id'], 0) > 0)} of {len(d['players'])}; "
             f"median minutes of used players: {statistics.median([v for v in mins.values() if v > 0]):.0f}\n")
    L.append("### Age distribution\n")
    ages = collections.Counter(int(p["age"]) for p in d["players"])
    L.append(md_table(["age", "players"], [(a, ages[a]) for a in sorted(ages)]))
    L.append("")
    L.append("### Birth-quarter distribution (relative age effect)\n")
    q = collections.Counter((int(p["birth_date"][5:7]) - 1) // 3 + 1 for p in d["players"])
    n = len(d["players"])
    L.append(md_table(["quarter", "players", "share", "target"],
                      [(f"Q{k}", q[k], f"{100 * q[k] / n:.0f}%", t) for k, t in zip((1, 2, 3, 4), ("~35%", "~28%", "~22%", "~15%"))]))
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Validate the synthetic dataset")
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--report", default="validation_report.md")
    args = ap.parse_args()
    d = load(args.data)
    d["dir"] = args.data
    checks = consistency_checks(d)
    bench, desc, per_team, dist_by, hsr_by = realism_rows(d)
    realism = (bench, desc)
    report = build_report(d, checks, realism, per_team, dist_by, hsr_by)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    for name, ok, det in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {det}")
    warn = [r for r in realism[0] if r[5] == "WARN"]
    print(f"Realism (published benchmarks): {len(realism[0]) - len(warn)} OK, {len(warn)} WARN; {len(realism[1])} descriptive statistics without a target")
    for r in warn:
        print(f"  WARN {r[1]}: {r[2]} (target {r[3]}, band {r[4]})")
    print(f"Report written to {args.report}")
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
