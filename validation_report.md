# Validation report – synthetic U19 tournament

Seed: **42**, generator version 0.1.0, generated 2026-10-23T18:39:32.590284+00:00

## 1. Consistency checks – ALL PASSED

| check | result | detail |
|---|---|---|
| Scores in matches.csv equal goal events | PASS | all 12 matches match |
| Every event's player was on the pitch | PASS | 23541 player events checked |
| Lineup minutes match substitution events | PASS | 118 substitutions checked |
| No duplicate event_ids | PASS | 26497 events, 0 duplicates |
| Timestamps non-decreasing within each match | PASS | ok |
| Coordinates inside the pitch (0-100) | PASS | 0 out-of-pitch coordinates |
| Penalties flagged explicitly (is_penalty) and consistently | PASS | 4 penalties |
| Suspended / injured players do not play (recomputed from cards and injuries) | PASS | 12 suspension and 5 injury absences expected; all match lineups.csv |
| Every squad player has one lineups.csv row per match (23 per team) | PASS | 24 team-matches checked |
| Team plays with ten men after a red card | PASS | 5 sending-offs checked |
| At most 5 substitutions in at most 3 windows per team per match | PASS | 118 substitutions, 4.9 per team-match |
| Rotation: only GK / CB play every minute of all six matches | PASS | players with 6 full matches: T1P01, T2P02, T3P03, T4P02 |
| Age composition (U19: born >= 2008-01-01; majority 18; <= 2 aged 15; <= 2 aged 16 per team) | PASS | ages {15: 2, 16: 3, 17: 32, 18: 55}, 16-year-olds per team {'T2': 2, 'T3': 1} |
| Top scorer has 4-6 goals | PASS | Kerem Svoboda (T4P22) 5 goals |
| Young hidden gem (15-16) plays at least 180 minutes (180-290) per team | PASS | T1 T1P09 (age 15) 234 min; T2 T2P12 (age 16) 184 min; T3 T3P20 (age 16) 223 min; T4 T4P11 (age 15) 217 min |
| Squad composition per team equals the squad design table; every primary position exists in the formation (3 GK, >= 9 ST) | PASS | ST 11, 23 players per team |
| 2-4 multi-positional players per team with realistic pairings | PASS | T1 4, T2 3, T3 3, T4 3 |
| Every multi-positional player has both positions in his formation and played both at least once | PASS | 13 hybrids; all played both positions |
| No position change within a match (one position per player per match; substitutes take the vacated slot) | PASS | 552 player-matches checked |

## 2. Realism – published benchmarks: 5 OK, 0 WARN

Only benchmarks from public, published sources are checked (`benchmarks.py`). For a tournament mean the band is the benchmark widened by one standard error of that mean, computed from the synthetic matches themselves.

| section | metric | actual | published benchmark | 12-match band | status | source |
|---|---|---|---|---|---|---|
| Per match | goals per match (tournament mean) | 3.67 | 2.93–3.44 | 2.34–4.03 | OK | uyl |
| Per team, per match | passes (all teams) | 337 | 283–381 | as benchmark | OK | sramkova2024 |
| Physical (outfield, per 90) | total distance km | 10.00 | 9.00–12.00 | as benchmark | OK | sportjournal_review |
| Physical (outfield, per 90) | position with the highest total distance | CM | CM | as benchmark | OK | causevic2025 |
| Physical (outfield, per 90) | position with the most high-speed running (≥ 19.8 km/h) | W | FB or W | as benchmark | OK | causevic2025, unisr_u19 |

Sources:

* `uyl` – UEFA Youth League, goals per match (season statistics as listed on Wikipedia). https://en.wikipedia.org/wiki/2013%E2%80%9314_UEFA_Youth_League · https://en.wikipedia.org/wiki/2019%E2%80%9320_UEFA_Youth_League · https://en.wikipedia.org/wiki/2022%E2%80%9323_UEFA_Youth_League · https://en.wikipedia.org/wiki/2023%E2%80%9324_UEFA_Youth_League
* `sramkova2024` – Šrámková, K. (2024). Analýza vybraných výkonnostních parametrů české fotbalové ligy U-19 v evropském kontextu. Bachelor's thesis, Charles University, Prague (abstract: Czech U19 league 332 ± 49 passes per match, team level; the lowest group together with Slovakia among six U19 leagues, 2023/24; assumed per team per match: the full text could not be checked). https://dspace.cuni.cz/handle/20.500.11956/192576
* `sportjournal_review` – Physical performance of youth football (soccer) players playing in European and national leagues matches, The Sport Journal (review: elite youth players cover about 9–12 km per match). https://thesportjournal.org/article/physical-performance-of-youth-football-soccer-players-playing-in-european-and-national-leagues-matches/
* `causevic2025` – Čaušević et al. (2025), Sensors 25(18), 5825: U19 GPS study, high-speed running ≥ 19.8 km/h, sprinting ≥ 25.2 km/h; central midfielders cover the most total distance, wide defenders and forwards the most high-speed running and sprinting. https://www.mdpi.com/1424-8220/25/18/5825
* `unisr_u19` – 10 Hz GPS study of 23 elite U19 players over 31 matches (IRIS UniSR): full-backs and wingers have the highest very-high-speed running and sprint counts. https://iris.unisr.it/handle/20.500.11768/103759

