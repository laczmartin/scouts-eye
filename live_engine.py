#!/usr/bin/env python3
"""Live KPI engine for the M12 replay.

`update(state, event)` consumes one event at a time (from replay.py's stdout,
from an HTTP POST, or offline from the event file) and maintains:
  * team live KPIs over rolling 5- and 15-minute windows (possession, field
    tilt, PPDA, xG, shots, pressing intensity, control-vs-chaos, momentum);
  * player live KPIs for the minutes played so far plus a low-reliability live
    position score;
  * a moments feed with evidence event ids and an importance in 0-1;
  * a state snapshot every match minute.

Usage:
    python replay.py --match M12 --speed 60 | python live_engine.py --stdin
    python live_engine.py --listen 8080     (then replay.py --url http://localhost:8080/events)
    python live_engine.py --offline         (reads data/synthetic/events/M12.jsonl)
"""

import argparse
import collections
import json
import math
import os
import statistics
import sys

from kpi import aggregate as A
from kpi import definitions as D
from kpi.accumulator import MatchAccumulator

WINDOWS = {"5min": 5 * 60000, "15min": 15 * 60000}
DEF_TYPES = ("tackle", "interception", "foul")
PLAYER_THRESHOLDS = {"progressive_passes": (5, 10), "pressures": (10, 20), "defensive_duels_won": (5, 10),
                     "key_passes": (2, 3), "touches_in_box": (5, 8), "dribbles_completed": (3, 5), "aerial_duels_won": (4, 6)}


