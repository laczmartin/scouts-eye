"""KPI catalogue and pitch geometry helpers.

Every KPI belongs to exactly one category. Per-90 KPIs are totals scaled to
90 minutes; `pct` KPIs are ratios of totals (numerator / denominator) and are
not scaled. Negative KPIs are inverted when percentiles are computed.
See docs/kpi_definitions.md for the formulas.
"""

import math

PITCH_X = 1.05  # metres per x unit (105 m pitch)
PITCH_Y = 0.68  # metres per y unit (68 m pitch)
BOX_X = 84.3    # penalty area: 16.5 m from the goal line
BOX_Y_LO, BOX_Y_HI = 20.4, 79.6
FINAL_THIRD_X = 66.7
PENALTY_XG = 0.76  # penalties are generated with a fixed xG

OUTFIELD_GROUPS = ["CB", "FB", "DM", "CM", "AM", "W", "ST"]

# category -> list of (kpi, kind) where kind is "per90" or "pct"
CATEGORIES = {
    "finishing": [("npxg", "per90"), ("shots", "per90"), ("npxg_per_shot", "ratio"),
                  ("shots_on_target_pct", "pct"), ("touches_in_box", "per90")],
    "goal_contribution": [("np_goals", "per90"), ("assists", "per90"), ("np_goals_assists", "per90")],
    "chance_creation": [("xa", "per90"), ("key_passes", "per90"), ("passes_into_box", "per90"), ("crosses_completed", "per90")],
    "passing": [("passes", "per90"), ("pass_accuracy_pct", "pct"), ("pass_accuracy_under_pressure_pct", "pct"),
                ("long_pass_accuracy_pct", "pct"), ("turnovers", "per90")],
    "progression": [("progressive_passes", "per90"), ("progressive_carries", "per90"), ("deep_progressions", "per90"),
                    ("xg_buildup", "per90")],
    "offensive_duels": [("offensive_duels", "per90"), ("offensive_duels_won_pct", "pct"), ("dribbles_completed", "per90")],
    "defensive_duels": [("defensive_duels", "per90"), ("defensive_duels_won_pct", "pct"), ("dribbled_past", "per90")],
    "aerial_play": [("aerial_duels", "per90"), ("aerial_duels_won_pct", "pct"), ("aerial_duels_won", "per90")],
    "defensive_activity": [("padj_tackles_interceptions", "per90"), ("ball_recoveries", "per90"), ("blocked_shots", "per90"),
                           ("clearances", "per90")],
    "pressing": [("pressures", "per90"), ("pressures_opp_half", "per90"), ("pressure_regains", "per90")],
    "physical": [("distance_m", "per90"), ("high_speed_distance_m", "per90"), ("sprints", "per90"), ("top_speed_kmh", "max")],
}
NEGATIVE_KPIS = {"turnovers", "dribbled_past"}
# Possession adjustment (PAdj) of volume KPIs that team style distorts (docs/kpi_definitions.md):
# defensive volumes x (0.5 / opponent possession share), attacking volumes x (0.5 / own possession share).
# Percentages, ratios, goals/assists (outputs) and physical KPIs are not adjusted.
PADJ_DEFENSIVE = {"ball_recoveries", "blocked_shots", "clearances", "pressures", "pressures_opp_half", "pressure_regains",
                  "defensive_duels", "dribbled_past", "aerial_duels", "aerial_duels_won"}
PADJ_ATTACKING = {"shots", "npxg", "touches_in_box", "xa", "key_passes", "passes_into_box", "crosses_completed", "passes",
                  "turnovers", "progressive_passes", "progressive_carries", "deep_progressions", "xg_buildup",
                  "offensive_duels", "dribbles_completed"}
KPI_KIND = {k: kind for cat in CATEGORIES.values() for k, kind in cat}
ALL_KPIS = [k for cat in CATEGORIES.values() for k, _ in cat]

# denominators for pct / ratio KPIs: kpi -> (numerator counter, denominator counter)
RATIO_DEFS = {
    "npxg_per_shot": ("npxg", "np_shots"),
    "shots_on_target_pct": ("shots_on_target", "shots"),
    "pass_accuracy_pct": ("passes_completed", "passes"),
    "pass_accuracy_under_pressure_pct": ("passes_completed_under_pressure", "passes_under_pressure"),
    "long_pass_accuracy_pct": ("long_passes_completed", "long_passes"),
    "offensive_duels_won_pct": ("offensive_duels_won", "offensive_duels"),
    "defensive_duels_won_pct": ("defensive_duels_won", "defensive_duels"),
    "aerial_duels_won_pct": ("aerial_duels_won", "aerial_duels"),
}
# raw counters that are totals (per90 or max KPIs map 1:1 to counters of the same name)
INFO_COUNTERS = ["fouls", "yellow_cards", "red_cards", "penalty_goals", "penalties_taken", "tackles_interceptions"]

RELIABILITY = [(90, "very low"), (180, "low"), (360, "medium"), (float("inf"), "good")]
SHRINK_K = 270.0


def reliability_label(minutes):
    for limit, label in RELIABILITY:
        if minutes < limit:
            return label
    return "good"


def dist_to_goal_m(x, y):
    return math.hypot((100.0 - x) * PITCH_X, (50.0 - y) * PITCH_Y)


def in_box(x, y):
    return x is not None and y is not None and x >= BOX_X and BOX_Y_LO <= y <= BOX_Y_HI


def is_progressive(x, y, ex, ey):
    """Progressive pass / carry (a common public definition): the ball ends at least 30 m closer
    to goal when start and end are in the own half, 15 m when it crosses
    halves, 10 m when both are in the opponent's half."""
    if ex is None or ey is None:
        return False
    gain = dist_to_goal_m(x, y) - dist_to_goal_m(ex, ey)
    if x < 50 and ex < 50:
        return gain >= 30
    if x >= 50 and ex >= 50:
        return gain >= 10
    return gain >= 15


def is_cross(e):
    """A pass from a wide final-third zone that ends inside the penalty area."""
    return (e["type"] == "pass" and e["x"] is not None and e["x"] > 66 and (e["y"] < 21 or e["y"] > 79)
            and in_box(e["end_x"], e["end_y"]) and e["pass_height"] in ("high", "low"))


def is_penalty_shot(e):
    """Penalties are flagged explicitly in the events (`is_penalty`); the fixed xG is no longer used to detect them."""
    return e["type"] == "shot" and bool(e.get("is_penalty"))
