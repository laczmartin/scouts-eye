"""Deterministic event metrics (no AI): pass distance, direction, difficulty, a line-breaking proxy,
ball and shot speed, and short player tags at thresholds.

Everything is computed from the event fields of data/synthetic/events/*.jsonl and
physical_snapshots.csv; nothing here reads the ground truth. Coordinates are 0-100 in
the acting team's attacking frame on a 105 x 68 m pitch (see docs/kpi_definitions.md).

Pass difficulty (0-1) is a simple, documented weighted sum, not a fitted model:

    difficulty = 0.35 * L + 0.20 * F + 0.20 * P + 0.10 * H + 0.15 * B

    L = min(distance / 40 m, 1)           long passes are harder
    F = min(max(forward metres, 0) / 30, 1)  passes that gain ground are harder
    P = 1 if under pressure else 0
    H = 1 high, 0.5 low (lofted), 0 ground
    B = 1 if the pass breaks a line (proxy below), else 0

Line-breaking proxy: the data has no opponent positions, so a pass "breaks a line" when it
goes forward at least 10 m and crosses into the next third of the pitch (x = 33.3 or 66.7)
or into the penalty area from outside it.

Ball speed and shot speed are event fields of the synthetic data (ball_speed_kmh). Their
plausibility is checked in tests/test_event_metrics.py against Rađa et al. (2019): U19
players reach about 107-111 km/h with a maximal dominant-foot instep kick in a test, and
80-103 km/h is the literature range for 15-19-year-olds; match shots are usually slower.
"""

import csv
import math

PITCH_X, PITCH_Y = 105.0, 68.0
THIRD_1, THIRD_2 = 100 / 3, 200 / 3
BOX_X, BOX_Y0, BOX_Y1 = 84.3, 20.4, 79.6
W_LENGTH, W_FORWARD, W_PRESSURE, W_HEIGHT, W_LINE = 0.35, 0.20, 0.20, 0.10, 0.15
HEIGHT = {"ground": 0.0, "low": 0.5, "high": 1.0}

# player tags (short captions with a name): thresholds are design choices, documented in the README
TAG_PASS_DIFFICULTY = 0.78     # a completed pass at least this difficult (about the top 1 % of completed passes)
TAG_SHOT_KMH = 100.0           # a shot at least this fast
TAG_TOP_SPEED_KMH = 28.0       # a new match-high top speed of at least this (5-minute physical windows)
SPRINT_KMH = 25.2              # sprint threshold of the physical snapshots (Čaušević et al. 2025)
SOURCES = {
    "shot_speed": "Rađa A et al. (2019), The ball kicking speed: a new, efficient performance indicator in youth soccer. "
                  "PLoS ONE 14(5): e0217101, doi:10.1371/journal.pone.0217101 (U19 maximal dominant instep kick "
                  "about 107-111 km/h; literature range 80-103 km/h at 15-19 years)",
    "sprint": "Čaušević et al. (2025), Sensors 25(18), 5825 (sprinting >= 25.2 km/h)",
}


def _in_box(x, y):
    return x >= BOX_X and BOX_Y0 <= y <= BOX_Y1


def pass_metrics(e):
    """Metrics of one pass event (dict) or None when it has no end location."""
    if e.get("type") != "pass" or e.get("end_x") is None or e.get("x") is None:
        return None
    dx = (e["end_x"] - e["x"]) * PITCH_X / 100.0
    dy = (e["end_y"] - e["y"]) * PITCH_Y / 100.0
    distance = math.hypot(dx, dy)
    angle = math.degrees(math.atan2(dy, dx))
    direction = "forward" if abs(angle) <= 45 else ("backward" if abs(angle) >= 135 else "lateral")
    into_box = _in_box(e["end_x"], e["end_y"]) and not _in_box(e["x"], e["y"])
    crosses_third = (e["x"] < THIRD_1 <= e["end_x"]) or (e["x"] < THIRD_2 <= e["end_x"])
    line_breaking = dx >= 10.0 and (crosses_third or into_box)
    pressure = bool(e.get("under_pressure"))
    height = e.get("pass_height") or "ground"
    L = min(distance / 40.0, 1.0)
    F = min(max(dx, 0.0) / 30.0, 1.0)
    difficulty = (W_LENGTH * L + W_FORWARD * F + W_PRESSURE * (1.0 if pressure else 0.0)
                  + W_HEIGHT * HEIGHT.get(height, 0.0) + W_LINE * (1.0 if line_breaking else 0.0))
    speed = e.get("ball_speed_kmh")
    return dict(distance_m=round(distance, 1), forward_m=round(dx, 1), direction=direction, under_pressure=pressure,
                height=height, line_breaking=line_breaking, into_box=into_box, difficulty=round(difficulty, 2),
                ball_speed_kmh=speed, travel_time_s=round(distance / (speed / 3.6), 2) if speed else None,
                completed=e.get("outcome") == "success")