### Descriptive statistics (no external target)

These values are reported for transparency only; no public benchmark is used for them.

| section | metric | actual |
|---|---|---|
| Per team, per match | passes (direct-style teams) | 313 |
| Per team, per match | passes (possession team) | 408 |
| Per team, per match | pass accuracy % (direct-style) | 75.6 |
| Per team, per match | pass accuracy % (possession) | 80.7 |
| Per team, per match | long passes (> 30 m) | 44.2 |
| Per team, per match | long pass accuracy % | 48.5 |
| Per team, per match | shots | 10.9 |
| Per team, per match | shots (possession team) | 10.0 |
| Per team, per match | shots on target % | 39.4 |
| Per team, per match | xG | 1.61 |
| Per team, per match | goals | 1.83 |
| Per team, per match | defensive duels | 69.4 |
| Per team, per match | defensive duels won % | 65.0 |
| Per team, per match | aerial duels | 27.3 |
| Per team, per match | aerial duels won % | 44.6 |
| Per team, per match | interceptions | 37.2 |
| Per team, per match | PPDA (direct-style teams) | 8.48 |
| Per team, per match | PPDA (possession team) | 14.86 |
| Per team, per match | corners | 6.2 |
| Per team, per match | fouls | 10.6 |
| Per team, per match | yellow cards | 1.33 |
| Per match, both teams | total events | 2208 |
| Per match, both teams | passes | 674 |
| Per match, both teams | goals in a single match (min / max) | 1 / 8 |
| Per match, both teams | draws across 12 matches | 3 |
| Per match, both teams | shots | 21.8 |
| Per match, both teams | mean xG per shot | 0.152 |
| Per match, both teams | goals / xG (tournament) | 1.14 |
| Per match, both teams | ground duel contests | 139 |
| Per match, both teams | aerial duel contests | 27.3 |
| Per match, both teams | pressures | 327 |
| Per match, both teams | possession split (most lopsided share, %) | 57 |
| Physical (outfield, per 90) | high-speed running m (≥ 19.8 km/h) | 617 |
| Physical (outfield, per 90) | sprint distance m (≥ 25.2 km/h) | 199 |
| Physical (outfield, per 90) | top speed km/h (match max, mean over players) | 29.7 |
| Physical (outfield, per 90) | distance km: fresh minus loaded players | 0.65 |
| Physical (outfield, per 90) | top speed gap: age 17+ minus age 15–16 (km/h) | 1.0 |

Per-position physical averages (per 90, players with >= 60 min): distance km / high-speed m
| position | distance km | high-speed m |
|---|---|---|
| CB | 9.26 | 457 |
| FB | 10.22 | 718 |
| DM | 10.49 | 495 |
| CM | 11.26 | 591 |
| AM | 10.07 | 675 |
| W | 10.01 | 786 |
| ST | 9.52 | 690 |

Per-team averages (per match):
| team | passes | pass acc % | shots | xG | goals | def. duels | PPDA | possession % |
|---|---|---|---|---|---|---|---|---|
| T1 Northbridge FC U19 | 314 | 74.9 | 10.7 | 1.58 | 2.00 | 70 | 8.5 | 47 |
| T2 Vallora United U19 | 329 | 76.6 | 11.5 | 1.69 | 2.33 | 70 | 7.4 | 52 |
| T3 Sankt Albrecht SV U19 | 297 | 75.3 | 11.3 | 1.66 | 1.17 | 74 | 9.5 | 46 |
| T4 Kalmarsund BK U19 | 408 | 80.7 | 10.0 | 1.52 | 1.83 | 64 | 14.9 | 54 |

## 3. Tournament summary

### Results

All matches at Hollowmere Arena (neutral venue); matchdays every 3 days (day 1 to day 16).

