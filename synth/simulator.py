"""Possession-chain match simulator.

A match is a sequence of possessions. Each possession is a chain of on-ball
actions (pass / carry / dribble / shot / clearance). Before every action the
defending team may apply pressure; passes can be intercepted or cleared,
carries can be challenged, dribbles are duels, high balls become aerial duels.
Probabilities depend on the actor's hidden abilities, team style, opponent
pressing, pitch zone, fatigue and game state.

Coordinates: every event is stored in the *acting team's* attacking frame
(0-100 x 0-100, attacking left -> right). Internally the ball position is
kept in the frame of the team in possession and mirrored on turnover.
"""

import math
import random

from . import config as C

S = C.SIM
PITCH_X = C.PITCH_LENGTH_M / 100.0  # metres per x unit
PITCH_Y = C.PITCH_WIDTH_M / 100.0   # metres per y unit


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _sig(x):
    return 1.0 / (1.0 + math.exp(-x))


def _ab(a):
    """Map a 0-100 ability to roughly -1..+1."""
    return (a - 50.0) / 50.0


def dist_m(x1, y1, x2, y2):
    return math.hypot((x2 - x1) * PITCH_X, (y2 - y1) * PITCH_Y)


def shot_xg(x, y, body_part, under_pressure, is_header=False, is_penalty=False):
    """Expected goal value from distance, angle, body part and pressure."""
    if is_penalty:
        return 0.76
    gx, gy = 100.0, 50.0
    d = dist_m(x, y, gx, gy)
    # goal-mouth angle (7.32 m goal)
    dy = (y - 50.0) * PITCH_Y
    dx = max(0.1, (100.0 - x) * PITCH_X)
    a1 = math.atan2(dy + 3.66, dx)
    a2 = math.atan2(dy - 3.66, dx)
    angle = abs(a1 - a2)
    logit = -0.86 - 0.105 * d + 1.25 * angle
    if is_header or body_part == "head":
        logit -= 0.45
    if under_pressure:
        logit -= 0.25
    return round(_clamp(_sig(logit), 0.01, 0.65), 3)


class OnPitch:
    __slots__ = ("pid", "group", "detail", "hx", "hy", "ab", "on_ms", "off_ms", "started", "yellows")

    def __init__(self, pid, group, detail, hx, hy, ab, on_ms, started):
        self.pid, self.group, self.detail = pid, group, detail
        self.hx, self.hy, self.ab = hx, hy, ab
        self.on_ms, self.off_ms, self.started = on_ms, None, started
        self.yellows = 0