class LiveState:
    def __init__(self, match, lineups, players, pool=None, weights=None, baseline=None):
        self.match = match
        self.home, self.away = match["home_team_id"], match["away_team_id"]
        self.acc = MatchAccumulator(match, lineups, players)
        self.players = {p["player_id"]: p for p in players}
        self.pool, self.weights = pool, weights
        self.settings = A.load_settings()
        self.baseline = baseline or {}          # player_id -> dict(goals, position_score, position_group, minutes)
        self.youngest_scorer_age = (baseline or {}).get("_youngest_scorer_age", 99)
        self.events = []                        # compact event log for windows
        self.moments = []
        self.snapshots = []
        self.score = {self.home: 0, self.away: 0}
        self.last_snapshot_minute = -1
        self.last_snapshot_key = None   # (period, minute): the second half restarts the minute count at 45
        self.last_momentum_sign = 0
        self.last_shift_ms = -10 ** 9
        self.last_surge_ms = {self.home: -10 ** 9, self.away: -10 ** 9}
        self.regime = None
        self.thresholds_hit = set()
        self.fouls_by = collections.Counter()

    # ------------------------------------------------------------ windows
    def window(self, team, size_ms, now_ms):
        lo = now_ms - size_ms
        evs = [e for e in self.events if lo < e["ts"] <= now_ms]
        opp = self.away if team == self.home else self.home
        on = sum(1 for e in evs if e["team"] == team and e["on_ball"])
        on_opp = sum(1 for e in evs if e["team"] == opp and e["on_ball"])
        ft = sum(1 for e in evs if e["team"] == team and e["on_ball"] and e["x"] is not None and e["x"] >= D.FINAL_THIRD_X)
        ft_opp = sum(1 for e in evs if e["team"] == opp and e["on_ball"] and e["x"] is not None and e["x"] >= D.FINAL_THIRD_X)
        opp_passes_own_half = sum(1 for e in evs if e["team"] == opp and e["type"] == "pass" and e["x"] is not None and e["x"] < 50)
        def_opp_half = sum(1 for e in evs if e["team"] == team and e["def_action"] and e["x"] is not None and e["x"] > 50)
        xg = sum(e["xg"] for e in evs if e["team"] == team and e["type"] == "shot")
        xg_opp = sum(e["xg"] for e in evs if e["team"] == opp and e["type"] == "shot")
        shots = sum(1 for e in evs if e["team"] == team and e["type"] == "shot")
        pressures = sum(1 for e in evs if e["team"] == team and e["type"] == "pressure")
        mins = min(size_ms, now_ms) / 60000.0 or 1.0
        passes = sum(1 for e in evs if e["type"] == "pass")
        possessions = len({e["pos"] for e in evs})
        changes = sum(1 for e in evs if e["type"] == "possession_change")
        return dict(
            possession_pct=round(100.0 * on / (on + on_opp), 1) if on + on_opp else 50.0,
            field_tilt_pct=round(100.0 * ft / (ft + ft_opp), 1) if ft + ft_opp else 50.0,
            ppda=round(opp_passes_own_half / def_opp_half, 2) if def_opp_half else None,
            xg=round(xg, 3), xg_against=round(xg_opp, 3), shots=shots,
            pressing_intensity=round(pressures / mins, 2),
            passes_per_possession=round(passes / possessions, 2) if possessions else 0.0,
            possession_changes_per_min=round(changes / mins, 2),
        )

    def momentum(self, team, now_ms):
        w = self.window(team, WINDOWS["15min"], now_ms)
        xg_part = math.tanh((w["xg"] - w["xg_against"]) / 0.5)
        tilt_part = (w["field_tilt_pct"] - 50.0) / 50.0
        return round(0.6 * xg_part + 0.4 * tilt_part, 3)

    def control_index(self, now_ms):
        """Control vs chaos over the last 15 minutes: passes per possession
        (high = control) against possession changes per minute (high = chaos)."""
        w = self.window(self.home, WINDOWS["15min"], now_ms)
        ppp, cpm = w["passes_per_possession"], w["possession_changes_per_min"]
        index = round(ppp / 4.0 - cpm / 4.0, 3)  # > 0 control, < 0 chaos
        regime = "control" if index > 0.15 else ("chaos" if index < -0.15 else "balanced")
        return index, regime, ppp, cpm

    # ------------------------------------------------------------ players
    def player_live(self, pid, now_ms):
        c = self.acc.p[pid]
        mins = self.acc.minutes(pid, now_ms)
        pos = self.acc.pos_of.get(pid)
        out = dict(player_id=pid, name=self.players[pid]["name"], team_id=self.acc.team_of[pid], position_group=pos,
                   minutes=round(mins, 1), reliability="very low (live)")
        raw = {}
        for k in D.ALL_KPIS:
            kind = D.KPI_KIND[k]
            if kind == "per90":
                v = c[k] / mins * 90.0 if mins > 0 else 0.0
            elif kind == "max":
                v = 0.0
            else:
                num, den = D.RATIO_DEFS[k]
                v = (100.0 if kind == "pct" else 1.0) * c[num] / c[den] if c[den] else 0.0
            raw[k] = round(v, 3)
        out["raw_per90"] = raw
        out["totals"] = {k: c[k] for k in ("passes", "progressive_passes", "key_passes", "shots", "np_goals", "assists",
                                           "pressures", "pressure_regains", "defensive_duels_won", "touches_in_box") if c[k]}
        if self.pool and self.weights and pos in D.OUTFIELD_GROUPS and mins > 0:
            cats = {}
            for cat, kpis in D.CATEGORIES.items():
                vals = []
                for k, _ in kpis:
                    if cat == "physical":
                        continue
                    shr = A.shrink(raw[k], mins, self.pool.mean(pos, k))
                    vals.append(self.pool.pct(pos, k, shr))
                cats[cat] = statistics.fmean(vals) if vals else 50.0
            w = self.weights["weights"][pos]
            out["live_position_score"] = round(sum(cats[cat] * w[cat] for cat in cats) / 100.0, 1)
            out["live_category_scores"] = {k: round(v, 1) for k, v in cats.items()}
        return out

    # ------------------------------------------------------------ moments
    def add_moment(self, e, mtype, fact, evidence, importance, team=None, player=None):
        self.moments.append(dict(t_ms=e["timestamp_ms"], minute=e["minute"], period=e["period"], type=mtype,
                                 team_id=team if team is not None else e["team_id"],
                                 player_id=player if player is not None else e["player_id"],
                                 fact=fact, evidence_event_ids=evidence, importance=round(importance, 2)))

    def snapshot(self, e):
        now = e["timestamp_ms"]
        idx, regime, ppp, cpm = self.control_index(now)
        teams = {}
        for t in (self.home, self.away):
            teams[t] = {name: self.window(t, size, now) for name, size in WINDOWS.items()}
            teams[t]["match"] = {k: v for k, v in self.acc.team_summary()[t].items() if k not in ("match_id", "team_id", "opponent_id")}
            teams[t]["momentum"] = self.momentum(t, now)
        on_pitch = [pid for pid in self.acc.on_ms if self.acc.on_ms[pid] <= now and (self.acc.off_ms.get(pid) is None or self.acc.off_ms[pid] > now)]
        players = [self.player_live(pid, now) for pid in on_pitch if self.acc.pos_of.get(pid) in D.OUTFIELD_GROUPS]
        min_live = self.settings["min_minutes_live"]
        for p in players:
            p["ranking_status"] = "ranked" if p["minutes"] >= min_live else "low_data"
        players.sort(key=lambda p: (p["ranking_status"] != "ranked", -p.get("live_position_score", 0)))
        self.snapshots.append(dict(
            minute=e["minute"], t_ms=now, period=e["period"], score={self.home: self.score[self.home], self.away: self.score[self.away]},
            control_index=idx, regime=regime, passes_per_possession=ppp, possession_changes_per_min=cpm,
            teams=teams, top_players=[dict(player_id=p["player_id"], name=p["name"], team_id=p["team_id"], position_group=p["position_group"],
                                           minutes=p["minutes"], live_position_score=p.get("live_position_score"), reliability=p["reliability"])
                                      for p in players if p["ranking_status"] == "ranked"][:5],
            players=players, n_events=self.acc.n_events, moments_so_far=len(self.moments)))


