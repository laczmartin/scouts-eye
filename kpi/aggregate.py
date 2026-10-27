"""From match counters to per-90 KPIs, shrunk values, percentiles and profiles."""

import collections
import csv
import json
import os
import statistics

from . import definitions as D
from .accumulator import MatchAccumulator

COUNTER_KPIS = [k for k in D.ALL_KPIS if D.KPI_KIND[k] == "per90"]


# ------------------------------------------------------------------ loading
def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_dataset(data_dir):
    d = dict(dir=data_dir)
    d["players"] = read_csv(os.path.join(data_dir, "players.csv"))
    d["teams"] = read_csv(os.path.join(data_dir, "teams.csv"))
    d["matches"] = read_csv(os.path.join(data_dir, "matches.csv"))
    d["lineups"] = read_csv(os.path.join(data_dir, "lineups.csv"))
    d["physical"] = read_csv(os.path.join(data_dir, "physical_snapshots.csv"))
    d["events"] = {}
    for m in d["matches"]:
        with open(os.path.join(data_dir, "events", f"{m['match_id']}.jsonl"), encoding="utf-8") as f:
            d["events"][m["match_id"]] = [json.loads(line) for line in f if line.strip()]
    return d


# ------------------------------------------------------------ per match
def match_player_rows(d, match):
    """Run the accumulator over one match; return per-player rows and the team summary."""
    mid = match["match_id"]
    lus = [lu for lu in d["lineups"] if lu["match_id"] == mid]
    acc = MatchAccumulator(match, lus, d["players"])
    for e in d["events"][mid]:
        acc.update(e)
    team = acc.team_summary()
    # possession share for PAdj
    poss = {t: team[t]["possession_pct"] / 100.0 for t in team}
    phys = collections.defaultdict(lambda: collections.Counter())
    for r in d["physical"]:
        if r["match_id"] != mid:
            continue
        c = phys[r["player_id"]]
        c["distance_m"] += float(r["distance_m"])
        c["high_speed_distance_m"] += float(r["high_speed_distance_m"])
        c["sprints"] += int(r["sprints"])
        c["top_speed_kmh"] = max(c["top_speed_kmh"], float(r["top_speed_kmh"]))
    rows = []
    for lu in lus:
        if lu["on_ms"] == "":
            continue
        pid = lu["player_id"]
        c = acc.p[pid]
        opp_poss = 1.0 - poss[lu["team_id"]]
        own_poss = poss[lu["team_id"]]
        f_def = (0.5 / opp_poss) if opp_poss > 0 else 1.0   # defensive volumes scale with the opponent's possession
        f_att = (0.5 / own_poss) if own_poss > 0 else 1.0   # attacking volumes scale with the own possession
        row = dict(match_id=mid, player_id=pid, team_id=lu["team_id"], position_group_played=lu["position_group_played"],
                   minutes=acc.minutes(pid), possession_share=round(own_poss, 3))
        for k in COUNTER_KPIS:
            if k in D.PADJ_DEFENSIVE:
                row[k] = c[k] * f_def
            elif k in D.PADJ_ATTACKING:
                row[k] = c[k] * f_att
            else:
                row[k] = c[k]
        row["padj_tackles_interceptions"] = c["tackles_interceptions"] * f_def
        for num, den in D.RATIO_DEFS.values():
            row[num] = c[num]
            row[den] = c[den]
        for k in ("distance_m", "high_speed_distance_m", "sprints", "top_speed_kmh"):
            row[k] = phys[pid][k]
        for k in D.INFO_COUNTERS:
            row[k] = c[k]
        rows.append(row)
    for t in team:
        team[t].update(match_id=mid, team_id=t, opponent_id=acc.opp(t))
    return rows, list(team.values()), acc


# ------------------------------------------------------------ tournament
def aggregate_player_position(match_rows):
    """Sum match rows per (player, position_group_played)."""
    agg = {}
    for r in match_rows:
        key = (r["player_id"], r["position_group_played"])
        a = agg.setdefault(key, collections.Counter())
        a["matches"] += 1
        for k, v in r.items():
            if k in ("match_id", "player_id", "team_id", "position_group_played"):
                continue
            if k == "top_speed_kmh":
                a[k] = max(a[k], v)
            else:
                a[k] += v
        a["_team"] = r["team_id"]
    return agg


def per90_values(a):
    """Raw per-90 / pct / max values from aggregated counters."""
    mins = a["minutes"]
    out = {}
    for k in D.ALL_KPIS:
        kind = D.KPI_KIND[k]
        if kind == "per90":
            out[k] = a[k] / mins * 90.0 if mins > 0 else 0.0
        elif kind == "max":
            out[k] = a[k]
        else:
            num, den = D.RATIO_DEFS[k]
            if kind == "pct":
                out[k] = 100.0 * a[num] / a[den] if a[den] else 0.0
            else:
                out[k] = a[num] / a[den] if a[den] else 0.0
    return out


