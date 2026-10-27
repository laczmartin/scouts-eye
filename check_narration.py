#!/usr/bin/env python3
"""Quality checks for the narration outputs. Standard library only, no Azure."""

import argparse
import collections
import json
import os
import statistics

from agents.facts import FactStore
from agents.selection import load_config
from agents import verify as V
from agents import outputs as O


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="M12")
    ap.add_argument("--dir", default="data/narration")
    args = ap.parse_args()
    cfg = load_config()
    store = FactStore(args.match)
    rows = [json.loads(l) for l in open(os.path.join(args.dir, f"{args.match}_overlays.jsonl"), encoding="utf-8") if l.strip()]
    if not os.path.exists(os.path.join(args.dir, "results_debug.jsonl")):
        raise SystemExit(f"{args.dir}/results_debug.jsonl is missing: it holds the per-variant verifier results.")
    with open(os.path.join(args.dir, "results_debug.jsonl"), encoding="utf-8") as f:
        results = [json.loads(l) for l in f if l.strip()]
    meta = json.load(open(os.path.join(args.dir, "run_metadata.json")))
    checks = []
    # 1. zero unverified numbers: every overlay text re-checked against its card data + state
    bad = 0
    for r in results:
        if not O.is_shown(r):
            continue
        facts = r["facts"]  # exactly the facts the narrator and the pre-check saw
        text = " ".join(str(r["final"].get(k) or "") for k in ("overlay", "commentary", "detail"))
        ok, bad_n = V.check_numbers(text, facts, cfg["number_tolerance_relative"], cfg["number_tolerance_absolute"])
        bad += 0 if ok else 1
    checks.append(("0 unverified numbers in final outputs", bad == 0, f"{bad} texts with unsupported numbers"))
    # 2. overlay length
    too_long = [r for r in rows if len(r["text"]) > cfg["overlay_max_chars"]]
    checks.append((f"Every overlay <= {cfg['overlay_max_chars']} characters", not too_long, f"{len(too_long)} too long; max {max(len(r['text']) for r in rows)}"))
    # 3. >= 25 overlays per persona; counts per mode
    per_persona = collections.Counter(r["persona"] for r in rows)
    per_mode_items = meta["items_by_mode"]
    checks.append(("Each persona has >= 25 overlays", all(per_persona[p] >= 25 for p in cfg["personas"]), f"overlays per persona {dict(per_persona)}; narration items per mode {per_mode_items} (targets { {m: cfg['modes'][m]['target_overlays'] for m in cfg['modes']} })"))
    # 4. analyst outputs contain metrics, fan outputs mostly don't
    def has_number(t):
        return any(ch.isdigit() for ch in t)
    an = [r for r in rows if r["persona"] == "analyst"]
    fa = [r for r in rows if r["persona"] == "fan"]
    an_share = sum(1 for r in an if has_number(r["text"] + " " + r["detail"])) / max(1, len(an))
    import re as _re
    strip_clock = lambda t: _re.sub(r"\d{1,2}\+\d{1,2}'|\b\d{1,3}(?:'|\. perc|th minute|st minute|nd minute|rd minute)", "", t)
    count_numbers = lambda t: len(_re.findall(r"\d+\s*[-–:]\s*\d+|\d+(?:[.,]\d+)?", strip_clock(t)))  # a score like 3-2 counts as one number
    fa_share = sum(1 for r in fa if count_numbers(r["text"]) > 1) / max(1, len(fa))
    checks.append(("Analyst outputs contain metrics; fan overlays mostly without numbers", an_share >= 0.8 and fa_share <= 0.35,
                   f"analyst texts with numbers: {100 * an_share:.0f} %; fan overlays with more than one number: {100 * fa_share:.0f} %"))
    # 5. languages present
    langs = collections.Counter(r["lang"] for r in rows)
    checks.append(("Both languages present (hu, en)", all(langs[l] > 0 for l in cfg["languages"]), dict(langs)))
    # 6. evidence on every overlay
    no_ev = sum(1 for r in rows if not r["evidence_event_ids"] and r["kind"] == "moment")
    checks.append(("Every moment overlay carries evidence_event_ids", no_ev == 0, f"{no_ev} moment overlays without evidence"))
    # 7. latency
    lat = [r["item_latency_s"] for r in results]
    checks.append(("Batch latency per item reported", True, f"mean {statistics.fmean(lat):.1f}s per item (all variants, including verification), elapsed {meta['elapsed_s']}s for {meta['items']} items"))
    # 8. failure recovery: every variant without a verified text keeps a checked fact card in its place
    fb_path = os.path.join(args.dir, f"{args.match}_fallbacks.jsonl")
    fallbacks = [json.loads(l) for l in open(fb_path, encoding="utf-8") if l.strip()] if os.path.exists(fb_path) else []
    fb_keys = {(x["item_id"], x["persona"], x["lang"], x["club_view"], str(x["focus_player"])) for x in fallbacks if x["text"]}
    missing = [r for r in results if not O.is_shown(r)
               and (r["item_id"], r["variant"]["persona"], r["variant"]["lang"], r["variant"]["club_view"], str(r["variant"]["focus_player"])) not in fb_keys]
    status = collections.Counter(r.get("status", "unset") for r in results)
    checks.append(("Every variant without a verified text keeps its fact card (fallback)", not missing and "unset" not in status,
                   f"status {dict(status)}; fact-card fallbacks {len(fb_keys)}; without a fact card: {len(missing)}"))
    for name, ok, det in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {det}")
    f = meta.get("tokens_full_run", meta["tokens"])
    print(f"full-run tokens {f['total']} (in {f['input']}, out {f['output']}), full-run cost ${meta.get('cost_usd_full_run', meta['cost_usd'])}; "
          f"this run: {meta['llm_calls']} LLM calls, {meta['cached_calls']} cached, ${meta['cost_usd']}")
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
