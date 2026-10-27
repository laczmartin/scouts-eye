#!/usr/bin/env python3
"""Apply the targeted text fixes of config/targeted_edits.json (no LLM, no cost).

    python apply_targeted_edits.py            # check and apply; prints old -> new for every edit
    python apply_targeted_edits.py --check    # only check: every edit is in the files, every edited text passes the rules

A targeted fix replaces one exact phrase (it must occur exactly once); the rest of the text stays byte for byte.
All edits of one text are applied together and kept only if (a) the whole edited text passes the full rule set
(the pipeline's pre-check checks for an overlay; the document and recap checks for a recap) and (b) it has no
finding the original text did not have. Otherwise the original stays. The third condition, (c) the whole text was
read again by hand, is the reviewer's (data/comparison/manual_review.json). Applied edits are recorded:
an overlay's record in results_debug.jsonl gets 'edited' (shown in the agent trace as "edited: targeted fix"),
a document's edits go to run_metadata.json 'targeted_edits'. Afterwards run
`python run_agents.py --mode rebuild` and `python build_site.py`.
"""

import argparse
import collections
import json
import os
import sys

from agents import verify as V
from agents.facts import FactStore
from agents.selection import load_config

EDITS = "config/targeted_edits.json"
RESULTS = "data/narration/results_debug.jsonl"
META = "data/narration/run_metadata.json"
DATE = "2026-10-27"


def variant_key(v):
    return f"{v['persona']}|{v['lang']}|{v['club_view']}|{v['focus_player'] or ''}"


def overlay_findings(text_obj, rec, item, store, cfg, rules):
    """The pre-check's findings for an overlay text (numbers, names, claim rules and every text check), as strings."""
    v, facts = rec["variant"], rec["facts"]
    text = " ".join(str(text_obj.get(k) or "") for k in ("overlay", "commentary", "detail"))
    out = [f"number {x}" for x in V.check_numbers(text, facts, cfg["number_tolerance_relative"], cfg["number_tolerance_absolute"])[1]]
    out += [f"name {x}" for x in V.check_names(text, facts, store)[1]]
    out += [f"claim {c['rule']}: {c['matched']}" for c in V.check_claims(text, v["lang"], item, store, rules, player_id=v["focus_player"]) if not c["supported"]]
    if len(text_obj.get("overlay") or "") > cfg["overlay_max_chars"]:
        out.append("overlay too long")
    core, player, wording = V.semantic_checks(text, text_obj, v["lang"], item, store, cfg, facts["state"], facts.get("moment"), v["focus_player"])
    return sorted(set(out + core + player + wording))


def doc_findings(text, path, store, recap_facts):
    lang = "hu" if path.endswith("_hu.md") else "en"
    if "_recap_" in os.path.basename(path):
        return sorted(set(V.check_document(text, lang, store) + V.check_recap(text, lang, recap_facts, store)))
    return sorted(set(V.check_document(text, lang, store) + V.check_scouting(text, lang, store)))


def on_disk(text, e):
    """Is the edit in the text as it is now (the new phrase there, the old one gone)?"""
    return e["new"] in text and e["old"] not in text