def shot_metrics(e):
    """Metrics of one shot event: speed, body part and distance to the goal centre."""
    if e.get("type") != "shot":
        return None
    gx, gy = 100.0, 50.0
    dist = math.hypot((gx - e["x"]) * PITCH_X / 100.0, (gy - e["y"]) * PITCH_Y / 100.0)
    return dict(shot_speed_kmh=e.get("ball_speed_kmh"), body_part=e.get("body_part"), distance_m=round(dist, 1),
                outcome=e.get("outcome"), xg=e.get("xg"), penalty=bool(e.get("is_penalty")))


def event_metrics(e):
    return pass_metrics(e) or shot_metrics(e)


def _clock(minute, period):
    base = 45 if period == 1 else 90
    return f"{base}+{minute - base}'" if minute > base else f"{minute}'"


def match_tags(events, snapshots, player_name, minute_to_tms=None, period_of_minute=None):
    """Short player tags at thresholds, in time order.

    events: the events of one match (dicts); snapshots: its rows of physical_snapshots.csv;
    player_name: pid -> name; minute_to_tms / period_of_minute: map a snapshot window end to the clock."""
    tags = []
    for e in events:
        m = pass_metrics(e)
        if m and m["completed"] and m["difficulty"] >= TAG_PASS_DIFFICULTY:
            name = player_name(e["player_id"])
            tags.append(dict(t_ms=e["timestamp_ms"], minute=e["minute"], period=e["period"], player_id=e["player_id"], team_id=e["team_id"],
                             kind="difficult_pass", value=m["difficulty"], event_id=e["event_id"],
                             detail=dict(distance_m=m["distance_m"], forward_m=m["forward_m"], under_pressure=m["under_pressure"],
                                         line_breaking=m["line_breaking"], ball_speed_kmh=m["ball_speed_kmh"]),
                             text_en=f"VERY DIFFICULT PASS – {name}, {_clock(e['minute'], e['period'])} (difficulty {m['difficulty']:.2f}, {m['distance_m']:.0f} m)",
                             text_hu=f"NAGYON NEHÉZ PASSZ – {name}, {_clock(e['minute'], e['period'])} (nehézség {m['difficulty']:.2f}, {m['distance_m']:.0f} m)"))
        s = shot_metrics(e)
        if s and s["shot_speed_kmh"] and s["shot_speed_kmh"] >= TAG_SHOT_KMH:
            name = player_name(e["player_id"])
            tags.append(dict(t_ms=e["timestamp_ms"], minute=e["minute"], period=e["period"], player_id=e["player_id"], team_id=e["team_id"],
                             kind="fast_shot", value=s["shot_speed_kmh"], event_id=e["event_id"], detail=s,
                             text_en=f"FAST SHOT – {name}, {_clock(e['minute'], e['period'])} ({s['shot_speed_kmh']:.0f} km/h)",
                             text_hu=f"ERŐS LÖVÉS – {name}, {_clock(e['minute'], e['period'])} ({s['shot_speed_kmh']:.0f} km/h)"))
    best = 0.0
    windows = {}
    for r in snapshots:   # the fastest player of each 5-minute window
        w = int(r["window_index"])
        if w not in windows or float(r["top_speed_kmh"]) > float(windows[w]["top_speed_kmh"]):
            windows[w] = r
    for w in sorted(windows):
        r = windows[w]
        top = float(r["top_speed_kmh"])
        if top >= TAG_TOP_SPEED_KMH and top > best:
            best = top
            end_min = int(float(r["window_start_min"]) + float(r["minutes_in_window"]))
            period = period_of_minute(end_min) if period_of_minute else (1 if end_min <= 45 else 2)
            name = player_name(r["player_id"])
            tags.append(dict(t_ms=minute_to_tms(end_min) if minute_to_tms else end_min * 60000, minute=end_min, period=period,
                             player_id=r["player_id"], team_id=r["team_id"], kind="top_speed", value=top, event_id=None,
                             detail=dict(window_start_min=int(float(r["window_start_min"])), sprints=int(r["sprints"]),
                                         sprint_distance_m=int(float(r["sprint_distance_m"]))),
                             text_en=f"FASTEST RUN SO FAR – {name}, {_clock(end_min, period)} ({top:.1f} km/h)",
                             text_hu=f"EDDIGI LEGGYORSABB FUTÁS – {name}, {_clock(end_min, period)} ({top:.1f} km/h)"))
    tags.sort(key=lambda t: t["t_ms"])
    return tags


def read_snapshots(match_id, path="data/synthetic/physical_snapshots.csv"):
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["match_id"] == match_id]