def update(state, e):
    """Consume one event. Returns the list of moments created by this event."""
    before = len(state.moments)
    acc = state.acc
    # per-player counters before the event, for threshold detection
    pid = e["player_id"]
    prev = dict(acc.p[pid]) if pid else {}
    acc.update(e)
    state.events.append(dict(ts=e["timestamp_ms"], team=e["team_id"], type=e["type"], x=e["x"], xg=e["xg"] or 0.0,
                             pos=e["possession_id"], on_ball=e["type"] in ("pass", "carry", "dribble", "shot"),
                             def_action=e["type"] in DEF_TYPES or (e["type"] == "ground_duel" and e.get("duel_role") == "defensive")))
    now = e["timestamp_ms"]
    et = e["type"]
    # --- goal / big chance
    if et == "shot":
        if e["outcome"] == "goal":
            state.score[e["team_id"]] += 1
            c = acc.p[pid]
            base_goals = state.baseline.get(pid, {}).get("goals", 0)
            goals_now = c["np_goals"] + c["penalty_goals"]
            fact = dict(scorer=state.players[pid]["name"], xg=e["xg"], score=f"{state.score[state.home]}-{state.score[state.away]}",
                        goals_in_match=goals_now, body_part=e["body_part"], penalty=D.is_penalty_shot(e))
            kp = next((f for f in reversed(acc.facts) if f["type"] == "assist" and f["evidence"][1] == e["event_id"]), None)
            evidence = [e["event_id"]]
            if kp:
                fact["assist_by"] = state.players[kp["player_id"]]["name"]
                evidence.insert(0, kp["evidence"][0])
            diff = state.score[e["team_id"]] - state.score[state.away if e["team_id"] == state.home else state.home]
            imp = 0.85 + (0.1 if diff in (0, 1) else 0.0) + (0.05 if e["minute"] >= 75 else 0.0)
            state.add_moment(e, "goal", fact, evidence, min(imp, 1.0))
            age = int(state.players[pid]["age"])
            if base_goals == 0 and goals_now == 1:
                state.add_moment(e, "milestone", dict(milestone="first tournament goal", scorer=state.players[pid]["name"], age=age), [e["event_id"]], 0.6)
            if age < state.youngest_scorer_age:
                state.youngest_scorer_age = age
                state.add_moment(e, "milestone", dict(milestone="youngest scorer of the tournament", scorer=state.players[pid]["name"], age=age), [e["event_id"]], 0.7)
            if goals_now == 2:
                state.add_moment(e, "milestone", dict(milestone="brace", scorer=state.players[pid]["name"]), [e["event_id"]], 0.6)
            if goals_now == 3:
                state.add_moment(e, "milestone", dict(milestone="hat-trick", scorer=state.players[pid]["name"]), [e["event_id"]], 0.9)
        elif e["xg"] >= 0.3:
            state.add_moment(e, "big_chance", dict(shooter=state.players[pid]["name"], xg=e["xg"], outcome=e["outcome"]), [e["event_id"]], 0.55)
    # --- cards, injuries, substitutions with context
    if et == "card":
        state.fouls_by[pid] += 0
        fact = dict(player=state.players[pid]["name"], card=e["card_type"], fouls_so_far=acc.p[pid]["fouls"],
                    minutes_played=round(acc.minutes(pid, now), 1))
        if e["outcome"] == "red":
            fact["team_plays_with"] = 10
        state.add_moment(e, "card", fact, [e["related_event_id"], e["event_id"]] if e["related_event_id"] else [e["event_id"]],
                         0.7 if e["outcome"] == "red" else 0.3)
    if et == "injury":
        state.add_moment(e, "injury", dict(player=state.players[pid]["name"], severity=e["outcome"], minutes_played=round(acc.minutes(pid, now), 1)),
                         [e["event_id"]], 0.5 if e["outcome"] == "major" else 0.35)
    if et == "substitution":
        inp = e["sub_player_in_id"]
        b_in = state.baseline.get(inp, {})
        fact = dict(off=state.players[pid]["name"], off_minutes=round(acc.minutes(pid, now), 1),
                    on=state.players[inp]["name"], on_age=int(state.players[inp]["age"]),
                    on_baseline_position_score=b_in.get("position_score"), on_baseline_minutes=b_in.get("minutes"),
                    score=f"{state.score[state.home]}-{state.score[state.away]}")
        state.add_moment(e, "substitution", fact, [e["event_id"]], 0.3)
    # --- player thresholds
    if pid:
        c = acc.p[pid]
        for k, levels in PLAYER_THRESHOLDS.items():
            for lv in levels:
                if prev.get(k, 0) < lv <= c[k] and (pid, k, lv) not in state.thresholds_hit:
                    state.thresholds_hit.add((pid, k, lv))
                    state.add_moment(e, "player_threshold", dict(player=state.players[pid]["name"], kpi=k, count=lv,
                                                                minutes=round(acc.minutes(pid, now), 1)), [e["event_id"]], 0.3 if lv == levels[0] else 0.4)
    # --- rolling-window moments (checked at most once per minute, after 10')
    new_minute = (e["period"], e["minute"]) != state.last_snapshot_key
    if e["minute"] >= 10 and new_minute:
        m_home = state.momentum(state.home, now)
        sign = 1 if m_home > 0.25 else (-1 if m_home < -0.25 else 0)
        if sign != 0 and sign != state.last_momentum_sign and now - state.last_shift_ms > 3 * 60000:
            if state.last_momentum_sign != 0:
                team = state.home if sign > 0 else state.away
                state.add_moment(e, "momentum_shift", dict(momentum_home=m_home, now_with=team), [e["event_id"]], 0.5, team=team, player=None)
            state.last_momentum_sign = sign
            state.last_shift_ms = now
        for t in (state.home, state.away):
            w5 = state.window(t, WINDOWS["5min"], now)
            avg_rate = acc.t[t]["pressures"] / (now / 60000.0)
            if w5["pressing_intensity"] >= 1.6 * avg_rate and w5["pressing_intensity"] * 5 >= 15 and now - state.last_surge_ms[t] > 5 * 60000:
                state.last_surge_ms[t] = now
                state.add_moment(e, "pressing_surge", dict(pressures_last_5min=int(w5["pressing_intensity"] * 5), match_rate_per_5min=round(avg_rate * 5, 1),
                                                           ppda_last_5min=w5["ppda"]), [e["event_id"]], 0.4, team=t, player=None)
        idx, regime, ppp, cpm = state.control_index(now)
        if state.regime is not None and regime != state.regime and regime != "balanced":
            state.add_moment(e, "control_chaos_switch", dict(from_regime=state.regime, to_regime=regime, control_index=idx,
                                                             passes_per_possession=ppp, possession_changes_per_min=cpm), [e["event_id"]], 0.45, team=None, player=None)
        if regime != "balanced" or state.regime is None:
            state.regime = regime
    # --- snapshot once per (period, minute); the second half starts again at minute 45
    if new_minute:
        state.last_snapshot_key = (e["period"], e["minute"])
        state.last_snapshot_minute = e["minute"]
        state.snapshot(e)
    return state.moments[before:]