def replace_once(text, old, new):
    """(new text, status): 'applied', 'already applied', or an error."""
    n_old, n_new = text.count(old), text.count(new)
    if n_old == 1:
        return text.replace(old, new, 1), "applied"
    if n_old == 0 and n_new >= 1:
        return text, "already applied"
    return text, f"the phrase occurs {n_old} times (must occur exactly once)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only check; write nothing")
    args = ap.parse_args()
    import run_agents
    store, cfg, rules = FactStore("M12"), load_config(), V.load_rules()
    edits = json.load(open(EDITS, encoding="utf-8"))["edits"]
    results = [json.loads(l) for l in open(RESULTS, encoding="utf-8") if l.strip()]
    items = {it["item_id"]: it for it in run_agents.build_items(store, cfg)}
    recap_facts = run_agents.build_recap_facts(store, results)
    groups = collections.OrderedDict()
    for e in edits:
        key = ("overlay", e["item_id"], e["variant"], e["field"]) if e["target"] == "overlay" else ("doc", e["file"])
        groups.setdefault(key, []).append(e)
    ok_all, report, meta_doc = True, [], []
    for key, es in groups.items():
        if key[0] == "overlay":
            rec = next(r for r in results if r["item_id"] == key[1] and variant_key(r["variant"]) == key[2])
            field = key[3]
            now = rec["final"][field]
            original = dict(rec["final"])
            if rec.get("edited") and rec["edited"].get("field") == field:
                original = dict(rec["final"], **{field: rec["edited"]["original"]})
            text = original[field]
            find = lambda t: overlay_findings(dict(original, **{field: t}), rec, items[rec["item_id"]], store, cfg, rules)
            label = f"{key[1]} {key[2]} {field}"
            present = [on_disk(now, e) and (rec.get("edited") or {}).get("kind") == "targeted fix" and e["id"] in rec["edited"]["ids"] for e in es]
        else:
            path = key[1]
            full = open(path, encoding="utf-8").read()
            text = full.split("\n\n<sub>Source")[0]      # the agent's text; the sources line stays as it is
            tail = full[len(text):]
            find = lambda t, p=path: doc_findings(t, p, store, recap_facts)
            label = path
            present = [on_disk(text, e) for e in es]
        statuses = []
        for e in es:
            text, st = replace_once(text, e["old"], e["new"])
            statuses.append(st)
        if any(s.startswith("the phrase") for s in statuses):
            ok_all = False
            report.append((label, "NOT APPLIED", statuses, [], []))
            continue
        # the original text: every applied edit undone (for an already applied edit, its new phrase back to the old one)
        orig_text = text
        for e in reversed(es):
            orig_text = orig_text.replace(e["new"], e["old"], 1)
        f_orig, f_new = find(orig_text), find(text)
        new_only = [f for f in f_new if f not in f_orig]
        accepted = not f_new and not new_only
        if args.check and not all(present):
            ok_all = False
            statuses = [st + ("" if p else " (NOT in the file yet)") for st, p in zip(statuses, present)]
        report.append((label, "ACCEPTED" if accepted else "REJECTED (the original stays)", statuses, f_orig, f_new))
        if not accepted:
            ok_all = False
            continue
        if key[0] == "doc":     # the metadata lists every accepted recap edit that is in the file, applied now or before
            meta_doc += [dict(id=e["id"], file=path, old=e["old"], new=e["new"], reason=e["reason"], date=DATE, kind="targeted fix") for e in es]
        if args.check or all(s == "already applied" for s in statuses):
            continue
        if key[0] == "overlay":
            rec["edited"] = dict(kind="targeted fix", date=DATE, field=field, ids=[e["id"] for e in es],
                                 replacements=[dict(old=e["old"], new=e["new"], reason=e["reason"]) for e in es],
                                 original=original[field],
                                 checks="full rule set: 0 findings, no finding the original did not have; the whole text read again by hand",
                                 verifier="the Verifier LLM verified the original text; the edit was checked by the deterministic rules and by hand, not by an LLM")
            rec["final"][field] = text
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text + tail)
    for label, verdict, statuses, f_orig, f_new in report:
        print(f"{verdict:<32} {label}: {', '.join(statuses)}")
        print(f"   findings before: {len(f_orig)}" + "".join(f"\n      - {x[:150]}" for x in f_orig))
        print(f"   findings after:  {len(f_new)}" + "".join(f"\n      - {x[:150]}" for x in f_new))
    if not args.check:
        if any(r.get("edited") for r in results):
            with open(RESULTS, "w", encoding="utf-8") as fh:
                for r in results:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        meta = json.load(open(META))
        if meta.get("targeted_edits", []) != meta_doc:     # only the recap edits that are in the files now
            meta["targeted_edits"] = meta_doc
            json.dump(meta, open(META, "w"), indent=2)
        for e in edits:
            print(f"  {e['id']:<4} {e.get('file') or e['item_id'] + ' ' + e['variant']}\n       old: {e['old']}\n       new: {e['new']}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
