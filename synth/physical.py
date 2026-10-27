"""Optional physical snapshots per player per 5-minute window.

These are *not* derived from events; they are plausible GPS-like numbers that
respect position profiles, hidden pace/stamina, age and in-match fatigue.
Thresholds follow the elite youth GPS literature: high-speed running
>= 19.8 km/h, sprinting >= 25.2 km/h.
"""

import random

# per-90 baselines by position_group: (total distance m, high-speed m, sprint m)
POSITION_PHYS = {
    "GK": (4800, 60, 15), "CB": (9700, 480, 150), "FB": (10500, 720, 230), "DM": (10600, 520, 150),
    "CM": (11300, 620, 180), "AM": (10400, 680, 210), "W": (10300, 820, 280), "ST": (9900, 700, 240),
}
WINDOW_MIN = 5
LOAD_PENALTY = 0.06  # output reduction per unit of accumulated load (1 unit ~ one full match not yet recovered)


def generate_snapshots(rng, match_id, lineups, players_by_id, abilities, match_end_ms, loads=None):
    """`loads` maps player_id -> accumulated fatigue load from previous matches;
    a loaded player covers less ground and reaches lower top speeds."""
    loads = loads or {}
    rows = []
    n_windows = int(match_end_ms // (WINDOW_MIN * 60000)) + 1
    for lu in lineups:
        if lu["on_ms"] is None:
            continue
        p = players_by_id[lu["player_id"]]
        load = loads.get(lu["player_id"], 0.0)
        ab = abilities[lu["player_id"]]
        base_dist, base_hsr, base_spr = POSITION_PHYS[p["position_group"]]
        stam = (ab["stamina"] - 50) / 50.0
        pace = (ab["pace"] - 50) / 50.0
        # individual multipliers
        load_f = 1.0 - LOAD_PENALTY * load
        dist_mult = (1.0 + 0.08 * stam + rng.gauss(0, 0.05)) * load_f
        hsr_mult = (1.0 + 0.18 * pace + 0.05 * stam + rng.gauss(0, 0.12)) * load_f ** 1.5
        top_speed_max = (30.0 + 2.2 * pace + rng.gauss(0, 0.6)) * (1.0 - 0.4 * LOAD_PENALTY * load)
        if p["age"] <= 16:
            top_speed_max -= 1.5
        if p["position_group"] == "GK":
            top_speed_max -= 4.0
        for w in range(n_windows):
            w_start, w_end = w * WINDOW_MIN * 60000, (w + 1) * WINDOW_MIN * 60000
            on = max(lu["on_ms"], w_start)
            off = min(lu["off_ms"], w_end, match_end_ms)
            if off <= on:
                continue
            mins = (off - on) / 60000.0
            mins_played_so_far = (on - lu["on_ms"]) / 60000.0
            fatigue = max(0.0, (mins_played_so_far - 50) / 45.0) * (0.12 - 0.06 * stam)
            f = (1 - fatigue) * (1 + rng.gauss(0, 0.10))
            dist = base_dist / 90.0 * mins * dist_mult * f
            hsr = max(0.0, base_hsr / 90.0 * mins * hsr_mult * f * (1 + rng.gauss(0, 0.35)))
            spr = max(0.0, base_spr / 90.0 * mins * hsr_mult * f * (1 + rng.gauss(0, 0.5)))
            sprints = int(round(spr / 18.0 + rng.random() * 0.8))
            top = top_speed_max * (0.80 + 0.2 * rng.random() ** 0.5) * (1 - 0.4 * fatigue)
            if sprints == 0:
                top = min(top, 24.5 + rng.random() * 2)
            rows.append(dict(
                match_id=match_id, team_id=lu["team_id"], player_id=lu["player_id"], window_index=w,
                window_start_min=w * WINDOW_MIN, minutes_in_window=round(mins, 2),
                distance_m=int(round(dist)), high_speed_distance_m=int(round(hsr)),
                sprint_distance_m=int(round(spr)), sprints=sprints, top_speed_kmh=round(top, 1),
            ))
    return rows