# ---------------------------------------------------------------- running
def load_baseline(baseline_dir, d):
    """Baseline facts needed for milestones and substitution context (M01-M11 only)."""
    baseline = {}
    goals = collections.Counter()
    ages = []
    pbi = {p["player_id"]: p for p in d["players"]}
    for m in d["matches"]:
        if m["live_flag"] == "True":
            continue
        for e in d["events"][m["match_id"]]:
            if e["type"] == "shot" and e["outcome"] == "goal":
                goals[e["player_id"]] += 1
                ages.append(int(pbi[e["player_id"]]["age"]))
    for pid in pbi:
        baseline[pid] = dict(goals=goals[pid])
    prof_path = os.path.join(baseline_dir, "player_profiles.csv")
    if os.path.exists(prof_path):
        for r in A.read_csv(prof_path):
            if r["profile_type"] == "primary":
                baseline[r["player_id"]].update(position_score=float(r["position_score"]), minutes=float(r["minutes"]),
                                                position_group=r["position_group"])
    baseline["_youngest_scorer_age"] = min(ages) if ages else 99
    return baseline


def make_state(d, match, pool, weights, baseline_dir):
    lus = [lu for lu in d["lineups"] if lu["match_id"] == match["match_id"]]
    return LiveState(match, lus, d["players"], pool, weights, load_baseline(baseline_dir, d))


