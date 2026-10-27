# Scouting validation (model vs hidden ground truth)

Profiles: `data/kpi/final/player_profiles.csv` (position score from events only). Ground truth: hidden ability composite per position (mean of the five abilities most relevant to the position, listed at the end). The weights were not tuned to the ground truth.

Only ranked players (>= 180 minutes in the position, `ranking_status = ranked`) are used; 11 primary profiles are 'low_data' and excluded from rankings.

## 1. Rank correlation: position score vs ground-truth composite

| position | players | Spearman ρ |
|---|---|---|
| CB | 17 | 0.23 |
| FB | 13 | -0.02 |
| DM | 8 | -0.18 |
| CM | 11 | 0.63 |
| AM | 1 | n/a |
| W | 10 | -0.24 |
| ST | 9 | 0.33 |
| overall (within-position ranks pooled) | 68 | 0.15 |

## 2. Ranking quality by minutes / reliability

| reliability | players | Spearman ρ (within-position ranks) | mean |rank gap| (0-1) |
|---|---|---|---|
| very low | 0 | n/a | n/a |
| low | 0 | n/a | n/a |
| medium | 64 | 0.19 | 0.31 |
| good | 4 | -0.40 | 0.36 |

Rank gap = |model percent-rank − ground-truth percent-rank| within the position group; lower is better.

## 3. Hidden talents (young standouts)

| player | name | age | position | model rank in group | ground-truth rank | position score | minutes (reliability) | mean category pct vs pool |
|---|---|---|---|---|---|---|---|---|
| T1P09 | Ilyes Petrovic | 15 | FB | 1 / 13 | 2 / 13 | 64.3 | 211.5 (medium) | 64 |
| T2P12 | Dominik Novak | 16 | DM | 1 / 8 | 3 / 8 | 57.2 | 184.3 (medium) | 65 |
| T3P20 | Abdoulaye Ferris | 16 | ST | 2 / 9 | 3 / 9 | 56.5 | 222.8 (medium) | 60 |
| T4P11 | Szymon Blanchard | 15 | FB | 6 / 13 | 3 / 13 | 55.2 | 217.1 (medium) | 56 |

The model rank is the rank of the position score among the tournament's players of the same position (primary profiles); the ground-truth rank uses the hidden composite. 'Mean category pct vs pool' is the player's average category score, i.e. his standing against the reference pool of 50 fictional tournaments.

## 4. Multi-positional players: is the secondary-position drop visible?

| player | name | main profile | score | secondary profile | score | model Δ | ground-truth Δ | hidden penalty |
|---|---|---|---|---|---|---|---|---|
| T1P05 | Dimitris Vogel | CB (275.7 min) | 34.0 | DM (97.2 min) | 33.3 | -0.7 | -10.0 | 7 |
| T1P13 | Cian Dubois | DM (232.4 min) | 35.7 | CM (104.2 min) | 55.4 | +19.7 | -1.2 | 7 |
| T1P18 | Szymon Winther | W (207.5 min) | 46.0 | ST (192.8 min) | 62.3 | +16.3 | -6.8 | 4 |
| T1P20 | Mathis Byrne | W (284.3 min) | 49.5 | ST (158.4 min) | 52.3 | +2.8 | -8.8 | 8 |
| T2P05 | Felix Keller | CB (230.9 min) | 49.3 | DM (189.2 min) | 47.4 | -1.9 | -5.4 | 3 |
| T2P22 | Harry Boateng | ST (188.0 min) | 56.1 | W (94.1 min) | 44.3 | -11.8 | -6.4 | 6 |
| T4P19 | Nikos Bakker | ST (159.6 min) | 56.0 | W (155.8 min) | 44.8 | -11.2 | +7.2 | 6 |

Secondary profiles exist for 7 players (≥ 90 minutes in the second position); the sign of the model difference matches the ground-truth difference for 3 of them. Secondary profiles are low-minute samples, so this is weak evidence either way.

## 5. Diagnostics: where is the signal lost?

Fresh fictional squads from 12 squad seeds (2000-2011), each simulated for 6, 12, 24 and 38 matches per team (consecutive tournaments with the same squads; suspensions, fatigue and the gem plan restart every 6 matches). Profiles use the same reference pool, weights and shrinkage as the real pipeline; only ranked primary profiles (>= 180 min) are used. Spearman ρ is computed per position with all squad seeds pooled.

### 5a. Sample-size curve: position score vs ground-truth composite

| position | 6 matches | 12 matches | 24 matches | 38 matches |
|---|---|---|---|---|
| CB | 0.37 (n=196) | 0.43 (n=212) | 0.46 (n=212) | 0.49 (n=215) |
| FB | 0.21 (n=176) | 0.40 (n=196) | 0.46 (n=192) | 0.46 (n=191) |
| DM | 0.45 (n=72) | 0.65 (n=88) | 0.69 (n=92) | 0.75 (n=89) |
| CM | 0.57 (n=129) | 0.62 (n=164) | 0.61 (n=165) | 0.63 (n=165) |
| AM | 0.48 (n=15) | 0.52 (n=31) | 0.69 (n=35) | 0.80 (n=34) |
| W | 0.39 (n=125) | 0.48 (n=132) | 0.49 (n=133) | 0.49 (n=136) |
| ST | 0.45 (n=112) | 0.54 (n=130) | 0.60 (n=131) | 0.63 (n=130) |

### 5b. Category scores vs the hidden abilities mapped to them