def shrink(raw, minutes, pool_mean, k=D.SHRINK_K):
    return (raw * minutes + pool_mean * k) / (minutes + k)


def percentile(pool_values, v):
    if not pool_values:
        return 50.0
    below = sum(1 for x in pool_values if x < v)
    equal = sum(1 for x in pool_values if x == v)
    return 100.0 * (below + 0.5 * equal) / len(pool_values)


class ReferencePool:
    """Per-position raw per-90 KPI distributions from the reference tournaments."""

    def __init__(self, rows):
        raw = collections.defaultdict(lambda: collections.defaultdict(list))  # pos -> kpi -> raw values
        mins = collections.defaultdict(list)
        for r in rows:
            pos = r["position_group"]
            mins[pos].append(float(r["minutes"]))
            for k in D.ALL_KPIS:
                raw[pos][k].append(float(r[k]))
        self.means = {pos: {k: statistics.fmean(v) for k, v in kp.items()} for pos, kp in raw.items()}
        # percentiles are taken against the pool's *shrunk* values (each pool player shrunk with his own
        # minutes towards the pool mean), so sparse KPIs (goals of defenders) are not distorted by a pool of zeros
        self.values = {pos: {k: [shrink(v, m, self.means[pos][k]) for v, m in zip(vals, mins[pos])]
                             for k, vals in kp.items()} for pos, kp in raw.items()}
        self.size = {pos: len(mins[pos]) for pos in mins}

    def mean(self, pos, k):
        return self.means.get(pos, {}).get(k, 0.0)

    def pct(self, pos, k, v):
        p = percentile(self.values.get(pos, {}).get(k, []), v)
        return 100.0 - p if k in D.NEGATIVE_KPIS else p


def tournament_rows(agg, pool, players_by_id):
    """player_tournament_kpis rows: raw per90, shrunk per90, percentiles, reliability."""
    rows = []
    for (pid, pos), a in agg.items():
        if pos not in D.OUTFIELD_GROUPS:
            continue
        raw = per90_values(a)
        mins = a["minutes"]
        row = dict(player_id=pid, team_id=a["_team"], position_group=pos, matches=a["matches"], minutes=round(mins, 1),
                   reliability=D.reliability_label(mins), age=players_by_id[pid]["age"], name=players_by_id[pid]["name"])
        for k in D.ALL_KPIS:
            shr = shrink(raw[k], mins, pool.mean(pos, k))
            row[f"{k}_raw"] = round(raw[k], 3)
            row[f"{k}_shrunk"] = round(shr, 3)
            row[f"{k}_pct"] = round(pool.pct(pos, k, shr), 1)
        for k in D.INFO_COUNTERS:
            row[k] = a[k]
        rows.append(row)
    return rows


def load_settings(path="config/kpi_settings.json"):
    with open(path) as f:
        return json.load(f)


def build_profiles(t_rows, weights, settings=None):
    """Category scores, position score, strengths / weaknesses per (player, position).
    Players below settings["min_minutes_ranking"] get ranking_status = low_data."""
    settings = settings or load_settings()
    min_rank = settings["min_minutes_ranking"]
    by_player = collections.defaultdict(list)
    for r in t_rows:
        by_player[r["player_id"]].append(r)
    profiles = []
    for pid, rows in by_player.items():
        rows.sort(key=lambda r: -r["minutes"])
        for i, r in enumerate(rows):
            if i > 0 and r["minutes"] < 90:
                continue
            pos = r["position_group"]
            cats = {}
            for cat, kpis in D.CATEGORIES.items():
                cats[cat] = statistics.fmean(r[f"{k}_pct"] for k, _ in kpis)
            w = weights["weights"][pos]
            score = sum(cats[c] * w[c] for c in cats) / 100.0
            ranked = sorted(cats.items(), key=lambda kv: -kv[1])
            prof = dict(player_id=pid, name=r["name"], team_id=r["team_id"], age=r["age"], position_group=pos,
                        profile_type="primary" if i == 0 else "secondary", minutes=r["minutes"], matches=r["matches"],
                        reliability=r["reliability"], position_score=round(score, 1),
                        ranking_status="ranked" if r["minutes"] >= min_rank else "low_data")
            for c, v in cats.items():
                prof[f"cat_{c}"] = round(v, 1)
            prof["strengths"] = ";".join(f"{c}:{v:.0f}" for c, v in ranked[:3])
            prof["weaknesses"] = ";".join(f"{c}:{v:.0f}" for c, v in ranked[-2:])
            prof["fouls"], prof["yellow_cards"], prof["red_cards"] = r["fouls"], r["yellow_cards"], r["red_cards"]
            profiles.append(prof)
    profiles.sort(key=lambda p: (p["position_group"], p["ranking_status"] != "ranked", -p["position_score"]))
    return profiles


def write_csv(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0].keys())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in fields})
