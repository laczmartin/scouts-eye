# KPI definitions (Phase 2)

All KPIs are computed from `data/synthetic/events/*.jsonl`, `lineups.csv` and
`physical_snapshots.csv` by `kpi/accumulator.py` and `kpi/aggregate.py`.
Nothing in the KPI layer reads `ground_truth_abilities.csv`. Definitions follow
common public event-data conventions where possible. Pitch: 105 × 68 m, coordinates 0–100
in the acting team's attacking frame. Penalty area: x ≥ 84.3 and 20.4 ≤ y ≤ 79.6.
Final third: x ≥ 66.7. Own half: x < 50.

## Scope and splits

* Profiles are produced for outfield players only (CB, FB incl. wing-backs,
  DM, CM, AM, W, ST). Goalkeepers contribute to team KPIs and the live feed.
* KPIs are computed per **position actually played** (`position_group_played`
  in `lineups.csv`); a player with minutes in two positions gets one row per
  position. The main profile is the position with the most minutes; a
  secondary profile is produced when the second position has ≥ 90 minutes.
* No age adjustment: every player is compared with all players of the same
  position group. No form / recent-matches comparison.
* Splits: **baseline** = M01–M11 (`data/kpi/`), **live** = M12 event by event
  (`data/kpi/live/`), **final** = M01–M12 (`data/kpi/final/`).

## Normalisation and reliability

* `per90 = total / minutes × 90` (minutes in that position).
* `pct` KPIs are ratios of totals (e.g. completed passes / passes) and are not
  scaled; the same shrinkage formula is applied to them with the player's
  minutes.
* **Shrunk value** = `(raw × minutes + pool_mean × k) / (minutes + k)` with
  k = 270 minutes and `pool_mean` the reference-pool mean of that position.
* **Percentile** (0–100) of the shrunk value against the reference pool of the
  same position, where every pool player is shrunk the same way with his own
  minutes (otherwise sparse KPIs such as defenders' goals would be distorted
  by a pool of zeros): `100 × (count below + 0.5 × count equal) / pool size`.
  Negative KPIs (turnovers, dribbled past) are inverted (100 − percentile).
* **Category score** = mean of the percentiles of the category's KPIs.
* **Position score** = Σ category score × weight / 100, with the public
  weights in `config/position_weights.json`.
* **Strengths / weaknesses** = the 3 highest and 2 lowest category scores.
* **Reliability** by minutes in the position: < 90 "very low", 90–179 "low",
  180–359 "medium", ≥ 360 "good".

## Reference pool

`data/reference/reference_player_kpis.csv`: 50 extra fictional tournaments
(seeds 1000–1049) generated with the same generator but without the
acceptance re-draw, reduced to raw per-90 KPIs per player and position with
≥ 180 minutes in that position. Seeds, counts and date are in
`reference_metadata.json`. Percentiles and pool means are taken by position
group only.

## Possession adjustment (PAdj) of volume KPIs

Team style distorts volumes: a possession team's players pass, progress and
shoot more, a pressing or weaker team's players defend more. Following the
common possession-adjustment (PAdj) convention, volume KPIs are scaled per match before
aggregation:

* **defensive volumes** × `0.5 / opponent possession share`: defensive duels,
  dribbled past, aerial duels, aerial duels won, PAdj tackles + interceptions,
  ball recoveries, blocked shots, clearances, pressures, pressures in the
  opponent's half, pressure regains;
* **attacking volumes** × `0.5 / own possession share`: passes, turnovers,
  shots, npxG, touches in the box, xA, key passes, passes into the box,
  completed crosses, progressive passes and carries, deep progressions,
  xGBuildup, offensive duels, completed dribbles.

Possession share = share of both teams' on-ball actions in that match
(`possession_share` column in `player_match_kpis.csv`). Percentages and
ratios (accuracy, duels won %, npxG per shot, on-target %), goals and assists
(outputs) and physical KPIs are not adjusted. The reference pool uses the
same adjustment. There is one position score; no separate team-adjusted
score is produced.

## Categories and KPIs (each KPI in exactly one category)