Mapping: finishing ← finishing; goal_contribution ← finishing, decision_making; chance_creation ← passing, decision_making; passing ← passing, decision_making; progression ← passing, ball_carrying; offensive_duels ← ball_carrying, pace; defensive_duels ← tackling, positioning; aerial_play ← aerial; defensive_activity ← tackling, positioning, pressing; pressing ← pressing, stamina; physical ← stamina, pace.

Spearman ρ with 6 matches per team:

| category | CB | FB | DM | CM | AM | W | ST |
|---|---|---|---|---|---|---|---|
| finishing | -0.11 | -0.06 | -0.09 | -0.01 | -0.38 | 0.20 | 0.30 |
| goal_contribution | -0.09 | -0.14 | -0.28 | -0.10 | -0.06 | -0.05 | 0.27 |
| chance_creation | -0.03 | -0.06 | -0.06 | 0.31 | 0.73 | 0.08 | -0.15 |
| passing | 0.35 | 0.37 | 0.49 | 0.41 | 0.71 | 0.30 | 0.39 |
| progression | 0.05 | 0.08 | 0.15 | 0.32 | 0.26 | 0.14 | 0.26 |
| offensive_duels | 0.31 | 0.14 | 0.41 | 0.35 | 0.08 | 0.31 | 0.31 |
| defensive_duels | 0.16 | 0.10 | 0.12 | 0.30 | 0.51 | 0.29 | 0.13 |
| aerial_play | 0.22 | -0.00 | 0.27 | 0.14 | -0.32 | 0.26 | 0.29 |
| defensive_activity | 0.31 | 0.08 | 0.14 | 0.11 | 0.23 | 0.02 | 0.29 |
| pressing | 0.31 | 0.03 | 0.32 | 0.32 | 0.16 | 0.33 | 0.35 |
| physical | 0.53 | 0.55 | 0.41 | 0.49 | 0.40 | 0.58 | 0.47 |

Spearman ρ with 38 matches per team:

| category | CB | FB | DM | CM | AM | W | ST |
|---|---|---|---|---|---|---|---|
| finishing | -0.07 | -0.04 | -0.00 | -0.00 | -0.01 | 0.29 | 0.44 |
| goal_contribution | 0.17 | -0.04 | -0.05 | 0.13 | 0.27 | 0.18 | 0.48 |
| chance_creation | 0.17 | -0.00 | 0.35 | 0.25 | 0.82 | 0.19 | 0.02 |
| passing | 0.47 | 0.46 | 0.78 | 0.51 | 0.60 | 0.29 | 0.60 |
| progression | 0.34 | 0.17 | 0.54 | 0.36 | 0.61 | 0.36 | 0.30 |
| offensive_duels | 0.31 | 0.29 | 0.44 | 0.48 | 0.50 | 0.41 | 0.45 |
| defensive_duels | 0.43 | 0.39 | 0.33 | 0.53 | 0.39 | 0.29 | 0.39 |
| aerial_play | 0.31 | 0.20 | 0.46 | 0.33 | -0.02 | 0.34 | 0.49 |
| defensive_activity | 0.37 | 0.16 | 0.42 | 0.41 | 0.42 | 0.30 | 0.46 |
| pressing | 0.51 | 0.16 | 0.44 | 0.35 | 0.66 | 0.42 | 0.37 |
| physical | 0.69 | 0.73 | 0.65 | 0.74 | 0.66 | 0.73 | 0.64 |

### 5c. Team effect on the position score

η² = share of the position-score variance explained by the team (squad seed × team); ρ(strength) = Spearman with the hidden team strength; within-team ρ = Spearman with the ground-truth composite after removing team means.

| position | η² (6) | ρ strength (6) | within-team ρ (6) | η² (38) | ρ strength (38) | within-team ρ (38) |
|---|---|---|---|---|---|---|
| CB | 0.51 | 0.40 | 0.35 | 0.65 | 0.47 | 0.62 |
| FB | 0.36 | -0.18 | 0.16 | 0.55 | -0.43 | 0.62 |
| DM | 0.38 | 0.20 | 0.45 | 0.45 | 0.45 | 0.77 |
| CM | 0.52 | 0.00 | 0.57 | 0.59 | 0.07 | 0.81 |
| AM | 0.91 | n/a | 0.83 | 0.74 | n/a | 0.63 |
| W | 0.57 | 0.60 | 0.32 | 0.79 | 0.79 | 0.67 |
| ST | 0.63 | 0.40 | 0.46 | 0.81 | 0.50 | 0.59 |

### 5d. Summary (computed from the tables above)

* Pooled over 12 fresh squads, the Spearman ρ between position score and the hidden composite ranges from 0.21 to 0.57 across positions with 6 matches per team, and from 0.46 to 0.80 with 38 matches per team.
* ρ is higher at 38 than at 6 matches for 7 of 7 positions (CB, FB, DM, CM, AM, W, ST).
* A single 12-match tournament (7-17 ranked players per position) is much noisier than these pooled values; the seed-42 tournament in section 1 is one such sample.
* Section 5b shows which categories carry signal; section 5c shows how much of the position score is explained by the team.

## Notes

* Ground-truth composite per position: CB: aerial, tackling, positioning, passing, pace; FB: pace, tackling, ball_carrying, passing, stamina; DM: tackling, passing, positioning, decision_making, pressing; CM: passing, decision_making, stamina, ball_carrying, pressing; AM: passing, ball_carrying, decision_making, finishing, pace; W: ball_carrying, pace, finishing, passing, pressing; ST: finishing, positioning, aerial, pace, ball_carrying.
* Six matches is a small sample; percentiles are shrunk towards the pool mean with k = 270 minutes, which pulls low-minute players towards average.
* The AM pool is small because only the 4-2-3-1 formation has an AM slot; AM players mostly play as wingers or central midfielders.