| match | MD | day | date | home | score | away | live |
|---|---|---|---|---|---|---|---|
| M01 | 1 | 1 | 2026-03-02 | Northbridge FC U19 | 4–2 | Vallora United U19 |  |
| M02 | 1 | 1 | 2026-03-02 | Sankt Albrecht SV U19 | 1–1 | Kalmarsund BK U19 |  |
| M03 | 2 | 4 | 2026-03-05 | Northbridge FC U19 | 1–1 | Sankt Albrecht SV U19 |  |
| M04 | 2 | 4 | 2026-03-05 | Vallora United U19 | 1–3 | Kalmarsund BK U19 |  |
| M05 | 3 | 7 | 2026-03-08 | Kalmarsund BK U19 | 0–2 | Northbridge FC U19 |  |
| M06 | 3 | 7 | 2026-03-08 | Vallora United U19 | 1–0 | Sankt Albrecht SV U19 |  |
| M07 | 4 | 10 | 2026-03-11 | Sankt Albrecht SV U19 | 2–0 | Northbridge FC U19 |  |
| M08 | 4 | 10 | 2026-03-11 | Kalmarsund BK U19 | 3–5 | Vallora United U19 |  |
| M09 | 5 | 13 | 2026-03-14 | Northbridge FC U19 | 3–2 | Kalmarsund BK U19 |  |
| M10 | 5 | 13 | 2026-03-14 | Sankt Albrecht SV U19 | 1–2 | Vallora United U19 |  |
| M11 | 6 | 16 | 2026-03-17 | Kalmarsund BK U19 | 2–2 | Sankt Albrecht SV U19 |  |
| M12 | 6 | 16 | 2026-03-17 | Vallora United U19 | 3–2 | Northbridge FC U19 | yes |

### Final table

| # | team | P | W | D | L | GF | GA | GD | Pts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | T2 Vallora United U19 | 6 | 4 | 0 | 2 | 14 | 13 | 1 | 12 |
| 2 | T1 Northbridge FC U19 | 6 | 3 | 1 | 2 | 12 | 10 | 2 | 10 |
| 3 | T3 Sankt Albrecht SV U19 | 6 | 1 | 3 | 2 | 7 | 7 | 0 | 6 |
| 4 | T4 Kalmarsund BK U19 | 6 | 1 | 2 | 3 | 11 | 14 | -3 | 5 |

Table before the last match (M12): T1 10 pts, T2 9 pts, T3 6 pts, T4 5 pts

### Top scorers

| player | team | age | position | goals |
|---|---|---|---|---|
| Kerem Svoboda | T4 | 18 | RS | 5 |
| Felix Alvarez | T2 | 18 | ST | 4 |
| Iker Andreou | T2 | 18 | AM | 4 |
| Mathis Byrne | T1 | 17 | LW | 3 |
| Abdoulaye Ferris | T3 | 16 | LS | 3 |
| Dimitris Eriksen | T1 | 18 | ST | 3 |
| Harry Boateng | T2 | 18 | ST | 3 |
| Mateo Van Dijkstra | T2 | 18 | AM | 2 |
| Szymon Winther | T1 | 18 | LW | 2 |
| Jakub Mbeki | T3 | 18 | LS | 2 |

### Cards, suspensions, injuries

Yellow cards: 32, second yellows: 1, straight reds: 4.

| match | team | player | reason |
|---|---|---|---|
| M05 | T4 | Bilal Fernandes (T4P07) | suspended |
| M05 | T1 | Sigurd Radic (T1P04) | suspended |
| M05 | T1 | Bilal Teixeira (T1P16) | injured |
| M06 | T2 | Felix Alvarez (T2P23) | injured |
| M07 | T3 | Ibrahima Alvarez (T3P17) | suspended |
| M08 | T2 | Riccardo Lehmann (T2P18) | suspended |
| M09 | T1 | Nikola Ferris (T1P12) | suspended |
| M09 | T4 | Oskar Winther (T4P10) | suspended |
| M10 | T3 | Ibrahima Alvarez (T3P17) | suspended |
| M10 | T2 | Riccardo Lehmann (T2P18) | suspended |
| M10 | T2 | Felix Alvarez (T2P23) | injured |
| M11 | T4 | Oskar Winther (T4P10) | suspended |
| M11 | T4 | Kerem Osei (T4P20) | suspended |
| M11 | T3 | Mathis Mbeki (T3P11) | suspended |
| M12 | T2 | Harry Boateng (T2P22) | injured |
| M12 | T2 | Felix Alvarez (T2P23) | injured |
| M12 | T1 | Alvaro Lambert (T1P10) | suspended |

Injury events: M03 T1P16 (minor), M04 T2P23 (minor), M08 T2P23 (major), M10 T2P22 (minor), M11 T3P08 (minor)

### Ten-men spells

