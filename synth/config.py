"""Tunable parameters for squad generation and the match simulator.

Everything that influences realism lives here so calibration is a matter of
editing numbers, not logic. The values were tuned during development so that
team and match statistics look plausible for U19 football; the public checks
are in benchmarks.py and validate.py (see the README data statement).
"""

TOURNAMENT_START = "2026-03-02"  # fictional date (ISO); matches on days 1, 4, 7, 10, 13, 16
MATCHDAY_GAP_DAYS = 3
VENUE = "Hollowmere Arena (neutral venue)"
ELIGIBLE_BORN_FROM = "2008-01-01"  # U19 rule: born on or after this date
# year-based age distribution: birth year -> share (age = tournament year - birth year)
AGE_YEAR_WEIGHTS = {2008: 0.64, 2009: 0.36}  # 18 and 17 year olds; 16/15 year olds are placed explicitly
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

# --- Teams ------------------------------------------------------------------
# strength: hidden overall level; style_* in 0..1.
# T4 is the "possession" profile (Danish-like), the others are direct/pressing.
TEAM_PROFILES = {
    "T1": dict(formation="4-3-3",   strength=71, style_possession=0.50, style_pressing=0.75, style_directness=0.55),
    "T2": dict(formation="4-2-3-1", strength=70, style_possession=0.45, style_pressing=0.85, style_directness=0.60),
    "T3": dict(formation="3-5-2",   strength=65, style_possession=0.40, style_pressing=0.65, style_directness=0.70),
    "T4": dict(formation="4-4-2",   strength=66, style_possession=0.85, style_pressing=0.35, style_directness=0.30),
}

# Squad composition (23 players) per team, calibrated on 23-man tournament squads
# (squad design). Position groups: GK, CB, FB (full-backs / wing-backs),
# DM, CM, AM, W (wingers / wide midfielders), ST.
SQUAD_COMPOSITION = {
    # Every primary position exists in the team's formation (amendment of 22 Oct):
    # AM players of T1/T3/T4 became CM or W, T2's central midfielders are listed as DM
    # (the double pivot of 4-2-3-1) and T4's as CM (the two central slots of 4-4-2).
    "T1": {"GK": 3, "CB": 4, "FB": 4, "DM": 2, "CM": 4, "AM": 0, "W": 4, "ST": 2},  # 4-3-3
    "T2": {"GK": 3, "CB": 4, "FB": 4, "DM": 4, "CM": 0, "AM": 3, "W": 3, "ST": 2},  # 4-2-3-1
    "T3": {"GK": 3, "CB": 5, "FB": 4, "DM": 2, "CM": 5, "AM": 0, "W": 0, "ST": 4},  # 3-5-2, FB = wing-backs
    "T4": {"GK": 3, "CB": 4, "FB": 4, "DM": 0, "CM": 5, "AM": 0, "W": 4, "ST": 3},  # 4-4-2, W = wide midfielders
}
# Multi-positional players: realistic primary <-> secondary pairings
HYBRID_PAIRS = {
    "defensive": [("CB", "FB"), ("FB", "CB"), ("CB", "DM"), ("DM", "CB")],
    "midfield": [("CM", "DM"), ("DM", "CM")],
    "attacking": [("AM", "W"), ("W", "AM"), ("W", "ST"), ("ST", "W"), ("W", "FB"), ("FB", "W")],
}
SECONDARY_PENALTY = (3, 8)  # abilities in the secondary position are this much lower (inclusive range)

# Formation slots: (position_detail, position_group, home_x, home_y) in the
# attacking frame (0-100, attacking left -> right).
FORMATIONS = {
    "4-3-3": [
        ("GK", "GK", 6, 50), ("LB", "FB", 26, 14), ("LCB", "CB", 20, 38), ("RCB", "CB", 20, 62), ("RB", "FB", 26, 86),
        ("DM", "DM", 38, 50), ("LCM", "CM", 52, 34), ("RCM", "CM", 52, 66),
        ("LW", "W", 72, 16), ("ST", "ST", 80, 50), ("RW", "W", 72, 84),
    ],
    "4-2-3-1": [
        ("GK", "GK", 6, 50), ("LB", "FB", 26, 14), ("LCB", "CB", 20, 38), ("RCB", "CB", 20, 62), ("RB", "FB", 26, 86),
        ("LDM", "DM", 40, 40), ("RDM", "DM", 40, 60), ("LW", "W", 66, 16), ("AM", "AM", 62, 50), ("RW", "W", 66, 84),
        ("ST", "ST", 80, 50),
    ],
    "4-4-2": [
        ("GK", "GK", 6, 50), ("LB", "FB", 26, 14), ("LCB", "CB", 20, 38), ("RCB", "CB", 20, 62), ("RB", "FB", 26, 86),
        ("LM", "W", 54, 16), ("LCM", "CM", 46, 38), ("RCM", "CM", 46, 62), ("RM", "W", 54, 84),
        ("LS", "ST", 78, 40), ("RS", "ST", 78, 60),
    ],
    "3-5-2": [
        ("GK", "GK", 6, 50), ("LCB", "CB", 20, 30), ("CB", "CB", 17, 50), ("RCB", "CB", 20, 70),
        ("LWB", "FB", 42, 12), ("RWB", "FB", 42, 88), ("DM", "DM", 38, 50), ("LCM", "CM", 54, 36), ("RCM", "CM", 54, 64),
        ("LS", "ST", 78, 42), ("RS", "ST", 78, 58),
    ],
}