| # | category | KPI | definition |
|---|---|---|---|
| 1 | Finishing | npxG | sum of shot xG, penalties excluded (a penalty is a shot with `is_penalty = true` in the events) |
| 1 | Finishing | shots | all shots (goal, saved, blocked, off target) |
| 1 | Finishing | npxG per shot | npxG / non-penalty shots (ratio, not per 90) |
| 1 | Finishing | shots on target % | (goals + saved) / shots |
| 1 | Finishing | touches in the penalty area | own on-ball actions (pass, carry, dribble, shot) starting inside the box, plus receptions of completed passes ending inside the box |
| 2 | Goal contribution | non-penalty goals | shots with outcome `goal`, penalties excluded |
| 2 | Goal contribution | assists | key passes that led directly to a goal |
| 2 | Goal contribution | NP goals + assists | sum of the two |
| 3 | Chance creation | xA | sum of the xG of the shots assisted by the player's key passes |
| 3 | Chance creation | key passes | the last completed pass-like event (pass, corner, free kick, throw-in) to the shooter in the same possession with no other player's on-ball action in between |
| 3 | Chance creation | passes into the penalty area | completed passes starting outside and ending inside the box |
| 3 | Chance creation | successful crosses | completed high or low passes from a wide final-third zone (x > 66, y < 21 or y > 79) ending inside the box |
| 4 | Passing | passes | events of type `pass` (set-piece deliveries and throw-ins excluded) |
| 4 | Passing | pass accuracy % | completed / passes |
| 4 | Passing | pass accuracy under pressure % | completed / passes with `under_pressure = true` |
| 4 | Passing | long pass accuracy % | completed / passes longer than 30 m |
| 4 | Passing | turnovers (negative) | failed passes and failed carries starting in the own half |
| 5 | Progression | progressive passes | completed passes that bring the ball ≥ 30 m closer to goal when start and end are in the own half, ≥ 15 m when crossing halves, ≥ 10 m when both are in the opponent's half (distance to the goal centre) |
| 5 | Progression | progressive carries | the same rule for completed carries |
| 5 | Progression | deep progressions | completed passes or carries starting before and ending inside the final third |
| 5 | Progression | xGBuildup | xG of the shots in possessions where the player had an on-ball action before the shot, excluding the shooter and the key passer |
| 6 | Offensive duels | offensive duels | dribbles (take-ons) plus the attacker's side of challenges on a carrier |
| 6 | Offensive duels | offensive duels won % | won / offensive duels |
| 6 | Offensive duels | successful dribbles | dribbles with outcome `success` |
| 7 | Defensive duels | defensive duels | tackles (defender-initiated challenges) plus the defender's side of take-ons |
| 7 | Defensive duels | defensive duels won % | won / defensive duels |
| 7 | Defensive duels | dribbled past (negative) | take-ons lost by the defender |
| 8 | Aerial play | aerial duels | all aerial duel events of the player |
| 8 | Aerial play | aerial duels won % | won / aerial duels (about 10 % of contests are neutral, so both players lose) |
| 8 | Aerial play | aerial duels won | won aerial duels |
| 9 | Defensive activity | PAdj tackles + interceptions | (tackles won + interceptions) × 0.5 / opponent possession share in that match (the same PAdj factor is applied to the other volume KPIs, see above) |
| 9 | Defensive activity | ball recoveries | `ball_recovery` events |
| 9 | Defensive activity | blocked shots | clearances linked to a blocked shot |
| 9 | Defensive activity | clearances | other clearances |
| 10 | Pressing | pressures | `pressure` events |
| 10 | Pressing | pressures in the opponent's half | pressures with x > 50 |
| 10 | Pressing | pressure regains | own-team ball recovery, interception or won tackle within 5 s of the player's pressure (each pressure counted at most once) |
| 11 | Physical | distance | metres from the 5-minute snapshots |
| 11 | Physical | high-speed running | metres at ≥ 19.8 km/h |
| 11 | Physical | sprints | number of sprints (≥ 25.2 km/h) |
| 11 | Physical | top speed | maximum over the matches (km/h, not per 90) |

Discipline (fouls, yellow and red cards) is reported as information only.

## Team KPIs per match (`team_match_kpis.csv`)

| KPI | definition |
|---|---|
| possession % | own on-ball actions (pass, carry, dribble, shot) / both teams' |
| field tilt % | own on-ball actions in the final third / both teams' final-third on-ball actions |
| PPDA | opponent passes started in their own half / own defensive actions (tackles, defensive ground duels, interceptions, fouls) in the opponent's half |
| xG, npxG, shots, goals | sums over the team's shots |
| passes, pass accuracy % | type `pass` events and completed share |
| pressures | `pressure` events |
| duels won % | won / (tackles + ground duels + dribbles + aerial duels) |
| saves | goalkeeper `save` events |