def write_outputs(state, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    mid = state.match["match_id"]
    with open(os.path.join(out_dir, f"{mid}_moments.jsonl"), "w") as f:
        for m in state.moments:
            f.write(json.dumps(m) + "\n")
    with open(os.path.join(out_dir, f"{mid}_state_by_minute.jsonl"), "w") as f:
        for s in state.snapshots:
            f.write(json.dumps(s) + "\n")


def run_offline(d, match, pool, weights, baseline_dir, out_dir):
    state = make_state(d, match, pool, weights, baseline_dir)
    for e in d["events"][match["match_id"]]:
        update(state, e)
    write_outputs(state, out_dir)
    types = collections.Counter(m["type"] for m in state.moments)
    print(f"  {match['match_id']}: {len(state.moments)} moments {dict(types)}, {len(state.snapshots)} minute snapshots -> {out_dir}")
    return state


def _load_context(args):
    d = A.load_dataset(args.data)
    match = next(m for m in d["matches"] if m["match_id"] == args.match)
    pool = A.ReferencePool(A.read_csv(os.path.join(args.reference, "reference_player_kpis.csv")))
    with open("config/position_weights.json") as f:
        weights = json.load(f)
    return d, match, pool, weights


def main():
    ap = argparse.ArgumentParser(description="Live KPI engine")
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--match", default="M12")
    ap.add_argument("--reference", default="data/reference")
    ap.add_argument("--baseline", default="data/kpi")
    ap.add_argument("--out", default="data/kpi/live")
    ap.add_argument("--stdin", action="store_true", help="read events (JSON lines) from stdin, e.g. piped from replay.py")
    ap.add_argument("--listen", type=int, default=None, help="accept events via HTTP POST on this port")
    ap.add_argument("--offline", action="store_true", help="process the event file directly")
    args = ap.parse_args()
    d, match, pool, weights = _load_context(args)
    state = make_state(d, match, pool, weights, args.baseline)
    if args.offline:
        for e in d["events"][match["match_id"]]:
            update(state, e)
    elif args.listen:
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                e = json.loads(self.rfile.read(n))
                for m in update(state, e):
                    print(json.dumps(m), flush=True)
                self.send_response(204)
                self.end_headers()

            def log_message(self, *a):
                pass
        print(f"listening on port {args.listen}; Ctrl-C to stop and write outputs", file=sys.stderr)
        try:
            HTTPServer(("", args.listen), Handler).serve_forever()
        except KeyboardInterrupt:
            pass
    else:
        for line in sys.stdin:
            if line.strip():
                for m in update(state, json.loads(line)):
                    print(json.dumps(m), flush=True)
    write_outputs(state, args.out)
    print(f"{len(state.moments)} moments, {len(state.snapshots)} snapshots written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