class TeamState:
    """One team in one match: line-up, bench, substitution windows, cards."""

    def __init__(self, team, players, abilities, rng, is_home, context):
        self.team = team
        self.tid = team["team_id"]
        self.is_home = is_home
        self.style_pos = team["style_possession"]
        self.style_press = team["style_pressing"]
        self.style_dir = team["style_directness"]
        self.abilities = abilities
        self.squad = [p for p in players if p["team_id"] == self.tid]
        self.rng = rng
        # cross-match context: availability, accumulated load, gem plan, recent starts
        self.unavailable = context.get("unavailable", {})      # player_id -> "suspended" / "injured"
        self.load = context.get("load", {})                    # player_id -> fatigue load (0 = fresh)
        self.gem_id = context.get("gem_id")
        self.gem_starts = context.get("gem_starts", False)
        self.gem_sub_in = context.get("gem_sub_in", False)
        self.recent_full = context.get("recent_full", {})      # player_id -> consecutive near-full matches
        self.secondary = abilities.get("_secondary", {})       # player_id -> dict(position, penalty, key_abilities)
        self.need_position = context.get("need_position", {})  # hybrid player_id -> set of positions still to be played
        self.matchday = context.get("matchday", 1)
        self.on = []          # OnPitch
        self.bench = []       # player dicts
        self.log = []         # OnPitch records of players who finished their spell
        self.rows = {}        # player_id -> lineup row dict
        self.subs_done = 0
        self.windows_used = 0
        self.sub_plan = []    # list of (minute, count)
        self.goals = 0
        self.men = 11
        self._pick_lineup()

    # ------------------------------------------------------------ line-up
    def _pick_lineup(self):
        rng = self.rng
        formation = C.FORMATIONS[self.team["formation"]]
        available = [p for p in self.squad if p["player_id"] not in self.unavailable]
        by_group = {}
        for p in available:
            by_group.setdefault(p["position_group"], []).append(p)
        used = set()
        for p in self.squad:
            if p["player_id"] in self.unavailable:
                self.rows[p["player_id"]] = dict(status=self.unavailable[p["player_id"]], on_ms=None, off_ms=None,
                                                 end_reason=None, position_detail=None, position_group_played=None)
        # the gem starts when the plan says so
        if self.gem_starts and self.gem_id not in self.unavailable:
            gem = next(p for p in self.squad if p["player_id"] == self.gem_id)
            slot = next((s for s in formation if s[1] == gem["position_group"]), None)
            if slot:
                self._start(gem, slot)
                used.add(gem["player_id"])
        # multi-positional players who still owe an appearance in one of their positions
        # are placed first, so that their primary slot does not grab them earlier
        if self.matchday >= 2:
            for p in available:
                needs = self.need_position.get(p["player_id"], ())
                if not needs or p["player_id"] in used or p["player_id"] == self.gem_id or rng.random() > 0.9:
                    continue
                if self.recent_full.get(p["player_id"], 0) >= 2 and p["position_group"] != "CB":
                    continue
                for detail, group, hx, hy in formation:
                    if group in needs and not any(o.detail == detail for o in self.on):
                        self._start(p, (detail, group, hx, hy))
                        used.add(p["player_id"])
                        break
        for detail, group, hx, hy in formation:
            if any(o.detail == detail for o in self.on):
                continue
            cands = [p for p in available if self.can_play(p, group) and p["player_id"] not in used and p["player_id"] != self.gem_id]
            if not cands:  # fall back to a neighbouring position group
                near = {"GK": [], "CB": ["DM", "FB"], "FB": ["W", "CB"], "DM": ["CM", "CB"], "CM": ["DM", "AM"],
                        "AM": ["CM", "W"], "W": ["AM", "FB", "ST"], "ST": ["W", "AM"]}[group]
                cands = [p for p in available if p["position_group"] in near and p["player_id"] not in used]
            if not cands:  # last resort: anyone available
                cands = [p for p in available if p["player_id"] not in used and (p["position_group"] != "GK" or group == "GK")]
            weights = []
            for p in cands:
                w = {"starter": 1.0, "rotation": 0.45, "fringe": 0.18}[p["squad_role"]]
                w *= math.exp(-1.3 * self.load.get(p["player_id"], 0.0))  # tired players rest
                if group == "GK":
                    w = 50.0 if p["squad_role"] == "starter" else 0.02
                elif group != "CB" and self.recent_full.get(p["player_id"], 0) >= 2:
                    w *= 0.02  # forced rotation: two near-full matches in a row
                if p["player_id"] == self.gem_id:
                    w *= 0.01  # gem starts only when planned
                if group in self.need_position.get(p["player_id"], ()) and self.matchday >= 2:
                    w *= 25.0  # a hybrid still has to play this position at least once
                elif p["position_group"] != group:  # playing the secondary position
                    w *= 0.35
                weights.append(w + 1e-6)
            p = rng.choices(cands, weights=weights)[0]
            used.add(p["player_id"])
            self._start(p, (detail, group, hx, hy))
        self.bench = [p for p in available if p["player_id"] not in used]
        for p in self.bench:
            self.rows[p["player_id"]] = dict(status="rotated", on_ms=None, off_ms=None, end_reason=None, position_detail=None, position_group_played=None)
        # 5 substitutions in 3 windows
        counts = rng.choice(S["sub_windows"])
        w1 = int(_clamp(rng.gauss(58, 6), 46, 66))
        w2 = int(_clamp(rng.gauss(70, 5), w1 + 4, 80))
        w3 = int(_clamp(rng.gauss(82, 4), w2 + 4, 89))
        self.sub_plan = list(zip((w1, w2, w3), counts))

    def abilities_for(self, pid, group):
        """Hidden abilities of a player when playing in `group`: the primary
        abilities, or a penalised copy in the secondary position."""
        ab = self.abilities[pid]
        sec = self.secondary.get(pid)
        if sec and sec["position"] == group and group != self._primary_of(pid):
            ab = dict(ab)
            for k in sec["key_abilities"]:
                ab[k] = max(5, ab[k] - sec["penalty"])
        return ab

    def _primary_of(self, pid):
        for p in self.squad:
            if p["player_id"] == pid:
                return p["position_group"]
        return None

    def can_play(self, p, group):
        return p["position_group"] == group or p.get("secondary_position") == group

    def _start(self, p, slot):
        detail, group, hx, hy = slot
        o = OnPitch(p["player_id"], group, detail, hx, hy, self.abilities_for(p["player_id"], group), 0, True)
        self.on.append(o)
        self.rows[p["player_id"]] = dict(status="started", on_ms=0, off_ms=None, end_reason=None,
                                         position_detail=detail, position_group_played=group)

    def player(self, pid):
        for o in self.on:
            if o.pid == pid:
                return o
        return None

    def pre_load(self, o):
        return self.load.get(o.pid, 0.0)

    def fatigue(self, o, ms):
        """0..1 in-match fatigue; grows with minutes on pitch, earlier for
        players carrying load from previous matches, slower for high stamina."""
        mins = (ms - o.on_ms) / 60000.0
        stam = o.ab["stamina"]
        onset = 55.0 - 12.0 * self.pre_load(o)
        f = max(0.0, (mins - onset) / 45.0) * (1.35 - 0.7 * stam / 100.0)
        return _clamp(f + 0.25 * self.pre_load(o), 0.0, 1.0)

    def pick_actor(self, x, y, exclude=None, prefer_group=None):
        """Choose the player most plausibly on the ball at (x, y) in own frame."""
        rng = self.rng
        weights, cands = [], []
        for o in self.on:
            if exclude is not None and o.pid == exclude:
                continue
            d2 = ((o.hx - x) ** 2 + (o.hy - y) ** 2)
            sigma = 20.0 if o.group != "GK" else 9.0
            w = math.exp(-d2 / (2 * sigma * sigma))
            w *= {"GK": 0.6, "CB": 1.0, "FB": 1.1, "DM": 1.25, "CM": 1.3, "AM": 1.15, "W": 1.05, "ST": 0.95}[o.group]
            if prefer_group and o.group in prefer_group:
                w *= 3.0
            weights.append(w + 1e-6)
            cands.append(o)
        return rng.choices(cands, weights=weights)[0]

    def pick_defender(self, x, y, prefer_gk=False):
        """Choose a defender near the ball; (x, y) is in the *attacker's* frame."""
        mx, my = 100.0 - x, 100.0 - y
        rng = self.rng
        weights, cands = [], []
        for o in self.on:
            d2 = ((o.hx - mx) ** 2 + (o.hy - my) ** 2)
            sigma = 18.0 if o.group != "GK" else 8.0
            w = math.exp(-d2 / (2 * sigma * sigma)) * (1.0 + 0.6 * _ab(o.ab["pressing"]))
            if o.group == "GK":
                w = w * 8.0 if prefer_gk else w * 0.25
            weights.append(w + 1e-6)
            cands.append(o)
        return rng.choices(cands, weights=weights)[0]

    def pick_recipient(self, passer, x, y, long_pass):
        rng = self.rng
        weights, cands = [], []
        for o in self.on:
            if o.pid == passer.pid:
                continue
            d = math.hypot((o.hx - x) * PITCH_X, (o.hy - y) * PITCH_Y)
            if long_pass:
                w = math.exp(-((d - 38.0) ** 2) / (2 * 9.0 ** 2))
            else:
                w = math.exp(-((d - 12.0) ** 2) / (2 * 7.0 ** 2))
            forward = o.hx - x
            # directness favours forward options, possession style favours safety
            w *= math.exp(forward * (0.008 + 0.016 * self.style_dir))
            if o.group == "GK":
                w *= 0.15 if x > 35 else 0.6
            if o.hx > 66:  # who gets into shooting positions: positioning and finishing talent
                w *= math.exp(0.6 * _ab(o.ab["positioning"]) + 0.35 * _ab(o.ab["finishing"]))
            weights.append(w + 1e-6)
            cands.append(o)
        return rng.choices(cands, weights=weights)[0]

    def gk(self):
        for o in self.on:
            if o.group == "GK":
                return o
        return self.on[0]