## Live engine (`live_engine.py`)

Rolling windows of 5 and 15 minutes of playing time (`timestamp_ms`):

* possession %, field tilt %, PPDA, xG, shots as above, restricted to the window;
* **pressing intensity** = pressures per minute in the window;
* **control vs chaos**: `passes per possession / 4 − possession changes per minute / 4`
  over the last 15 minutes; > 0.15 "control", < −0.15 "chaos", otherwise "balanced";
* **momentum** (home perspective) = `0.6 × tanh(Δ xG over 15 min / 0.5) + 0.4 × (field tilt − 50) / 50`.

Player live KPIs are raw per 90 for the minutes played so far; the live
position score uses the same shrinkage (k = 270) and pool percentiles and is
labelled "very low (live)" reliability. Physical KPIs are not available live.

Moments (`M12_moments.jsonl`, each with evidence event ids and an importance
0–1): goal (0.85–1.0), big chance with xG ≥ 0.3 (0.55), milestone (first
tournament goal 0.6, youngest scorer 0.7, brace 0.6, hat-trick 0.9),
momentum shift (0.5, when the 15-minute momentum changes sign beyond ±0.25,
at most every 3 minutes), control/chaos switch (0.45), pressing surge (0.4,
5-minute pressing rate ≥ 1.6 × the match rate and ≥ 15 pressures, at most
every 5 minutes per team), player threshold (0.3–0.4, e.g. 5th / 10th
progressive pass, 10th / 20th pressure, 5th touch in the box), card (0.3,
red 0.7), injury (0.35–0.5), substitution with context (0.3).
Snapshots are written once per match minute (`M12_state_by_minute.jsonl`).

## Event metrics: pass difficulty, ball and shot speed, player tags

Computed by `kpi/event_metrics.py` from the event fields (no AI, no ground truth);
tested in `tests/test_event_metrics.py`.

| metric | definition |
|---|---|
| pass distance (m) | √((Δx·1.05)² + (Δy·0.68)²) from the 0–100 coordinates on a 105 × 68 m pitch; equals `pass_length_m` of the data (largest difference 0.1 m) |
| forward metres | Δx·1.05 (negative = backwards) |
| direction | forward if the pass angle is within ±45° of the attacking direction, backward within ±45° of the own goal, else lateral |
| line-breaking (proxy) | the data has no opponent positions, so a pass "breaks a line" when it goes forward at least 10 m and crosses into the next third (x = 33.3 or 66.7) or into the penalty area from outside it |
| pass difficulty (0–1) | 0.35·L + 0.20·F + 0.20·P + 0.10·H + 0.15·B with L = min(distance / 40 m, 1), F = min(max(forward m, 0) / 30, 1), P = 1 under pressure, H = 1 high / 0.5 low / 0 ground, B = 1 line-breaking. A fixed, documented weighting, not a fitted model. Check on all tournament passes: completion falls with every band, 85.6 % (0–0.2), 82.9 %, 77.4 %, 69.5 %, 54.1 %, 35.6 % (0.8–1) |
| ball speed (km/h) | `ball_speed_kmh` of the synthetic data for passes, set pieces and shots; ball travel time = distance / speed |
| shot speed (km/h) | `ball_speed_kmh` of a shot; in the data foot shots 60–110 km/h (median 86), headers 30–61 km/h. Plausibility: Rađa et al. (2019), PLoS ONE 14(5): e0217101 (doi:10.1371/journal.pone.0217101) measured a maximal dominant-foot instep kick of about 107–111 km/h for U19 players in a test and cite 80–103 km/h as the range for 15–19-year-olds; match shots are usually slower than a maximal test kick |

**Player tags** (short captions with the player's name, design choices):
a completed pass with difficulty ≥ 0.78 (about the top 1 % of completed passes),
a shot of at least 100 km/h, and a new match-high top speed of at least 28 km/h in
a 5-minute physical window (the fastest player of each window; sprint threshold of
the snapshots 25.2 km/h after Čaušević et al. 2025). M12 has 13 tags. The tags of
the last 5 minutes, the shot speed of a moment's shot and the pass that set it up
are part of the facts the Match Analyst gets; the UI shows the tags in the overlay
feed, the metrics in the event line, the evidence panel and the live player card.