| match | team | player | red card | minutes with 10 | possession before → after | shots before → after |
|---|---|---|---|---|---|---|
| M04 | T4 | T4P07 | 74' | 18 | 54% → 48% | 11 → 1 |
| M06 | T3 | T3P17 | 58' | 35 | 48% → 36% | 5 → 8 |
| M06 | T2 | T2P18 | 77' | 16 | 56% → 62% | 10 → 0 |
| M08 | T4 | T4P10 | 0' | 96 | 57% → 51% | 0 → 7 |
| M10 | T3 | T3P11 | 58' | 34 | 44% → 45% | 8 → 2 |

### Squad composition (primary positions)

| team | formation | GK | CB | FB | DM | CM | AM | W | ST | total |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | 4-3-3 | 3 | 4 | 4 | 2 | 4 | 0 | 4 | 2 | 23 |
| T2 | 4-2-3-1 | 3 | 4 | 4 | 4 | 0 | 3 | 3 | 2 | 23 |
| T3 | 3-5-2 | 3 | 5 | 4 | 2 | 5 | 0 | 0 | 4 | 23 |
| T4 | 4-4-2 | 3 | 4 | 4 | 0 | 5 | 0 | 4 | 3 | 23 |
| total |  | 12 | 17 | 16 | 8 | 14 | 3 | 11 | 11 | 92 |

### Multi-positional players

Position changes happen only between matches. `position_group_played` in lineups.csv is the slot actually filled in that match; abilities in the secondary position carry a small hidden penalty (ground truth only).

| player | name | team | primary | secondary | matches by position played | status |
|---|---|---|---|---|---|---|
| T1P05 | Dimitris Vogel | T1 | CB | DM | CB: M03, M09, M12; DM: M05 | both positions played |
| T1P13 | Cian Dubois | T1 | DM | CM | CM: M03, M05; DM: M01, M07, M09, M12 | both positions played |
| T1P18 | Szymon Winther | T1 | W | ST | ST: M01, M12; W: M03, M05, M07, M09 | both positions played |
| T1P20 | Mathis Byrne | T1 | W | ST | ST: M03, M05; W: M01, M07, M09, M12 | both positions played |
| T2P05 | Felix Keller | T2 | CB | DM | CB: M04, M06, M12; DM: M01, M10 | both positions played |
| T2P18 | Riccardo Lehmann | T2 | AM | W | AM: M06; ST: M12; W: M04 | both positions played; emergency cover at ['ST'] |
| T2P22 | Harry Boateng | T2 | ST | W | ST: M01, M06, M08, M10; W: M04 | both positions played |
| T3P05 | Elias Pedersen | T3 | CB | DM | CB: M02, M06, M07, M10; DM: M03; FB: M11 | both positions played; emergency cover at ['FB'] |
| T3P07 | Vojtech Diallo | T3 | CB | DM | CB: M02, M03, M07, M11; DM: M06 | both positions played |
| T3P19 | Alessandro Svoboda | T3 | CM | DM | CM: M02, M03, M10; DM: M06 | both positions played |
| T4P06 | Tyrese Dubois | T4 | CB | FB | CB: M02, M08, M09, M11; FB: M04 | both positions played |
| T4P10 | Oskar Winther | T4 | FB | W | FB: M02, M08; W: M04 | both positions played |
| T4P19 | Nikos Bakker | T4 | W | ST | ST: M02, M05, M08, M09; W: M04, M11 | both positions played |

### Hidden gems (youngest standouts) and fatigue

| team | player | age | minutes |
|---|---|---|---|
| T1 | Ilyes Petrovic (T1P09) | 15 | 234 |
| T2 | Dominik Novak (T2P12) | 16 | 184 |
| T3 | Abdoulaye Ferris (T3P20) | 16 | 223 |
| T4 | Szymon Blanchard (T4P11) | 15 | 217 |

Distance per 90 (outfield, >= 60 min): fresh players 10.18 km (n=162) vs players who played >= 60 min three days earlier 9.53 km (n=60).

### Minutes distribution (per player, whole tournament)

| minutes | players |
|---|---|
| 0–0 min | 8 |
| 1–89 min | 0 |
| 90–179 min | 8 |
| 180–299 min | 33 |
| 300–449 min | 38 |
| 450–700 min | 5 |

Players used: 84 of 92; median minutes of used players: 307

### Age distribution

| age | players |
|---|---|
| 15 | 2 |
| 16 | 3 |
| 17 | 32 |
| 18 | 55 |

### Birth-quarter distribution (relative age effect)

| quarter | players | share | target |
|---|---|---|---|
| Q1 | 45 | 49% | ~35% |
| Q2 | 18 | 20% | ~28% |
| Q3 | 10 | 11% | ~22% |
| Q4 | 19 | 21% | ~15% |
