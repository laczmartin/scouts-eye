"""Realism benchmarks taken ONLY from public, published sources.

validate.py and calibrate.py compare the synthetic data with these values.
Every other metric is reported as a descriptive statistic without a target.
"""

SOURCES = {
    "uyl": {
        "label": "UEFA Youth League, goals per match (season statistics as listed on Wikipedia)",
        "values": {"2013–14": 3.44, "2019–20": 3.32, "2022–23": 3.44, "2023–24": 2.93},
        "urls": [
            "https://en.wikipedia.org/wiki/2013%E2%80%9314_UEFA_Youth_League",
            "https://en.wikipedia.org/wiki/2019%E2%80%9320_UEFA_Youth_League",
            "https://en.wikipedia.org/wiki/2022%E2%80%9323_UEFA_Youth_League",
            "https://en.wikipedia.org/wiki/2023%E2%80%9324_UEFA_Youth_League",
        ],
    },
    "sramkova2024": {
        "label": "Šrámková, K. (2024). Analýza vybraných výkonnostních parametrů české fotbalové ligy U-19 "
                 "v evropském kontextu. Bachelor's thesis, Charles University, Prague (abstract: Czech U19 league "
                 "332 ± 49 passes per match, team level; the lowest group together with Slovakia among six U19 leagues, 2023/24; "
                 "assumed per team per match: the full text could not be checked)",
        "urls": ["https://dspace.cuni.cz/handle/20.500.11956/192576"],
    },
    "sportjournal_review": {
        "label": "Physical performance of youth football (soccer) players playing in European and national leagues "
                 "matches, The Sport Journal (review: elite youth players cover about 9–12 km per match)",
        "urls": ["https://thesportjournal.org/article/physical-performance-of-youth-football-soccer-players-playing-in-european-and-national-leagues-matches/"],
    },
    "causevic2025": {
        "label": "Čaušević et al. (2025), Sensors 25(18), 5825: U19 GPS study, high-speed running ≥ 19.8 km/h, "
                 "sprinting ≥ 25.2 km/h; central midfielders cover the most total distance, wide defenders and "
                 "forwards the most high-speed running and sprinting",
        "urls": ["https://www.mdpi.com/1424-8220/25/18/5825"],
    },
    "unisr_u19": {
        "label": "10 Hz GPS study of 23 elite U19 players over 31 matches (IRIS UniSR): full-backs and wingers "
                 "have the highest very-high-speed running and sprint counts",
        "urls": ["https://iris.unisr.it/handle/20.500.11768/103759"],
    },
}

# goals per match: the range of the four published seasons
GOALS_PER_MATCH = (min(SOURCES["uyl"]["values"].values()), max(SOURCES["uyl"]["values"].values()))
# passes per team per match (assumed per team per match; the thesis full text could not be checked):
# published mean ± published standard deviation (single-match spread)
PASSES_PER_TEAM = (332 - 49, 332 + 49)
# total distance per 90 of outfield players (km)
DISTANCE_KM_PER_90 = (9.0, 12.0)
# qualitative position patterns
HIGHEST_DISTANCE_POSITIONS = {"CM"}
HIGHEST_HSR_POSITIONS = {"FB", "W"}
# speed thresholds used by the physical snapshots (definitions, not checks)
HSR_THRESHOLD_KMH, SPRINT_THRESHOLD_KMH = 19.8, 25.2
