"""Event-by-event KPI accumulation for one match.

`MatchAccumulator.update(event)` consumes events in timestamp order and keeps
per-player and per-team counters, so the same code serves the batch pipeline
and the live engine. Every derived fact (key pass, assist, pressure regain,
xG build-up ...) is computed here with the event ids as evidence.
"""

import collections

from . import definitions as D

ON_BALL = ("pass", "carry", "dribble", "shot")
PASS_LIKE = ("pass", "corner", "free_kick", "throw_in")


class MatchAccumulator:
    def __init__(self, match, lineups, players):
        """`lineups`: this match's lineups.csv rows (all 46). `players`: players.csv rows."""
        self.match = match
        self.home, self.away = match["home_team_id"], match["away_team_id"]
        self.team_of = {p["player_id"]: p["team_id"] for p in players}
        self.pos_of = {}          # player -> position_group_played in this match
        self.on_ms, self.off_ms = {}, {}
        for lu in lineups:
            if lu["on_ms"] not in ("", None):
                self.pos_of[lu["player_id"]] = lu["position_group_played"]
                self.on_ms[lu["player_id"]] = int(lu["on_ms"])
                self.off_ms[lu["player_id"]] = int(lu["off_ms"])
        self.p = collections.defaultdict(collections.Counter)   # player counters
        self.t = collections.defaultdict(collections.Counter)   # team counters
        self.t_x = collections.defaultdict(float)
        self.possession = None       # current possession id
        self.chain = []              # events of the current possession
        self.recent_pressures = []   # (ts, team, player, event_id)
        self.last_ms = 0
        self.n_events = 0
        self.facts = []              # derived facts with evidence (key passes, assists, regains)

    # ------------------------------------------------------------ helpers
    def minutes(self, pid, now_ms=None):
        if pid not in self.on_ms:
            return 0.0
        end = self.off_ms.get(pid)
        if now_ms is not None:
            end = min(end, now_ms) if end is not None else now_ms
        return max(0.0, (end - self.on_ms[pid]) / 60000.0)

    def opp(self, team):
        return self.away if team == self.home else self.home

    # ------------------------------------------------------------ update
    def update(self, e):
        self.n_events += 1
        self.last_ms = e["timestamp_ms"]
        pid, team, et = e["player_id"], e["team_id"], e["type"]
        if e["possession_id"] != self.possession:
            self._close_possession()
            self.possession = e["possession_id"]
            self.chain = []
        self.chain.append(e)
        if team is not None:
            tc = self.t[team]
            if et in ON_BALL:
                tc["on_ball"] += 1
                if e["x"] is not None and e["x"] >= D.FINAL_THIRD_X:
                    tc["final_third_actions"] += 1
        if pid is None:
            if et == "possession_change" and team is not None:
                self.t[team]["possessions"] += 1
            return
        pc = self.p[pid]
        x, y = e["x"], e["y"]
        tc = self.t[team]
        if et in ("tackle", "dribble", "aerial_duel") or (et == "ground_duel"):
            tc["duels"] += 1
            tc["duels_won"] += e["outcome"] == "success"
        if (et in ("tackle", "interception", "foul") or (et == "ground_duel" and e["duel_role"] == "defensive")) and x is not None and x > 50:
            tc["def_actions_opp_half"] += 1
        if et in ON_BALL and D.in_box(x, y):
            pc["touches_in_box"] += 1
        if et == "pass":
            self._pass(e, pc, team)
        elif et in ("corner", "free_kick", "throw_in"):
            self._restart(e, pc)
        elif et == "carry":
            self._carry(e, pc)
        elif et == "dribble":
            pc["offensive_duels"] += 1
            if e["outcome"] == "success":
                pc["offensive_duels_won"] += 1
                pc["dribbles_completed"] += 1
        elif et == "ground_duel":
            if e["duel_role"] == "offensive":
                pc["offensive_duels"] += 1
                pc["offensive_duels_won"] += e["outcome"] == "success"
            else:
                pc["defensive_duels"] += 1
                pc["defensive_duels_won"] += e["outcome"] == "success"
                if e["outcome"] == "fail":
                    pc["dribbled_past"] += 1
        elif et == "tackle":
            pc["defensive_duels"] += 1
            if e["outcome"] == "success":
                pc["defensive_duels_won"] += 1
                pc["tackles_interceptions"] += 1
                self._regain(e)
        elif et == "interception":
            pc["interceptions"] += 1
            pc["tackles_interceptions"] += 1
            self._regain(e)
        elif et == "ball_recovery":
            pc["ball_recoveries"] += 1
            self._regain(e)
        elif et == "aerial_duel":
            pc["aerial_duels"] += 1
            pc["aerial_duels_won"] += e["outcome"] == "success"
        elif et == "clearance":
            if e["related_event_id"] and self._is_blocked_shot(e):
                pc["blocked_shots"] += 1
            else:
                pc["clearances"] += 1
        elif et == "pressure":
            pc["pressures"] += 1
            if x is not None and x > 50:
                pc["pressures_opp_half"] += 1
            self.recent_pressures.append((e["timestamp_ms"], team, pid, e["event_id"]))
            self.t[team]["pressures"] += 1
        elif et == "shot":
            self._shot(e, pc, team)
        elif et == "save":
            pc["saves"] += 1
            self.t[team]["saves"] += 1
        elif et == "foul":
            pc["fouls"] += 1
            self.t[team]["fouls"] += 1
        elif et == "card":
            if e["card_type"] == "yellow":
                pc["yellow_cards"] += 1
            else:
                pc["red_cards"] += 1

    # ------------------------------------------------------------ pieces
    def _pass(self, e, pc, team):
        ok = e["outcome"] == "success"
        pc["passes"] += 1
        pc["passes_completed"] += ok
        self.t[team]["passes"] += 1
        self.t[team]["passes_completed"] += ok
        if e["x"] is not None and e["x"] < 50:
            self.t[team]["passes_own_half"] += 1
        if e["under_pressure"]:
            pc["passes_under_pressure"] += 1
            pc["passes_completed_under_pressure"] += ok
        if e["pass_length_m"] is not None and e["pass_length_m"] > 30:
            pc["long_passes"] += 1
            pc["long_passes_completed"] += ok
        if ok:
            if D.is_progressive(e["x"], e["y"], e["end_x"], e["end_y"]):
                pc["progressive_passes"] += 1
            if e["x"] < D.FINAL_THIRD_X <= e["end_x"]:
                pc["deep_progressions"] += 1
            if D.in_box(e["end_x"], e["end_y"]) and not D.in_box(e["x"], e["y"]):
                pc["passes_into_box"] += 1
            if D.is_cross(e):
                pc["crosses_completed"] += 1
            if e["recipient_id"] and D.in_box(e["end_x"], e["end_y"]):
                self.p[e["recipient_id"]]["touches_in_box"] += 1
        elif e["x"] is not None and e["x"] < 50:
            pc["turnovers"] += 1

    def _restart(self, e, pc):
        # set-piece deliveries are not passes for the passing KPIs, but can be key passes / assists
        pass

    def _carry(self, e, pc):
        if e["outcome"] == "success":
            if D.is_progressive(e["x"], e["y"], e["end_x"], e["end_y"]):
                pc["progressive_carries"] += 1
            if e["x"] < D.FINAL_THIRD_X <= e["end_x"]:
                pc["deep_progressions"] += 1
        elif e["x"] is not None and e["x"] < 50:
            pc["turnovers"] += 1

    def _shot(self, e, pc, team):
        pen = D.is_penalty_shot(e)
        goal = e["outcome"] == "goal"
        pc["shots"] += 1
        pc["shots_on_target"] += e["outcome"] in ("goal", "saved")
        self.t[team]["shots"] += 1
        self.t[team]["xg"] += e["xg"]
        self.t_x[team] += e["xg"]
        if pen:
            pc["penalties_taken"] += 1
            pc["penalty_goals"] += goal
            pc["xg"] += e["xg"]
            self.t[team]["goals"] += goal
            return
        pc["np_shots"] += 1
        pc["npxg"] += e["xg"]
        pc["xg"] += e["xg"]
        pc["np_goals"] += goal
        pc["np_goals_assists"] += goal
        self.t[team]["npxg"] += e["xg"]
        self.t[team]["goals"] += goal
        # key pass / assist: the last successful pass-like event to the shooter in this possession,
        # with no other player's on-ball action in between
        kp = self._find_key_pass(e)
        if kp is not None:
            kpc = self.p[kp["player_id"]]
            kpc["key_passes"] += 1
            kpc["xa"] += e["xg"]
            fact = dict(type="key_pass", player_id=kp["player_id"], shooter=e["player_id"], xg=e["xg"],
                        evidence=[kp["event_id"], e["event_id"]])
            if goal:
                kpc["assists"] += 1
                kpc["np_goals_assists"] += 1
                fact["type"] = "assist"
            self.facts.append(fact)
        # xG build-up: everyone with an on-ball action earlier in the possession, except shooter and key passer
        excluded = {e["player_id"], kp["player_id"] if kp else None}
        for pid2 in {c["player_id"] for c in self.chain[:-1] if c["type"] in ON_BALL + PASS_LIKE and c["team_id"] == team}:
            if pid2 not in excluded:
                self.p[pid2]["xg_buildup"] += e["xg"]

    def _find_key_pass(self, shot):
        shooter = shot["player_id"]
        for c in reversed(self.chain[:-1]):
            if c["team_id"] != shot["team_id"]:
                continue
            if c["type"] in PASS_LIKE:
                return c if (c["recipient_id"] == shooter and c["outcome"] == "success") else None
            if c["type"] in ON_BALL and c["player_id"] != shooter:
                return None
        return None

    def _is_blocked_shot(self, e):
        for c in reversed(self.chain):
            if c["event_id"] == e["related_event_id"]:
                return c["type"] == "shot" and c["outcome"] == "blocked"
        return False

    def _regain(self, e):
        """Pressure regain: an own-team recovery (tackle won, interception, ball recovery)
        within 5 s of a pressure by a teammate (or the same player)."""
        ts = e["timestamp_ms"]
        self.recent_pressures = [r for r in self.recent_pressures if ts - r[0] <= 5000]
        for r_ts, r_team, r_pid, r_eid in self.recent_pressures:
            if r_team == e["team_id"]:
                self.p[r_pid]["pressure_regains"] += 1
                self.facts.append(dict(type="pressure_regain", player_id=r_pid, evidence=[r_eid, e["event_id"]]))
                self.recent_pressures = [r for r in self.recent_pressures if r[3] != r_eid]
                break

    def _close_possession(self):
        self.chain = []

    # ------------------------------------------------------------ outputs
    def team_summary(self, end_ms=None):
        """Team KPIs for the match so far (both teams)."""
        out = {}
        h, a = self.home, self.away
        on = {t: self.t[t]["on_ball"] for t in (h, a)}
        tot = on[h] + on[a] or 1
        ft = {t: self.t[t]["final_third_actions"] for t in (h, a)}
        ftt = ft[h] + ft[a] or 1
        for team in (h, a):
            opp = self.opp(team)
            tc = self.t[team]
            out[team] = dict(
                possession_pct=100.0 * on[team] / tot,
                field_tilt_pct=100.0 * ft[team] / ftt,
                ppda=(self.t[opp]["passes_own_half"] / self.t[team]["def_actions_opp_half"]) if self.t[team]["def_actions_opp_half"] else None,
                xg=round(tc["xg"], 3), npxg=round(tc["npxg"], 3), shots=tc["shots"], goals=tc["goals"],
                passes=tc["passes"], pass_accuracy_pct=(100.0 * tc["passes_completed"] / tc["passes"]) if tc["passes"] else 0.0,
                pressures=tc["pressures"], saves=tc["saves"], fouls=tc["fouls"],
                duels=tc["duels"], duels_won_pct=(100.0 * tc["duels_won"] / tc["duels"]) if tc["duels"] else 0.0,
                possessions=tc["possessions"],
            )
        return out