# position_group -> mean ability profile (before team/age/noise adjustments)
ABILITY_NAMES = ["passing", "ball_carrying", "finishing", "aerial", "tackling",
                 "positioning", "pressing", "decision_making", "pace", "stamina"]
POSITION_ABILITY_MEANS = {
    #         pass carry fin  aer  tack pos  press dec  pace stam
    "GK": [52, 30, 15, 55, 30, 62, 25, 55, 40, 50],
    "CB": [52, 42, 25, 68, 66, 62, 50, 55, 52, 58],
    "FB": [55, 56, 32, 48, 60, 56, 60, 54, 66, 66],
    "DM": [62, 50, 32, 55, 64, 62, 62, 62, 52, 66],
    "CM": [64, 58, 42, 46, 54, 58, 62, 62, 56, 70],
    "AM": [64, 64, 52, 38, 40, 54, 56, 64, 60, 62],
    "W":  [56, 66, 50, 36, 38, 50, 58, 54, 72, 64],
    "ST": [50, 56, 66, 56, 34, 56, 56, 56, 64, 60],
}
POSITION_HEIGHT_MEAN = {"GK": 186, "CB": 185, "FB": 177, "DM": 180, "CM": 178, "AM": 176, "W": 175, "ST": 181}

# --- Match simulation --------------------------------------------------------
SIM = dict(
    # time per event in seconds (mean), by type
    t_pass=1.9, t_carry=2.6, t_dribble=2.4, t_shot=1.5, t_duel=1.2, t_pressure=0.4,
    t_throw_in=14.0, t_free_kick=22.0, t_corner=28.0, t_goal=55.0, t_kickoff=4.0, t_goal_kick=16.0,
    t_substitution=20.0,
    # action selection
    p_pass=0.67, p_carry=0.26, p_dribble=0.040, p_clearance_own_third=0.09,
    possession_pass_bonus=0.09,          # possession team shifts carry -> pass by this share
    p_long=0.08, directness_long_scale=0.08,
    p_shot_base=0.18, shot_xg_scale=1.0,  # p_shot = base + scale * xg, only in shooting zone
    # pass success logits
    logit_short=1.5, logit_long=0.25, k_passing=0.75, pressure_penalty=0.55,
    progression_penalty=0.012, possession_bonus=0.38, final_third_penalty=0.0, zone_slope=0.018,
    # failed pass resolution
    p_fail_interception=1.0, p_fail_clearance=0.14, p_fail_out=0.16,
    # aerial duels
    p_aerial_on_high=0.18, p_aerial_neutral=0.10,
    # carries / duels
    p_carry_challenge=2.2, challenge_zone_scale=2.0, high_press_scale=0.34,
    logit_defender_wins=1.42, k_tackling=0.9, k_carrying=0.8,
    p_dribble_success=0.36,
    p_foul_in_duel=0.165, p_attacker_foul=0.12,
    p_yellow=0.135, p_yellow_late_bonus=0.03,
    # pressing
    p_pressure_base=0.26, pressing_scale=1.0,
    # shots
    goal_overperformance=1.13, p_on_target=0.36, p_blocked_share=0.42,
    p_corner_after_block=0.50, p_corner_after_save=0.45, p_corner_after_clearance=0.38, p_corner_after_box_fail=0.30,
    p_offside=0.045,
    # fatigue
    fatigue_penalty=0.09,
    # substitutions: 5 per match in 3 windows
    sub_windows=((1, 2, 2), (2, 2, 1), (2, 1, 2), (1, 1, 3), (1, 3, 1), (3, 1, 1)),
    # cards, injuries, fatigue across matches
    p_straight_red=0.006, p_injury_minor=0.012, p_injury_major=0.003,
    load_recovery=0.45, load_ability_penalty=0.10, load_physical_penalty=0.06,
    ten_men_pass_penalty=0.2, ten_men_shot_factor=0.8, ten_men_opp_shot_factor=1.15,
    possession_shot_bonus=-0.2,
    # game state
    trailing_shot_bonus=0.25, trailing_direct_bonus=0.12, leading_pressing_cut=0.15,
)

# Ground-truth composite per position (mean of the five most relevant hidden abilities);
# used by evaluate_scouting.py and to make sure every hidden gem is a real top-3 talent in his position.
GT_COMPOSITE = {
    "CB": ["aerial", "tackling", "positioning", "passing", "pace"],
    "FB": ["pace", "tackling", "ball_carrying", "passing", "stamina"],
    "DM": ["tackling", "passing", "positioning", "decision_making", "pressing"],
    "CM": ["passing", "decision_making", "stamina", "ball_carrying", "pressing"],
    "AM": ["passing", "ball_carrying", "decision_making", "finishing", "pace"],
    "W": ["ball_carrying", "pace", "finishing", "passing", "pressing"],
    "ST": ["finishing", "positioning", "aerial", "pace", "ball_carrying"],
}