class MatchSimulator:
    def __init__(self, match, teams, players, abilities, rng, context=None):
        self.match = match
        self.rng = rng
        context = context or {}
        tmap = {t["team_id"]: t for t in teams}
        self.home = TeamState(tmap[match["home_team_id"]], players, abilities, rng, True, context.get(match["home_team_id"], {}))
        self.away = TeamState(tmap[match["away_team_id"]], players, abilities, rng, False, context.get(match["away_team_id"], {}))
        self.injuries = []  # (team_id, player_id, severity)
        self._last_injury_check = 0
        self.events = []
        self.seq = 0
        self.possession_id = 0
        self.ms = 0
        self.period = 1
        self.period_start_ms = 0
        self.st1 = rng.randint(1, 4)
        self.st2 = rng.randint(2, 6)
        self.period_end_ms = (45 + self.st1) * 60000
        self._pending = None

    # ------------------------------------------------------------------ utils
    def opp(self, ts):
        return self.away if ts is self.home else self.home

    def clock(self):
        """(minute, second) match clock; second half starts at 45:00."""
        rel = self.ms - self.period_start_ms
        base = 0 if self.period == 1 else 45 * 60
        total = base + rel // 1000
        return int(total // 60), int(total % 60)

    def tick(self, seconds):
        self.ms += int(max(0.3, self.rng.gauss(seconds, seconds * 0.3)) * 1000)

    def emit(self, ts, etype, actor, outcome=None, x=None, y=None, **kw):
        self.seq += 1
        minute, second = self.clock()
        eid = f"{self.match['match_id']}-{self.seq:05d}"
        ev = dict(
            event_id=eid, match_id=self.match["match_id"], period=self.period,
            minute=minute, second=second, timestamp_ms=self.ms,
            possession_id=f"{self.match['match_id']}-P{self.possession_id:04d}",
            team_id=ts.tid if ts else None, player_id=actor.pid if actor else None,
            type=etype, outcome=outcome,
            x=None if x is None else round(_clamp(x, 0, 100), 1),
            y=None if y is None else round(_clamp(y, 0, 100), 1),
            end_x=None, end_y=None, pass_length_m=None, pass_height=None, body_part=None,
            under_pressure=False, recipient_id=None, xg=None, ball_speed_kmh=None,
            related_event_id=None, duel_role=None, card_type=None, sub_player_in_id=None,
            is_penalty=False, score_home=self.home.goals, score_away=self.away.goals,
        )
        for k, v in kw.items():
            if k in ("end_x", "end_y") and v is not None:
                v = round(_clamp(v, 0, 100), 1)
            ev[k] = v
        self.events.append(ev)
        return ev

    def body_part(self, o, foot_bias=True):
        pref = None
        for p in self.home.squad + self.away.squad:
            if p["player_id"] == o.pid:
                pref = p["preferred_foot"]
                break
        r = self.rng.random()
        if pref == "left":
            return "left_foot" if r < 0.82 else "right_foot"
        if pref == "both":
            return "left_foot" if r < 0.5 else "right_foot"
        return "right_foot" if r < 0.82 else "left_foot"

    def game_state(self, ts):
        diff = ts.goals - self.opp(ts).goals
        minute = self.clock()[0]
        late = minute >= 60
        return diff, late

    # ------------------------------------------------------- substitutions
    def maybe_substitute(self):
        minute = self.clock()[0]
        for ts in (self.home, self.away):
            while ts.sub_plan and ts.sub_plan[0][0] <= minute and ts.subs_done < 5 and ts.windows_used < 3:
                _, count = ts.sub_plan.pop(0)
                self.sub_window(ts, count)
            # the gem comes on in the second half when planned and not yet used
            if (ts.gem_sub_in and ts.sub_plan and minute >= 60 and ts.subs_done < 5
                    and any(p["player_id"] == ts.gem_id for p in ts.bench)):
                pass  # handled inside sub_window via priority

    def sub_window(self, ts, count, forced_out=None, reason="substituted"):
        """One substitution window: `count` changes at the same moment."""
        if ts.subs_done >= 5 or ts.windows_used >= 3:
            return False
        ts.windows_used += 1
        made = 0
        for i in range(count):
            if ts.subs_done >= 5:
                break
            out = forced_out if (i == 0 and forced_out is not None) else None
            if self.do_sub(ts, out, reason if out is not None else "substituted"):
                made += 1
        if made:
            self.tick(S["t_substitution"])
        return made > 0

    def do_sub(self, ts, out=None, reason="substituted"):
        rng = self.rng
        if out is None:
            outfield = [o for o in ts.on if o.group != "GK" and o.started]  # substitutes are not taken off again
            if not outfield:
                return False
            minute = self.clock()[0]
            weights = []
            for o in outfield:
                w = 0.25 + 1.2 * self.fatigue_of(ts, o) + 0.8 * ts.pre_load(o) + (0.6 if o.yellows else 0) + rng.random() * 0.5
                if o.pid == ts.gem_id and minute >= 58:
                    w += 6.0  # the young gem is protected: off in the first window after about an hour
                if o.group == "CB":
                    w *= 0.5
                weights.append(w)
            out = rng.choices(outfield, weights=weights)[0]
        same = [p for p in ts.bench if ts.can_play(p, out.group)]
        if not same:
            near = {"GK": ["GK"], "CB": ["DM", "FB"], "FB": ["W", "CB"], "DM": ["CM", "CB"], "CM": ["DM", "AM"],
                    "AM": ["CM", "W"], "W": ["AM", "ST", "FB"], "ST": ["W", "AM"]}[out.group]
            same = [p for p in ts.bench if p["position_group"] in near]
        if not same:
            same = [p for p in ts.bench if p["position_group"] != "GK"] if out.group != "GK" else []
        if not same:
            return False
        def pri(p):
            base = {"starter": 0.0, "rotation": 0.6, "fringe": 1.4}[p["squad_role"]] + ts.load.get(p["player_id"], 0.0)
            if p["player_id"] == ts.gem_id:
                base += -3.0 if ts.gem_sub_in else 3.0  # the gem comes on only when planned
            if out.group in ts.need_position.get(p["player_id"], ()) and ts.matchday >= 2:
                base -= 2.5  # a hybrid still has to play this position at least once
            elif p["position_group"] != out.group:  # would play the secondary position
                base += 0.8
            return base + rng.random() * 0.9
        same.sort(key=pri)
        inp = same[0]
        ts.bench.remove(inp)
        self._leave(ts, out, reason)
        new = OnPitch(inp["player_id"], out.group, out.detail, out.hx, out.hy, ts.abilities_for(inp["player_id"], out.group), self.ms, False)
        ts.on.append(new)
        ts.rows[inp["player_id"]] = dict(status="sub_in", on_ms=self.ms, off_ms=None, end_reason=None,
                                         position_detail=out.detail, position_group_played=out.group)
        ts.subs_done += 1
        self.emit(ts, "substitution", out, outcome="success", x=0, y=50, sub_player_in_id=inp["player_id"])
        return True

    def _leave(self, ts, o, reason):
        o.off_ms = self.ms
        ts.on.remove(o)
        ts.log.append(o)
        ts.rows[o.pid]["off_ms"] = self.ms
        ts.rows[o.pid]["end_reason"] = reason

    def fatigue_of(self, ts, o):
        return ts.fatigue(o, self.ms)

    def send_off(self, ts, o):
        self._leave(ts, o, "red_card")
        ts.men = len(ts.on)

    def maybe_injury(self):
        """Random knocks: minor (misses next match) or major (out for the tournament).
        The injured player is substituted if a window is still available;
        otherwise the team carries on a player short."""
        rng = self.rng
        dt_min = (self.ms - self._last_injury_check) / 60000.0  # rates are per player per 90 minutes
        self._last_injury_check = self.ms
        if dt_min <= 0:
            return
        for ts in (self.home, self.away):
            for o in list(ts.on):
                if o.pid == ts.gem_id:
                    continue  # the hidden gem never gets injured (so the scouting story has enough minutes)
                r = rng.random()
                p_minor = S["p_injury_minor"] / 90.0 * dt_min * (1 + 1.5 * self.fatigue_of(ts, o))
                p_major = S["p_injury_major"] / 90.0 * dt_min * (1 + 1.5 * self.fatigue_of(ts, o))
                if r < p_minor + p_major:
                    sev = "major" if r < p_major else "minor"
                    self.emit(ts, "injury", o, outcome=sev, x=o.hx, y=o.hy)
                    self.injuries.append((ts.tid, o.pid, sev))
                    if ts.subs_done < 5 and ts.windows_used < 3:
                        count = 1
                        if ts.sub_plan and ts.sub_plan[0][0] - self.clock()[0] <= 6:
                            count = ts.sub_plan.pop(0)[1]  # merge with the upcoming planned window
                        self.sub_window(ts, count, forced_out=o, reason="injury")
                    else:
                        self._leave(ts, o, "injury")
                        ts.men = len(ts.on)
                    self.tick(45.0)
                    return

    # ---------------------------------------------------------------- flow
    def run(self):
        # kickoff of first half: home team
        self.play_half(self.home)
        # second half
        self.period = 2
        self.period_start_ms = self.ms
        self.period_end_ms = self.ms + (45 + self.st2) * 60000
        self.play_half(self.away)
        # close lineups
        for ts in (self.home, self.away):
            for o in list(ts.on):
                self._leave(ts, o, "full_time")
        return self.events

    def play_half(self, kickoff_team):
        self.new_possession(kickoff_team)
        actor = kickoff_team.pick_actor(50, 50, prefer_group=("ST", "AM"))
        self.emit(kickoff_team, "kickoff", actor, outcome="success", x=50, y=50)
        self.tick(S["t_kickoff"])
        ts, x, y = kickoff_team, 48.0, 50.0
        while self.ms < self.period_end_ms:
            self.maybe_substitute()
            self.maybe_injury()
            ts, x, y = self.play_possession(ts, x, y)

    def new_possession(self, ts):
        self.possession_id += 1

    def turnover(self, ts, x, y, restart=None):
        """Possession switches to the opponent at the mirrored location."""
        opp = self.opp(ts)
        self.new_possession(opp)
        self.emit(opp, "possession_change", None, x=100 - x, y=100 - y)
        return opp, 100.0 - x, 100.0 - y

    # ----------------------------------------------------------- possession
    def play_possession(self, ts, x, y):
        """Play one possession chain starting at (x, y) in ts's frame.
        Returns (team_in_possession, x, y) for the next possession."""
        rng = self.rng
        opp = self.opp(ts)
        actor = ts.pick_actor(x, y)
        n_actions = 0
        while self.ms < self.period_end_ms:
            n_actions += 1
            diff, late = self.game_state(ts)
            # ----- pressure from the defending team
            press = opp.style_press * S["pressing_scale"]
            if diff < 0:  # opponent leading -> opponent presses less
                press *= (1 - S["leading_pressing_cut"])
            zone_f = 1.25 if x < 45 else (1.0 if x < 70 else 0.75)
            p_press = S["p_pressure_base"] * (0.55 + press) * zone_f
            if len(opp.on) < 11:
                p_press *= 0.75  # a team with ten men presses less
            under_pressure = rng.random() < p_press
            if under_pressure:
                d = opp.pick_defender(x, y)
                self.emit(opp, "pressure", d, outcome="success", x=100 - x, y=100 - y)
                self.tick(S["t_pressure"])
            # ----- choose action
            xg_here = shot_xg(x, y, "right_foot", under_pressure) if x > 62 else 0.0
            p_shot = 0.0
            if x > 62:
                dm = _ab(actor.ab["decision_making"])
                p_shot = (S["p_shot_base"] * (0.1 + 0.9 * (x - 62) / 38) * (1 - 0.45 * dm)
                          + S["shot_xg_scale"] * xg_here * (1 + 0.8 * dm))  # good decision makers pick their shots
                if diff < 0 and late:
                    p_shot *= (1 + S["trailing_shot_bonus"])
                if actor.group in ("GK", "CB"):
                    p_shot *= 0.5
                p_shot *= 1 + S["possession_shot_bonus"] * (ts.style_pos - 0.5)  # possession teams finish their build-up
                if len(ts.on) < 11:
                    p_shot *= S["ten_men_shot_factor"]
                if len(opp.on) < 11:
                    p_shot *= S["ten_men_opp_shot_factor"]
            p_clear = S["p_clearance_own_third"] if (x < 25 and under_pressure) else (0.015 if x < 30 else 0.0)
            p_pass = S["p_pass"] + S["possession_pass_bonus"] * (ts.style_pos - 0.5) * 2
            p_carry = S["p_carry"] - S["possession_pass_bonus"] * (ts.style_pos - 0.5) * 2
            p_drib = S["p_dribble"] * (2.2 if x > 60 else 0.5)
            if actor.group == "GK":
                p_carry *= 0.3
                p_drib = 0.0
            r = rng.random() * (p_shot + p_clear + p_pass + p_carry + p_drib)
            if r < p_shot:
                return self.do_shot(ts, actor, x, y, under_pressure)
            r -= p_shot
            if r < p_clear:
                return self.do_clearance(ts, actor, x, y, under_pressure)
            r -= p_clear
            if r < p_drib:
                ok, actor, x, y, res = self.do_dribble(ts, actor, x, y, under_pressure)
                if not ok:
                    return res
                continue
            r -= p_drib
            if r < p_carry:
                ok, actor, x, y, res = self.do_carry(ts, actor, x, y, under_pressure, diff, late)
                if not ok:
                    return res
                continue
            ok, actor, x, y, res = self.do_pass(ts, actor, x, y, under_pressure, diff, late)
            if not ok:
                return res
        return ts, x, y

    # --------------------------------------------------------------- actions
    def do_pass(self, ts, actor, x, y, under_pressure, diff, late, restart=None):
        rng = self.rng
        opp = self.opp(ts)
        directness = ts.style_dir + (S["trailing_direct_bonus"] if (diff < 0 and late) else 0)
        p_long = S["p_long"] + S["directness_long_scale"] * (directness - 0.5) * 2
        if x < 30:
            p_long *= 1.6
        elif x > 70:
            p_long *= 0.55
        if actor.group == "GK":
            p_long = 0.30
        long_pass = rng.random() < p_long
        rcpt = ts.pick_recipient(actor, x, y, long_pass)
        ex = _clamp(rcpt.hx + rng.gauss(0, 4), 0, 100)
        ey = _clamp(rcpt.hy + rng.gauss(0, 5), 0, 100)
        if ex > 66:  # creative passers find the receiver closer to goal and more central
            cre = 0.5 * _ab(actor.ab["passing"]) + 0.5 * _ab(actor.ab["decision_making"])
            ex = _clamp(ex + 3.0 * cre, 0, 99)
            ey = _clamp(ey + (50.0 - ey) * 0.12 * cre, 0, 100)
        length = dist_m(x, y, ex, ey)
        is_long = length > 30.0
        cross = x > 72 and (y < 22 or y > 78) and ex > 83 and 25 < ey < 75
        if cross and rng.random() < 0.5:
            ey = 50 + rng.gauss(0, 7)
            ex = 90 + rng.gauss(0, 3)
            length = dist_m(x, y, ex, ey)
        if is_long or cross:
            height = rng.choices(["high", "low", "ground"], weights=[0.72, 0.18, 0.10])[0]
        else:
            height = rng.choices(["ground", "low", "high"], weights=[0.84, 0.11, 0.05])[0]
        body = "head" if (height == "high" and rng.random() < 0.04) else self.body_part(actor)
        speed = round(_clamp(rng.gauss(38 + 0.55 * length, 6), 18, 85), 1)
        # success probability
        logit = S["logit_long"] if is_long else S["logit_short"]
        logit += S["k_passing"] * _ab(actor.ab["passing"]) + 0.25 * _ab(actor.ab["decision_making"])
        logit -= S["pressure_penalty"] if under_pressure else 0.0
        logit -= S["progression_penalty"] * max(0.0, ex - x)
        logit += S["possession_bonus"] * (ts.style_pos - 0.5) * 2
        logit += S["zone_slope"] * (50.0 - ex)  # passes are safer deep in own half, riskier near the opponent's goal
        if ex > 66:
            logit += 0.5 * _ab(actor.ab["decision_making"])  # final-third passes depend on decision making too
        if cross:
            logit -= 0.9
        logit -= S["fatigue_penalty"] * self.fatigue_of(ts, actor) * 3
        logit += 0.25 * _ab(rcpt.ab["positioning"])
        if len(ts.on) < 11:
            logit -= S["ten_men_pass_penalty"]  # fewer passing options with ten men
        p_ok = _sig(logit)
        aerial = height == "high" and rng.random() < S["p_aerial_on_high"]
        etype = restart or "pass"
        ev = self.emit(ts, etype, actor, outcome=None, x=x, y=y, end_x=ex, end_y=ey,
                       pass_length_m=round(length, 1), pass_height=height, body_part=body,
                       under_pressure=under_pressure, recipient_id=rcpt.pid, ball_speed_kmh=speed)
        self.tick(S["t_pass"] + length / 20.0)
        # offside on forward passes into the final third
        if ex > 72 and ex - x > 8 and rcpt.group in ("ST", "W", "AM") and rng.random() < S["p_offside"]:
            ev["outcome"] = "fail"
            off = self.emit(ts, "offside", rcpt, outcome="fail", x=ex, y=ey, related_event_id=ev["event_id"])
            ev["related_event_id"] = off["event_id"]
            self.tick(S["t_free_kick"])
            opp, nx, ny = self.turnover(ts, ex, ey)
            return False, None, None, None, self.restart_free_kick(opp, nx, ny, direct=False)
        if aerial:
            won = self.aerial_duel(ts, rcpt, ex, ey, ev, p_ok)
            pending = self._pending
            if pending is not None:
                # defender fouled in the air -> set piece already generated
                self._pending = None
                ev["outcome"] = "success"
                return False, None, None, None, pending
            if won:
                ev["outcome"] = "success"
                return True, rcpt, ex, ey, None
            ev["outcome"] = "fail"
            return False, None, None, None, self.loose_ball(opp, ts, ex, ey, ev)
        if rng.random() < p_ok:
            ev["outcome"] = "success"
            return True, rcpt, ex, ey, None
        ev["outcome"] = "fail"
        return False, None, None, None, self.failed_pass(ts, ev, ex, ey)

    def failed_pass(self, ts, ev, ex, ey):
        """Resolve a failed pass: interception, clearance, out of play or loose ball."""
        rng = self.rng
        opp = self.opp(ts)
        r = rng.random()
        if ex > 85 and r < S["p_corner_after_box_fail"]:
            return self.restart_corner(ts)
        p_int = S["p_fail_interception"] * (0.080 + 1.5 * (ex / 100.0) ** 2)
        if ex < 50:  # interceptions in the passer's own half need a high-pressing opponent
            p_int *= (0.35 + 0.65 * opp.style_press) / 0.75
        if r < p_int:
            d = opp.pick_defender(ex, ey)
            ie = self.emit(opp, "interception", d, outcome="success", x=100 - ex, y=100 - ey,
                           related_event_id=ev["event_id"])
            self.tick(S["t_duel"])
            o, nx, ny = self.turnover(ts, ex, ey)
            return o, nx, ny
        r -= S["p_fail_interception"]
        if r < S["p_fail_clearance"] or (ex > 80 and r < S["p_fail_clearance"] * 2):
            d = opp.pick_defender(ex, ey)
            return self.clearance_by(opp, d, 100 - ex, 100 - ey, ev)
        r -= S["p_fail_clearance"]
        if r < S["p_fail_out"]:
            # ball out of play -> throw-in for the opponent
            self.tick(S["t_throw_in"])
            o, nx, ny = self.turnover(ts, ex, ey)
            return self.restart_throw_in(o, nx, ny)
        return self.loose_ball(opp, ts, ex, ey, ev)

    def loose_ball(self, winner_pref, loser, x, y, related):
        """Loose ball after a failed action; the opponent usually recovers."""
        rng = self.rng
        opp = self.opp(loser)
        if rng.random() < 0.70:
            d = opp.pick_defender(x, y)
            self.emit(opp, "ball_recovery", d, outcome="success", x=100 - x, y=100 - y,
                      related_event_id=related["event_id"] if related else None)
            self.tick(S["t_duel"])
            return self.turnover(loser, x, y)
        a = loser.pick_actor(x, y)
        self.emit(loser, "ball_recovery", a, outcome="success", x=x, y=y)
        self.tick(S["t_duel"])
        return loser, x, y

    def aerial_duel(self, ts, rcpt, ex, ey, pass_ev, p_pass_ok):
        """Two aerial_duel events (one per player). Returns True if attacker wins."""
        rng = self.rng
        opp = self.opp(ts)
        d = opp.pick_defender(ex, ey)
        logit = 0.0 + 0.9 * (_ab(rcpt.ab["aerial"]) - _ab(d.ab["aerial"])) - 0.25
        logit += 0.4 * (p_pass_ok - 0.5)
        neutral = rng.random() < S["p_aerial_neutral"]
        won = (not neutral) and rng.random() < _sig(logit)
        d_won = (not neutral) and (not won)
        a_ev = self.emit(ts, "aerial_duel", rcpt, outcome="success" if won else "fail", x=ex, y=ey,
                         body_part="head", duel_role="offensive", related_event_id=pass_ev["event_id"])
        d_ev = self.emit(opp, "aerial_duel", d, outcome="success" if d_won else "fail", x=100 - ex, y=100 - ey,
                         body_part="head", duel_role="defensive", related_event_id=a_ev["event_id"])
        a_ev["related_event_id"] = d_ev["event_id"]
        self.tick(S["t_duel"])
        if not won and rng.random() < 0.06:
            # defender foul in the air
            return self._foul_result(opp, d, ts, rcpt, ex, ey, d_ev)
        return won

    def do_carry(self, ts, actor, x, y, under_pressure, diff, late):
        rng = self.rng
        opp = self.opp(ts)
        fwd = rng.gauss(7.0, 4.0) * (1 + 0.5 * _ab(actor.ab["ball_carrying"]))
        if x > 85:
            fwd *= 0.4
        ex = _clamp(x + fwd, 0, 100)
        ey = _clamp(y + rng.gauss(0, 5), 0, 100)
        length = dist_m(x, y, ex, ey)
        ev = self.emit(ts, "carry", actor, outcome="success", x=x, y=y, end_x=ex, end_y=ey,
                       under_pressure=under_pressure)
        self.tick(S["t_carry"] * (0.5 + length / 10.0))
        # a defender may challenge the carrier
        zone = 0.05 + S["challenge_zone_scale"] * (ex / 100.0) ** 3.2  # more challenges closer to the defender's goal
        p_ch = S["p_carry_challenge"] * zone * (0.7 + 0.6 * opp.style_press)
        if ex < 50:  # carrier in own half -> mainly a high-pressing opponent challenges here
            p_ch *= S["high_press_scale"] * (0.35 + 0.65 * opp.style_press) / 0.75
        if under_pressure:
            p_ch *= 1.5
        if rng.random() < p_ch:
            d = opp.pick_defender(ex, ey)
            logit = S["logit_defender_wins"] + S["k_tackling"] * _ab(d.ab["tackling"]) - S["k_carrying"] * _ab(actor.ab["ball_carrying"])
            logit += S["fatigue_penalty"] * 3 * (self.fatigue_of(ts, actor) - self.fatigue_of(opp, d))
            def_wins = rng.random() < _sig(logit)
            foul = rng.random() < S["p_foul_in_duel"] * (0.5 if ex > 83 else 1.0)
            t_ev = self.emit(opp, "tackle", d, outcome="success" if (def_wins and not foul) else "fail",
                             x=100 - ex, y=100 - ey, duel_role="defensive", related_event_id=ev["event_id"])
            a_ev = self.emit(ts, "ground_duel", actor, outcome="fail" if (def_wins and not foul) else "success",
                             x=ex, y=ey, duel_role="offensive", related_event_id=t_ev["event_id"])
            self.tick(S["t_duel"])
            if foul:
                return False, None, None, None, self.foul(opp, d, ts, actor, ex, ey, t_ev)
            if def_wins:
                ev["outcome"] = "fail"
                if rng.random() < 0.5:
                    return False, None, None, None, self.loose_ball(opp, ts, ex, ey, t_ev)
                return False, None, None, None, self.turnover(ts, ex, ey)
        return True, actor, ex, ey, None

    def do_dribble(self, ts, actor, x, y, under_pressure):
        """Take-on: attacker 'dribble' vs defender 'ground_duel'."""
        rng = self.rng
        opp = self.opp(ts)
        d = opp.pick_defender(x, y)
        logit = math.log(S["p_dribble_success"] / (1 - S["p_dribble_success"]))
        logit += 0.9 * _ab(actor.ab["ball_carrying"]) + 0.4 * _ab(actor.ab["pace"]) - 0.9 * _ab(d.ab["tackling"])
        success = rng.random() < _sig(logit)
        foul = (not success) and rng.random() < S["p_foul_in_duel"] * 1.3 * (0.5 if x > 83 else 1.0)
        a_foul = success and rng.random() < 0.03
        ex = _clamp(x + rng.gauss(6, 3), 0, 100)
        ey = _clamp(y + rng.gauss(0, 6), 0, 100)
        d_ev = self.emit(ts, "dribble", actor, outcome="success" if success else "fail", x=x, y=y, end_x=ex, end_y=ey,
                         under_pressure=under_pressure, duel_role="offensive")
        g_ev = self.emit(opp, "ground_duel", d, outcome="fail" if success else "success", x=100 - x, y=100 - y,
                         duel_role="defensive", related_event_id=d_ev["event_id"])
        d_ev["related_event_id"] = g_ev["event_id"]
        self.tick(S["t_dribble"])
        if foul:
            d_ev["outcome"] = "success"  # fouled while dribbling: the take-on counts as won (common event-data convention)
            g_ev["outcome"] = "fail"
            return False, None, None, None, self.foul(opp, d, ts, actor, x, y, g_ev)
        if a_foul:
            return False, None, None, None, self.foul(ts, actor, opp, d, x, y, d_ev)
        if success:
            return True, actor, ex, ey, None
        if rng.random() < 0.5:
            return False, None, None, None, self.loose_ball(opp, ts, x, y, g_ev)
        return False, None, None, None, self.turnover(ts, x, y)

    def do_shot(self, ts, actor, x, y, under_pressure, is_penalty=False, is_free_kick=False):
        rng = self.rng
        opp = self.opp(ts)
        if not is_penalty and not is_free_kick:
            fin = _ab(actor.ab["finishing"])
            x = _clamp(x + 2.5 * fin, 0, 99)                 # a better finisher creates a better shooting spot
            y = _clamp(y + (50.0 - y) * 0.15 * fin, 0, 100)
        is_header = (not is_penalty) and (not is_free_kick) and x > 88 and rng.random() < 0.18
        body = "head" if is_header else self.body_part(actor)
        xg = shot_xg(x, y, body, under_pressure, is_header, is_penalty)
        if is_penalty:
            xg = 0.76
        p_goal = _clamp(xg * S["goal_overperformance"] * (1 + 0.05 * _ab(actor.ab["finishing"])), 0.01, 0.95)
        r = rng.random()
        gk = opp.gk()
        if r < p_goal:
            outcome = "goal"
        else:
            # remaining shots: on target (saved), blocked, off target
            p_saved = _clamp((S["p_on_target"] - p_goal) / (1 - p_goal), 0.05, 0.6)
            r2 = rng.random()
            if r2 < p_saved:
                outcome = "saved"
            elif r2 < p_saved + (1 - p_saved) * S["p_blocked_share"] * (0.0 if (is_penalty) else 1.0) * (0.6 if is_free_kick else 1.0):
                outcome = "blocked"
            else:
                outcome = "off_target"
        if is_header:
            speed = round(_clamp(rng.gauss(45, 8), 25, 70), 1)
        else:
            speed = round(_clamp(rng.gauss(85, 12), 60, 110), 1)
        ev = self.emit(ts, "shot", actor, outcome=outcome, x=x, y=y, end_x=100, end_y=50 + rng.gauss(0, 4),
                       body_part=body, under_pressure=under_pressure, xg=xg, ball_speed_kmh=speed, is_penalty=is_penalty)
        self.tick(S["t_shot"])
        if outcome == "goal":
            ts.goals += 1
            ev["score_home"], ev["score_away"] = self.home.goals, self.away.goals
            self.tick(S["t_goal"])
            # kickoff by the conceding team
            self.new_possession(opp)
            k = opp.pick_actor(50, 50, prefer_group=("ST", "AM"))
            self.emit(opp, "kickoff", k, outcome="success", x=50, y=50)
            self.tick(S["t_kickoff"])
            return opp, 48.0, 50.0
        if outcome == "saved":
            s_ev = self.emit(opp, "save", gk, outcome="success", x=100 - x, y=100 - y, related_event_id=ev["event_id"])
            ev["related_event_id"] = s_ev["event_id"]
            self.tick(S["t_duel"])
            r3 = rng.random()
            if r3 < S["p_corner_after_save"]:
                return self.restart_corner(ts)
            if r3 < 0.72:
                # keeper holds -> goalkeeper distribution
                self.tick(S["t_goal_kick"])
                o, nx, ny = self.turnover(ts, 95, 50)
                return o, 6.0, 50.0
            return self.loose_ball(opp, ts, x - 6, y, s_ev)
        if outcome == "blocked":
            d = opp.pick_defender(x, y)
            b_ev = self.emit(opp, "clearance", d, outcome="success", x=100 - x + 2, y=100 - y, related_event_id=ev["event_id"])
            self.tick(S["t_duel"])
            if rng.random() < S["p_corner_after_block"]:
                return self.restart_corner(ts)
            return self.loose_ball(opp, ts, x - 8, y, b_ev)
        # off target -> goal kick (goalkeeper restarts play)
        self.tick(S["t_goal_kick"])
        o, nx, ny = self.turnover(ts, 95, 50)
        return o, 6.0, 50.0

    def do_clearance(self, ts, actor, x, y, under_pressure):
        return self.clearance_by(ts, actor, x, y, None, under_pressure)

    def clearance_by(self, ts, actor, x, y, related, under_pressure=False):
        """Clearance by ts at (x, y) in ts's frame. Ball goes long and is usually lost."""
        rng = self.rng
        opp = self.opp(ts)
        ex = _clamp(x + rng.gauss(35, 10), 0, 100)
        ey = _clamp(rng.gauss(50, 25), 0, 100)
        ev = self.emit(ts, "clearance", actor, outcome="success", x=x, y=y, end_x=ex, end_y=ey,
                       under_pressure=under_pressure, related_event_id=related["event_id"] if related else None)
        self.tick(S["t_pass"] + 1.5)
        r = rng.random()
        if r < S["p_corner_after_clearance"] and x < 20:
            return self.restart_corner(opp)
        if r < 0.45:
            self.tick(S["t_throw_in"])
            o, nx, ny = self.turnover(ts, ex, ey)
            return self.restart_throw_in(o, nx, ny)
        if r < 0.75:
            return self.turnover(ts, ex, ey)
        a = ts.pick_actor(ex, ey)
        self.emit(ts, "ball_recovery", a, outcome="success", x=ex, y=ey)
        return ts, ex, ey

    # ------------------------------------------------------------------ fouls
    def foul(self, fouling_ts, fouler, fouled_ts, fouled, x, y, related):
        """x, y in the fouled team's frame. Emits foul (+card) and the free kick."""
        f_ev = self.emit(fouling_ts, "foul", fouler, outcome="fail", x=100 - x, y=100 - y,
                         related_event_id=related["event_id"] if related else None)
        rng = self.rng
        minute = self.clock()[0]
        p_y = S["p_yellow"] + (S["p_yellow_late_bonus"] if minute > 70 else 0)
        if x > 60:
            p_y += 0.05  # tactical / cynical fouls near own goal
        if fouler.yellows >= 1:
            p_y *= 0.4  # booked players foul more carefully; referees are slower to show a second yellow
        if fouler.pid == fouling_ts.gem_id:
            pass  # the hidden gem is never booked, so he cannot be suspended
        elif rng.random() < S["p_straight_red"]:
            self.emit(fouling_ts, "card", fouler, outcome="red", x=100 - x, y=100 - y, card_type="straight_red",
                      related_event_id=f_ev["event_id"])
            self.send_off(fouling_ts, fouler)
        elif rng.random() < p_y:
            fouler.yellows += 1
            if fouler.yellows >= 2:
                self.emit(fouling_ts, "card", fouler, outcome="red", x=100 - x, y=100 - y, card_type="second_yellow",
                          related_event_id=f_ev["event_id"])
                self.send_off(fouling_ts, fouler)
            else:
                self.emit(fouling_ts, "card", fouler, outcome="yellow", x=100 - x, y=100 - y, card_type="yellow",
                          related_event_id=f_ev["event_id"])
        self.tick(S["t_free_kick"])
        self.new_possession(fouled_ts)
        # fouls inside the box are rarely penalised (defenders are careful; ~0.25 penalties per match)
        in_box = x > 83.5 and 20 < y < 80 and rng.random() < 0.15
        if in_box:
            return self.restart_penalty(fouled_ts, f_ev)
        return self.restart_free_kick(fouled_ts, x, y, direct=(x > 65 and 25 < y < 75), related=f_ev)

    def _foul_result(self, fouling_ts, fouler, fouled_ts, fouled, x, y, related):
        # aerial foul: treat like a normal foul, attacker keeps possession via free kick
        self._pending = self.foul(fouling_ts, fouler, fouled_ts, fouled, x, y, related)
        return True  # attacker "wins" (keeps the ball via the set piece)

    # --------------------------------------------------------------- restarts
    def restart_free_kick(self, ts, x, y, direct, related=None):
        rng = self.rng
        taker = ts.pick_actor(x, y, prefer_group=("CM", "AM", "DM"))
        if direct and rng.random() < 0.25:
            ev = self.emit(ts, "free_kick", taker, outcome="success", x=x, y=y, related_event_id=related["event_id"] if related else None)
            self.tick(1.0)
            return self.do_shot(ts, taker, x, y, False, is_free_kick=True)
        diff, late = self.game_state(ts)
        ok, actor, nx, ny, res = self.do_pass(ts, taker, x, y, False, diff, late, restart="free_kick")
        if related is not None and self.events:
            for e in reversed(self.events):
                if e["type"] == "free_kick":
                    e["related_event_id"] = related["event_id"]
                    break
        if not ok:
            return res
        return ts, nx, ny

    def restart_penalty(self, ts, related):
        taker = ts.pick_actor(88, 50, prefer_group=("ST", "AM"))
        ev = self.emit(ts, "free_kick", taker, outcome="success", x=88.6, y=50, related_event_id=related["event_id"], is_penalty=True)
        self.tick(30.0)
        return self.do_shot(ts, taker, 88.6, 50.0, False, is_penalty=True)

    def restart_throw_in(self, ts, x, y):
        rng = self.rng
        y = 0.0 if y < 50 else 100.0
        taker = ts.pick_actor(x, y, prefer_group=("FB", "W"))
        rcpt = ts.pick_recipient(taker, x, y, False)
        ex = _clamp(rcpt.hx + rng.gauss(0, 4), 0, 100)
        ey = _clamp(rcpt.hy + rng.gauss(0, 5), 0, 100)
        ok = rng.random() < 0.80
        self.emit(ts, "throw_in", taker, outcome="success" if ok else "fail", x=x, y=y, end_x=ex, end_y=ey,
                  pass_length_m=round(dist_m(x, y, ex, ey), 1), pass_height="low", body_part="other", recipient_id=rcpt.pid)
        self.tick(S["t_pass"])
        if ok:
            return ts, ex, ey
        return self.turnover(ts, ex, ey)

    def restart_corner(self, ts):
        rng = self.rng
        opp = self.opp(ts)
        self.tick(S["t_corner"])
        self.new_possession(ts)
        y = 0.0 if rng.random() < 0.5 else 100.0
        taker = ts.pick_actor(85, y, prefer_group=("W", "AM", "CM"))
        short = rng.random() < 0.15
        if short:
            rcpt = ts.pick_recipient(taker, 100, y, False)
            ex, ey = _clamp(rcpt.hx + 15, 0, 100), _clamp(y + (12 if y == 0 else -12), 0, 100)
            self.emit(ts, "corner", taker, outcome="success", x=100, y=y, end_x=ex, end_y=ey,
                      pass_length_m=round(dist_m(100, y, ex, ey), 1), pass_height="ground", body_part=self.body_part(taker),
                      recipient_id=rcpt.pid, ball_speed_kmh=round(rng.gauss(35, 5), 1))
            self.tick(S["t_pass"])
            return ts, ex, ey
        rcpt = ts.pick_actor(92, 50, prefer_group=("CB", "ST"))
        ex, ey = _clamp(92 + rng.gauss(0, 3), 0, 100), _clamp(50 + rng.gauss(0, 9), 0, 100)
        ev = self.emit(ts, "corner", taker, outcome=None, x=100, y=y, end_x=ex, end_y=ey,
                       pass_length_m=round(dist_m(100, y, ex, ey), 1), pass_height="high", body_part=self.body_part(taker),
                       recipient_id=rcpt.pid, ball_speed_kmh=round(rng.gauss(62, 6), 1))
        self.tick(S["t_pass"] + 1.5)
        won = self.aerial_duel(ts, rcpt, ex, ey, ev, 0.45)
        pending = getattr(self, "_pending", None)
        if pending is not None:
            self._pending = None
            ev["outcome"] = "success"
            return pending
        if won:
            ev["outcome"] = "success"
            if rng.random() < 0.30:
                return self.do_shot(ts, rcpt, ex, ey, True)
            return ts, ex, ey
        ev["outcome"] = "fail"
        d = opp.pick_defender(ex, ey)
        if rng.random() < 0.6:
            return self.clearance_by(opp, d, 100 - ex, 100 - ey, ev)
        return self.loose_ball(opp, ts, ex, ey, ev)


def simulate_match(match, teams, players, abilities, rng, context=None):
    """Run one match.

    Returns (events, lineup_rows, score_home, score_away, stoppage, end_ms, injuries).
    lineup_rows has one row per squad player (23 per team) with a status:
    started / sub_in / rotated (unused) / suspended / injured."""
    sim = MatchSimulator(match, teams, players, abilities, rng, context)
    events = sim.run()
    lineups = []
    for ts in (sim.home, sim.away):
        for p in ts.squad:
            r = ts.rows[p["player_id"]]
            on, off = r["on_ms"], r["off_ms"]
            lineups.append(dict(
                match_id=match["match_id"], team_id=ts.tid, player_id=p["player_id"], status=r["status"],
                position_detail=r["position_detail"], position_group_played=r.get("position_group_played"),
                on_ms=on, off_ms=off, end_reason=r["end_reason"],
                minutes_played=round((off - on) / 60000.0, 1) if on is not None else 0.0,
            ))
    return events, lineups, sim.home.goals, sim.away.goals, (sim.st1, sim.st2), sim.ms, sim.injuries
