#!/usr/bin/env python3
"""Scouting validation against the hidden ground truth.

It reads ground_truth_abilities.csv for the validation (as do validate.py, only to identify
the planted talents, and build_site.py, only to show their labelled validation rank).
It writes scouting_validation.md. Weights are never tuned here.
"""

import argparse
import collections
import csv
import os
import statistics

from kpi import definitions as D

from synth.config import GT_COMPOSITE as COMPOSITE  # shared with the generator (gems are top-3 by this composite)


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def composite(gt_row, pos, secondary=False):
    pen = 0
    if secondary and gt_row["secondary_position"] == pos and gt_row["secondary_penalty"]:
        pen = int(gt_row["secondary_penalty"])
        keys = set(k.split(":")[0] for k in gt_row["secondary_key_abilities"].split(";") if k)
    else:
        keys = set()
    return statistics.fmean(int(gt_row[a]) - (pen if a in keys else 0) for a in COMPOSITE[pos])


def diagnostics_section(args):
    import json
    from kpi import aggregate as A
    from kpi import diagnostics as G
    a, b = args.diag_seeds.split("-")
    seeds = list(range(int(a), int(b) + 1))
    pool = A.ReferencePool(A.read_csv(os.path.join(args.reference, "reference_player_kpis.csv")))
    with open("config/position_weights.json") as f:
        weights = json.load(f)
    settings = A.load_settings()
    sizes = (6, 12, 24, 38)
    res = G.run_diagnostics(pool, weights, settings, COMPOSITE, seeds, sizes, log=lambda s: print(s, file=__import__("sys").stderr))
    L = ["## 5. Diagnostics: where is the signal lost?\n",
         f"Fresh fictional squads from {len(seeds)} squad seeds ({seeds[0]}-{seeds[-1]}), each simulated for 6, 12, 24 and 38 matches per team "
         "(consecutive tournaments with the same squads; suspensions, fatigue and the gem plan restart every 6 matches). "
         "Profiles use the same reference pool, weights and shrinkage as the real pipeline; only ranked primary profiles (>= 180 min) are used. "
         "Spearman ρ is computed per position with all squad seeds pooled.\n",
         "### 5a. Sample-size curve: position score vs ground-truth composite\n"]
    rows = []
    for pos in D.OUTFIELD_GROUPS:
        cells = []
        for n in sizes:
            rho, k = res["curve"][(n, pos)]
            cells.append(f"{rho:.2f} (n={k})" if rho is not None else f"n/a (n={k})")
        rows.append((pos, *cells))
    L.append(md_table(["position"] + [f"{n} matches" for n in sizes], rows))
    L.append("")
    L.append("### 5b. Category scores vs the hidden abilities mapped to them\n")
    L.append("Mapping: " + "; ".join(f"{c} ← {', '.join(v)}" for c, v in G.CATEGORY_ABILITIES.items()) + ".\n")
    for n in (sizes[0], sizes[-1]):
        L.append(f"Spearman ρ with {n} matches per team:\n")
        rows = []
        for cat in G.CATEGORY_ABILITIES:
            cells = []
            for pos in D.OUTFIELD_GROUPS:
                rho, k = res["category"][(n, pos, cat)]
                cells.append(f"{rho:.2f}" if rho is not None else "n/a")
            rows.append((cat, *cells))
        L.append(md_table(["category"] + D.OUTFIELD_GROUPS, rows))
        L.append("")
    L.append("### 5c. Team effect on the position score\n")
    L.append("η² = share of the position-score variance explained by the team (squad seed × team); ρ(strength) = Spearman with the hidden team strength; "
             "within-team ρ = Spearman with the ground-truth composite after removing team means.\n")
    rows = []
    for pos in D.OUTFIELD_GROUPS:
        cells = []
        for n in (sizes[0], sizes[-1]):
            eta, rs, rw, k = res["team"][(n, pos)]
            cells += [f"{eta:.2f}" if eta is not None else "n/a", f"{rs:.2f}" if rs is not None else "n/a", f"{rw:.2f}" if rw is not None else "n/a"]
        rows.append((pos, *cells))
    L.append(md_table(["position", "η² (6)", "ρ strength (6)", "within-team ρ (6)", "η² (38)", "ρ strength (38)", "within-team ρ (38)"], rows))
    L.append("")
    L.append("### 5d. Summary (computed from the tables above)\n")
    def rng_of(n):
        vals = [res["curve"][(n, p)][0] for p in D.OUTFIELD_GROUPS if res["curve"][(n, p)][0] is not None]
        return (min(vals), max(vals)) if vals else (None, None)
    lo6, hi6 = rng_of(sizes[0]); lo38, hi38 = rng_of(sizes[-1])
    L.append(f"* Pooled over {len(seeds)} fresh squads, the Spearman ρ between position score and the hidden composite ranges from "
             f"{lo6:.2f} to {hi6:.2f} across positions with {sizes[0]} matches per team, and from {lo38:.2f} to {hi38:.2f} with {sizes[-1]} matches per team.")
    better = [p for p in D.OUTFIELD_GROUPS if res["curve"][(sizes[0], p)][0] is not None and res["curve"][(sizes[-1], p)][0] is not None
              and res["curve"][(sizes[-1], p)][0] > res["curve"][(sizes[0], p)][0]]
    L.append(f"* ρ is higher at {sizes[-1]} than at {sizes[0]} matches for {len(better)} of {len(D.OUTFIELD_GROUPS)} positions ({', '.join(better)}).")
    L.append("* A single 12-match tournament (7-17 ranked players per position) is much noisier than these pooled values; "
             "the seed-42 tournament in section 1 is one such sample.")
    L.append("* Section 5b shows which categories carry signal; section 5c shows how much of the position score is explained by the team.")
    L.append("")
    return L


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--kpi", default="data/kpi/final", help="profiles to evaluate (final = M01-M12)")
    ap.add_argument("--reference", default="data/reference")
    ap.add_argument("--out", default="scouting_validation.md")
    ap.add_argument("--diagnostics", action="store_true", help="sample-size curve, category and team diagnostics (slow)")
    ap.add_argument("--diag-seeds", default="2000-2011", help="squad seeds for the diagnostics")
    args = ap.parse_args()
    gt = {r["player_id"]: r for r in read_csv(os.path.join(args.data, "ground_truth_abilities.csv"))}
    players = {r["player_id"]: r for r in read_csv(os.path.join(args.data, "players.csv"))}
    profiles = read_csv(os.path.join(args.kpi, "player_profiles.csv"))
    ref = read_csv(os.path.join(args.reference, "reference_player_kpis.csv"))
    L = ["# Scouting validation (model vs hidden ground truth)\n",
         f"Profiles: `{args.kpi}/player_profiles.csv` (position score from events only). Ground truth: hidden ability composite "
         "per position (mean of the five abilities most relevant to the position, listed at the end). "
         "The weights were not tuned to the ground truth.\n"]

    # 1. Spearman per position and overall (primary profiles)
    prim = [p for p in profiles if p["profile_type"] == "primary" and p["ranking_status"] == "ranked"]
    L.append(f"Only ranked players (>= 180 minutes in the position, `ranking_status = ranked`) are used; "
             f"{sum(1 for p in profiles if p['profile_type'] == 'primary') - len(prim)} primary profiles are 'low_data' and excluded from rankings.\n")
    rows, all_x, all_y = [], [], []
    for pos in D.OUTFIELD_GROUPS:
        xs, ys = [], []
        for p in prim:
            if p["position_group"] != pos:
                continue
            xs.append(float(p["position_score"]))
            ys.append(composite(gt[p["player_id"]], pos, secondary=True))
        rho = spearman(xs, ys)
        rows.append((pos, len(xs), f"{rho:.2f}" if rho is not None else "n/a"))
        # overall: within-position ranks pooled (z-scored percent ranks)
        if len(xs) >= 3:
            all_x += [r / len(xs) for r in ranks(xs)]
            all_y += [r / len(ys) for r in ranks(ys)]
    rho_all = spearman(all_x, all_y)
    L.append("## 1. Rank correlation: position score vs ground-truth composite\n")
    L.append(md_table(["position", "players", "Spearman ρ"], rows + [("overall (within-position ranks pooled)", len(all_x), f"{rho_all:.2f}")]))
    L.append("")
    # by reliability
    L.append("## 2. Ranking quality by minutes / reliability\n")
    rel_rows = []
    for label in ("very low", "low", "medium", "good"):
        xs, ys = [], []
        for pos in D.OUTFIELD_GROUPS:
            sub = [p for p in prim if p["position_group"] == pos]
            if len(sub) < 3:
                continue
            sx = [float(p["position_score"]) for p in sub]
            sy = [composite(gt[p["player_id"]], pos, secondary=True) for p in sub]
            rx, ry = ranks(sx), ranks(sy)
            for i, p in enumerate(sub):
                if p["reliability"] == label:
                    xs.append(rx[i] / len(sub)); ys.append(ry[i] / len(sub))
        rho = spearman(xs, ys)
        mean_abs = statistics.fmean(abs(a - b) for a, b in zip(xs, ys)) if xs else None
        rel_rows.append((label, len(xs), f"{rho:.2f}" if rho is not None else "n/a", f"{mean_abs:.2f}" if mean_abs is not None else "n/a"))
    L.append(md_table(["reliability", "players", "Spearman ρ (within-position ranks)", "mean |rank gap| (0-1)"], rel_rows))
    L.append("\nRank gap = |model percent-rank − ground-truth percent-rank| within the position group; lower is better.\n")

    # 3. hidden talents
    L.append("## 3. Hidden talents (young standouts)\n")
    ref_by_pos = collections.defaultdict(list)
    for r in ref:
        ref_by_pos[r["position_group"]].append(r)
    trows = []
    for pid, g in gt.items():
        if g["standout"] != "young_gem":
            continue
        prof = [p for p in profiles if p["player_id"] == pid]
        if not prof:
            trows.append((pid, players[pid]["name"], players[pid]["age"], "no profile (no minutes)", "", "", "", "", ""))
            continue
        p = prof[0]
        pos = p["position_group"]
        group = sorted([q for q in prim if q["position_group"] == pos], key=lambda q: -float(q["position_score"]))
        if p["ranking_status"] != "ranked":
            cats = [float(p[k]) for k in p if k.startswith("cat_")]
            trows.append((pid, players[pid]["name"], players[pid]["age"], pos, "low data (not ranked)", "", p["position_score"],
                          f"{p['minutes']} ({p['reliability']})", f"{statistics.fmean(cats):.0f}"))
            continue
        rank = next(i + 1 for i, q in enumerate(group) if q["player_id"] == pid)
        gt_group = sorted(group, key=lambda q: -composite(gt[q["player_id"]], pos, secondary=True))
        gt_rank = next(i + 1 for i, q in enumerate(gt_group) if q["player_id"] == pid)
        # rank in the reference pool: share of pool players with a lower position score is not stored;
        # approximate with the mean KPI percentile of the profile's categories (already pool-based)
        cats = [float(p[k]) for k in p if k.startswith("cat_")]
        trows.append((pid, players[pid]["name"], players[pid]["age"], pos, f"{rank} / {len(group)}", f"{gt_rank} / {len(group)}",
                      p["position_score"], f"{p['minutes']} ({p['reliability']})", f"{statistics.fmean(cats):.0f}"))
    L.append(md_table(["player", "name", "age", "position", "model rank in group", "ground-truth rank", "position score", "minutes (reliability)", "mean category pct vs pool"], trows))
    L.append("\nThe model rank is the rank of the position score among the tournament's players of the same position (primary profiles); "
             "the ground-truth rank uses the hidden composite. 'Mean category pct vs pool' is the player's average category score, i.e. "
             "his standing against the reference pool of 50 fictional tournaments.\n")

    # 4. multi-positional players
    L.append("## 4. Multi-positional players: is the secondary-position drop visible?\n")
    mrows = []
    by_pid = collections.defaultdict(list)
    for p in profiles:
        by_pid[p["player_id"]].append(p)
    for pid, lst in sorted(by_pid.items()):
        if len(lst) < 2:
            continue
        a = next(p for p in lst if p["profile_type"] == "primary")
        b = next(p for p in lst if p["profile_type"] == "secondary")
        g = gt[pid]
        gt_a = composite(g, a["position_group"], secondary=True)
        gt_b = composite(g, b["position_group"], secondary=True)
        mrows.append((pid, players[pid]["name"], f"{a['position_group']} ({a['minutes']} min)", a["position_score"],
                      f"{b['position_group']} ({b['minutes']} min)", b["position_score"],
                      f"{float(b['position_score']) - float(a['position_score']):+.1f}", f"{gt_b - gt_a:+.1f}", g["secondary_penalty"]))
    if mrows:
        L.append(md_table(["player", "name", "main profile", "score", "secondary profile", "score", "model Δ", "ground-truth Δ", "hidden penalty"], mrows))
        same_sign = sum(1 for r in mrows if (float(r[6]) < 0) == (float(r[7]) < 0))
        L.append(f"\nSecondary profiles exist for {len(mrows)} players (≥ 90 minutes in the second position); the sign of the model difference "
                 f"matches the ground-truth difference for {same_sign} of them. Secondary profiles are low-minute samples, so this is weak evidence either way.\n")
    else:
        L.append("No player has ≥ 90 minutes in a second position, so no secondary profiles exist.\n")
    if args.diagnostics:
        L.extend(diagnostics_section(args))
    elif os.path.exists(args.out):
        # the diagnostics are slow (--diagnostics): a quick run keeps the section 5 computed last time
        import re
        last = re.search(r"\n(## 5\. Diagnostics.*?)\n## Notes", open(args.out, encoding="utf-8").read(), re.S)
        if last:
            L.append(last.group(1).strip() + "\n")
    L.append("## Notes\n")
    L.append("* Ground-truth composite per position: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in COMPOSITE.items()) + ".")
    L.append("* Six matches is a small sample; percentiles are shrunk towards the pool mean with k = 270 minutes, which pulls low-minute players towards average.")
    L.append("* The AM pool is small because only the 4-2-3-1 formation has an AM slot; AM players mostly play as wingers or central midfielders.")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
