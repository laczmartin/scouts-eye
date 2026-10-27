"""Fact store: the only data the agents may use, plus the read-only function tools.

Sources:
  data/kpi/live/M12_moments.jsonl, data/kpi/live/M12_state_by_minute.jsonl,
  data/kpi/player_profiles.csv (baseline M01-M11, used during the live match),
  data/kpi/final/player_profiles.csv (M01-M12, used for the recap / scouting note),
  data/kpi/final/team_match_kpis.csv.
"""

import csv
import json
import os


def slim_state(s):
    """A state snapshot for the prompts: without the per-player list, with the three top players."""
    return {k: v for k, v in s.items() if k not in ("players", "top_players")} | {"top_players": s.get("top_players", [])[:3]}


def _read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class FactStore:
    def __init__(self, match_id="M12", kpi_dir="data/kpi", data_dir="data/synthetic"):
        self.match_id = match_id
        self.data_dir = data_dir
        self.moments = _read_jsonl(os.path.join(kpi_dir, "live", f"{match_id}_moments.jsonl"))
        for i, m in enumerate(self.moments):
            m["moment_id"] = f"{match_id}-MOM-{i:03d}"
        self.states = _read_jsonl(os.path.join(kpi_dir, "live", f"{match_id}_state_by_minute.jsonl"))
        self.profiles = {}            # baseline (M01-M11) primary profiles by player
        for r in _read_csv(os.path.join(kpi_dir, "player_profiles.csv")):
            if r["profile_type"] == "primary":
                self.profiles[r["player_id"]] = r
        self.profiles_final = {}
        for r in _read_csv(os.path.join(kpi_dir, "final", "player_profiles.csv")):
            if r["profile_type"] == "primary":
                self.profiles_final[r["player_id"]] = r
        self.team_kpis = [r for r in _read_csv(os.path.join(kpi_dir, "final", "team_match_kpis.csv"))]
        self.players = {p["player_id"]: p for p in _read_csv(os.path.join(data_dir, "players.csv"))}
        self.teams = {t["team_id"]: t for t in _read_csv(os.path.join(data_dir, "teams.csv"))}
        self.match = next(m for m in _read_csv(os.path.join(data_dir, "matches.csv")) if m["match_id"] == match_id)
        self.home, self.away = self.match["home_team_id"], self.match["away_team_id"]
        self.by_id = {m["moment_id"]: m for m in self.moments}
        self.all_matches = _read_csv(os.path.join(data_dir, "matches.csv"))
        self.venue = self.match.get("venue", "neutral venue")
        self.tournament = self.tournament_context()
        for m in self.moments:
            self.annotate_moment(m)

    # ------------------------------------------------------------ event metrics and player tags (kpi/event_metrics.py, no AI)
    @property
    def events(self):
        if not hasattr(self, "_events"):
            self._events = _read_jsonl(os.path.join(self.data_dir, "events", f"{self.match_id}.jsonl"))
            self._events_by_id = {e["event_id"]: e for e in self._events}
        return self._events

    def event(self, event_id):
        self.events
        return self._events_by_id.get(event_id)

    def minute_to_tms(self, minute):
        for s in self.states:
            if s["minute"] >= minute:
                return s["t_ms"]
        return self.states[-1]["t_ms"] if self.states else minute * 60000

    def period_of_minute(self, minute):
        for s in self.states:
            if s["minute"] >= minute:
                return s["period"]
        return self.states[-1]["period"] if self.states else (1 if minute <= 45 else 2)

    @property
    def tags(self):
        if not hasattr(self, "_tags"):
            from kpi import event_metrics as EM
            self._tags = EM.match_tags(self.events, EM.read_snapshots(self.match_id, os.path.join(self.data_dir, "physical_snapshots.csv")),
                                       self.player_name, self.minute_to_tms, self.period_of_minute)
        return self._tags

    def tags_between(self, t_from_ms, t_to_ms):
        return [t for t in self.tags if t_from_ms < t["t_ms"] <= t_to_ms]

    def moment_ball_metrics(self, m):
        """Shot speed of the moment's shot and the metrics of the pass that set it up (if any)."""
        from kpi import event_metrics as EM
        shot = next((self.event(i) for i in m.get("evidence_event_ids", []) if self.event(i) and self.event(i)["type"] == "shot"), None)
        if not shot:
            return None
        out = dict(shot=EM.shot_metrics(shot))
        idx = self.events.index(shot)
        for e in reversed(self.events[max(0, idx - 6):idx]):
            if e["type"] == "pass" and e.get("outcome") == "success" and e.get("recipient_id") == shot["player_id"]:
                pm = EM.pass_metrics(e)
                out["assist_pass"] = dict(passer=self.player_name(e["player_id"]), distance_m=pm["distance_m"], difficulty=pm["difficulty"],
                                          line_breaking=pm["line_breaking"], ball_speed_kmh=pm["ball_speed_kmh"])
                break
        return out

    # ------------------------------------------------------------ tournament context (computed, never typed in)
    def standings(self, matches):
        tbl = {t: dict(team_id=t, team=self.team_name(t), played=0, won=0, drawn=0, lost=0, gf=0, ga=0, points=0) for t in self.teams}
        for m in matches:
            h, a, gh, ga = m["home_team_id"], m["away_team_id"], int(m["home_score"]), int(m["away_score"])
            for t, f, g in ((h, gh, ga), (a, ga, gh)):
                r = tbl[t]
                r["played"] += 1; r["gf"] += f; r["ga"] += g
                if f > g: r["won"] += 1; r["points"] += 3
                elif f == g: r["drawn"] += 1; r["points"] += 1
                else: r["lost"] += 1
        rows = sorted(tbl.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["team_id"]))
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            r["gd"] = r["gf"] - r["ga"]
        return rows

    def tournament_context(self):
        before = self.standings([m for m in self.all_matches if m["match_id"] < self.match_id])
        after = self.standings([m for m in self.all_matches if m["match_id"] <= self.match_id])
        pos = {r["team_id"]: r for r in before}
        a, b = pos[self.home], pos[self.away]
        leader, chaser = (a, b) if a["rank"] < b["rank"] else (b, a)
        stake = (f"Title decider: {leader['team']} ({leader['points']} pts) vs {chaser['team']} ({chaser['points']} pts) are 1st and 2nd "
                 f"before the last matchday; the winner of this match wins the tournament" + (", a draw keeps " + leader['team'] + " top" if leader["points"] > chaser["points"] else ", a draw decides on goal difference") + ".")
        return dict(matchday=int(self.match["matchday"]), last_matchday=True, venue=self.venue, neutral_venue=True,
                    standings_before=before, stake=stake, standings_after=after, tournament_winner=after[0]["team"], tournament_winner_id=after[0]["team_id"])

    # ------------------------------------------------------------ clock and goal semantics
    def period_at_ms(self, t_ms):
        return self.state_at_ms(t_ms)["period"]

    @staticmethod
    def clock_string(minute, period):
        """Football clock: 45+N' only for first-half minutes after 45, 90+N' only for second-half minutes after 90;
        second-half minutes 46-90 are plain minutes."""
        if period == 1 and minute > 45:
            return f"45+{minute - 45}'"
        if period == 2 and minute > 90:
            return f"90+{minute - 90}'"
        return f"{minute}'"

    def state_at_ms(self, t_ms):
        cands = [s for s in self.states if s["t_ms"] <= t_ms]
        return cands[-1] if cands else self.states[0]

    def annotate_moment(self, m):
        # the period comes from the event itself (live engine); derive it from the snapshot only for old files
        m["period"] = m.get("period") or self.period_at_ms(m["t_ms"])
        m["clock"] = self.clock_string(m["minute"], m["period"])
        m["half"] = "first half" if m["period"] == 1 else "second half"
        if m["type"] == "goal":
            sh, sa = (int(x) for x in m["fact"]["score"].split("-"))
            scorer_goals = sh if m["team_id"] == self.home else sa
            other = sa if m["team_id"] == self.home else sh
            if scorer_goals - other == 0:
                effect = "equaliser"
            elif scorer_goals - other == 1:
                effect = "takes the lead" if scorer_goals == 1 or (scorer_goals - 1) == other else "takes the lead"
            elif scorer_goals > other:
                effect = "extends the lead"
            else:
                effect = "reduces the deficit"
            m["fact"]["score_after_goal"] = f"{self.team_name(self.home)} {sh}-{sa} {self.team_name(self.away)}"
            m["fact"]["goal_effect"] = effect
            m["fact"]["scoring_team"] = self.team_name(m["team_id"])
        elif m["type"] == "milestone":
            # a milestone raised by a goal (brace, first tournament goal, youngest scorer) carries that goal's score and effect
            goal = next((g for g in self.moments if g["type"] == "goal" and g["t_ms"] == m["t_ms"] and g["player_id"] == m["player_id"]), None)
            if goal and "score_after_goal" in goal["fact"]:
                for k in ("score", "score_after_goal", "goal_effect", "scoring_team"):
                    m["fact"][k] = goal["fact"][k]
                m["fact"]["note"] = "this milestone is the goal just scored; describe the score after that goal and its effect exactly"

    # ------------------------------------------------------------ lookups
    def team_name(self, tid):
        return self.teams[tid]["team_name"] if tid in self.teams else str(tid)

    def player_name(self, pid):
        return self.players[pid]["name"] if pid in self.players else str(pid)

    def state_at(self, minute, period=None):
        """Latest snapshot at or before `minute` (second-half minutes >= 45 prefer period 2)."""
        cands = [s for s in self.states if s["minute"] <= minute and (period is None or s["period"] == period)]
        if not cands:
            cands = [s for s in self.states if s["minute"] <= minute]
        return cands[-1] if cands else self.states[0]

    def state_at_ms(self, t_ms):
        cands = [s for s in self.states if s["t_ms"] <= t_ms]
        return cands[-1] if cands else self.states[0]

    def moments_between(self, t_from_ms, t_to_ms, mtype=None):
        return [m for m in self.moments if t_from_ms <= m["t_ms"] <= t_to_ms and (mtype is None or m["type"] == mtype)]

    def player_live(self, pid, t_ms):
        s = self.state_at_ms(t_ms)
        for p in s["players"]:
            if p["player_id"] == pid:
                return p
        return None

    # ------------------------------------------------------------ line-ups: who is on the pitch at a moment
    @property
    def lineups(self):
        if not hasattr(self, "_lineups"):
            self._lineups = {r["player_id"]: r for r in _read_csv(os.path.join(self.data_dir, "lineups.csv")) if r["match_id"] == self.match_id}
        return self._lineups

    def _change_clock(self, t_ms):
        """Clock string of the substitution / sending-off at t_ms (from the event itself)."""
        e = next((x for x in self.events if x["timestamp_ms"] == t_ms and x["type"] in ("substitution", "card", "injury")), None)
        return self.clock_string(e["minute"], e["period"]) if e else self.clock_string(self.state_at_ms(t_ms)["minute"], self.period_at_ms(t_ms))

    def pitch_status(self, pid, t_ms, clock=None):
        """Whether a player is on the pitch at t_ms (line-ups and substitutions). Only what is known at that moment:
        a player who comes on later is 'not brought on so far', never 'comes on at 54''."""
        p = self.players.get(pid)
        clock = clock or self.clock_string(self.state_at_ms(t_ms)["minute"], self.period_at_ms(t_ms))
        if p is None or p["team_id"] not in (self.home, self.away):
            return dict(on_pitch=False, status="not_in_match", text="does not play in this match (his team is not playing)")
        r = self.lineups.get(pid)
        on = int(r["on_ms"]) if r and r["on_ms"] else None
        off = int(r["off_ms"]) if r and r["off_ms"] else None
        if on is None or t_ms < on:
            why = {"injured": "injured, not available for this match", "suspended": "suspended for this match"}.get((r or {}).get("status"))
            return dict(on_pitch=False, status="not_on_pitch_yet", at=clock,
                        text=f"not on the pitch at {clock}: " + (why or "not in the starting line-up and not brought on so far"))
        if off is not None and t_ms >= off and r["end_reason"] != "full_time":
            how = {"substituted": "substituted"}.get(r["end_reason"], r["end_reason"].replace("_", " ") or "went off")
            return dict(on_pitch=False, status="off", at=clock, went_off=self._change_clock(off),
                        text=f"not on the pitch any more: {how} at {self._change_clock(off)}")
        since = "kick-off" if on == 0 else self._change_clock(on)
        return dict(on_pitch=True, status="on_pitch", at=clock, since=since,
                    text=f"on the pitch at {clock} (since {since}" + ("" if on == 0 else ", came on as a substitute") + ")")

    def final_score(self):
        return int(self.match["home_score"]), int(self.match["away_score"])

    # ------------------------------------------------------------ tools (read-only, JSON strings)
    def make_tools(self):
        store = self

        def get_moment(moment_id: str) -> str:
            """Return one match moment (type, minute, team, player, fact, evidence event ids, importance) by moment id."""
            m = store.by_id.get(moment_id)
            return json.dumps(m, ensure_ascii=False) if m else json.dumps({"error": f"unknown moment {moment_id}"})

        def get_state(minute: int) -> str:
            """Return the live match state at a match minute: score, control/chaos regime, team windows (5/15 min), momentum, top players."""
            s = store.state_at(int(minute))
            slim = {k: v for k, v in s.items() if k != "players"}
            return json.dumps(slim, ensure_ascii=False)

        def get_player_profile(player_id: str) -> str:
            """Return a player's baseline tournament profile (position, minutes, reliability, position score, category scores, strengths, weaknesses)."""
            p = store.profiles.get(player_id)
            if not p:
                return json.dumps({"error": f"no profile for {player_id} (goalkeeper or no minutes)"})
            out = dict(p)
            out["name"] = store.player_name(player_id)
            return json.dumps(out, ensure_ascii=False)

        def get_player_live(player_id: str, minute: int) -> str:
            """Return a player's live KPIs in this match up to a minute (minutes played, totals, raw per 90, live position score, reliability)."""
            s = store.state_at(int(minute))
            for p in s["players"]:
                if p["player_id"] == player_id:
                    return json.dumps(p, ensure_ascii=False)
            return json.dumps({"error": f"{player_id} not on the pitch at minute {minute}"})

        def get_team_kpis(match_id: str) -> str:
            """Return both teams' KPIs for a match (possession, field tilt, PPDA, xG, shots, passes, pressures, duels won %, saves)."""
            rows = [r for r in store.team_kpis if r["match_id"] == match_id]
            return json.dumps(rows, ensure_ascii=False)

        return [get_moment, get_state, get_player_profile, get_player_live, get_team_kpis]
