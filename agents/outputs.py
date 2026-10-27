"""Writers for data/narration/: overlays, commentary, recap, scouting notes, verifier report."""

import collections
import json
import os

from agents import verify as V


def overlay_layout(rec):
    if rec["variant"]["focus_player"]:
        return "player_card"
    if rec["mode"] == "fan":
        t = rec["card"].get("type", "")
        return "scorebug_note" if t == "goal" else "lower_third"
    return "side_card" if rec["card"].get("type") == "state" else "lower_third"


def is_shown(r):
    """A verified (or recovered) agent text exists for this variant."""
    return r["verdict"] not in ("reject", "fallback") and bool(r["final"])


def annotate_status(rec, log_entries):
    """Fill `status` / `recovery` for a result written before these fields existed (same rules as agents/pipeline.py).

    log_entries: the agent-log entries of this record's trace. Only facts already in the record or the log are used."""
    if "status" in rec:
        return rec
    v = rec["variant"]
    recovery = []
    for e in log_entries:
        if e.get("ok", True) or e.get("status") == "failed":
            continue
        if e["agent"] == "analyst":
            recovery.append(dict(agent="analyst", kind="invalid_json", action="deterministic insight card from the facts"))
        elif e["agent"] == "scout" and rec["mode"] == "focus":
            recovery.append(dict(agent="scout", kind="invalid_json", action="narrated without the scout note"))
        elif e["agent"] == "narrator" and (e.get("persona"), e.get("lang"), e.get("club_view"), e.get("focus_player")) == (v["persona"], v["lang"], v["club_view"], v["focus_player"]):
            recovery.append(dict(agent="narrator", kind="invalid_json", action="treated as a failed pre-check; one repair round"))
    if any("verifier output unparsable" in str(x) for x in rec.get("reasons", [])):
        recovery.append(dict(agent="verifier", kind="invalid_json", action="kept the text that passed the deterministic pre-check"))
    if rec["verdict"] == "reject":
        last = rec["attempts"][-1]["precheck"]["passed"] if rec.get("attempts") else False
        recovery.append(dict(agent="verifier" if last else "pre-check", kind="rejected", action="fact card stays"))
    rec["recovery"] = recovery
    rec["status"] = "fallback" if rec["verdict"] in ("reject", "fallback") else ("recovered" if recovery else "verified")
    return rec


def write_fallbacks(results, path, cfg):
    """Fact cards that stay on screen where no verified agent text exists (rejected or failed variants)."""
    rows = []
    for r in results:
        if is_shown(r):
            continue
        fc = r.get("fact_card") or {}
        v = r["variant"]
        rows.append(dict(t_ms=r["t_ms"], minute=r["minute"], clock=r.get("clock"), period=r.get("period"), duration_ms=cfg["overlay_duration_ms"], layout=overlay_layout(r),
                         persona=v["persona"], lang=v["lang"], club_view=v["club_view"], focus_player=v["focus_player"],
                         text=fc.get("text") if fc and not fc.get("problems") else None, detail="",
                         data=fc.get("data", {}), evidence_event_ids=fc.get("evidence_event_ids", r["card"].get("evidence_event_ids", [])),
                         source_fields=["fact_card"], verified=False, agent_trace_id=r["trace"], mode=r["mode"], kind=r["kind"], item_id=r["item_id"],
                         verdict=r["verdict"], status="fallback", fallback=True, reasons=r.get("reasons", [])[:3],
                         recovery=[dict(agent=x.get("agent"), kind=x.get("kind"), action=x.get("action")) for x in r.get("recovery", [])],
                         fact_card=fc.get("text"), fact_card_problems=fc.get("problems", [])))
    rows.sort(key=lambda x: (x["t_ms"], x["persona"], x["lang"], x["club_view"], str(x["focus_player"])))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def shown(text, lang):
    """The text as shown: Hungarian texts get the decimal comma (57,1 %); the verified record keeps the agent's text."""
    return V.hu_decimal_commas(text) if lang == "hu" else text


def write_overlays(results, path, cfg):
    rows = []
    for r in results:
        if not is_shown(r):
            continue
        v = r["variant"]
        rows.append(dict(t_ms=r["t_ms"], minute=r["minute"], clock=r.get("clock"), period=r.get("period"), duration_ms=cfg["overlay_duration_ms"], layout=overlay_layout(r),
                         persona=v["persona"], lang=v["lang"], club_view=v["club_view"], focus_player=v["focus_player"],
                         text=shown(r["final"]["overlay"], v["lang"]), detail=shown(r["final"].get("commentary") or r["final"].get("detail") or "", v["lang"]),
                         data=r["card"].get("data", {}), evidence_event_ids=r["card"].get("evidence_event_ids", []),
                         source_fields=r["card"].get("source_fields", []), verified=True, agent_trace_id=r["trace"],
                         mode=r["mode"], kind=r["kind"], item_id=r["item_id"], verdict=r["verdict"],
                         fact_card=(r.get("fact_card") or {}).get("text"), upgraded=r.get("upgraded_from_fact_card", bool(r.get("fact_card"))),
                         fact_card_latency_s=r.get("fact_card_latency_s"), live_latency_s=r.get("live_latency_s"),
                         status=r.get("status", "verified"), recovery=[dict(agent=x.get("agent"), kind=x.get("kind"), action=x.get("action")) for x in r.get("recovery", [])],
                         **({"edited": "targeted fix"} if r.get("edited") else {})))
    rows.sort(key=lambda x: (x["t_ms"], x["persona"], x["lang"], x["club_view"], str(x["focus_player"])))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def write_commentary(results, out_dir, store, cfg):
    for persona in cfg["personas"]:
        for lang in cfg["languages"]:
            lines = [r for r in results if is_shown(r) and r["variant"]["persona"] == persona
                     and r["variant"]["lang"] == lang and r["variant"]["club_view"] == "neutral" and not r["variant"]["focus_player"]]
            title = {"hu": f"# {store.match_id} – kommentár ({persona})", "en": f"# {store.match_id} – commentary ({persona})"}[lang]
            L = [title, "", f"{store.team_name(store.home)} – {store.team_name(store.away)}", ""]
            for r in lines:
                L.append(f"**{r.get('clock') or str(r['minute']) + chr(39)}** {shown(r['final']['commentary'], lang)}  ")
                L.append(f"<sub>evidence: {', '.join(r['card'].get('evidence_event_ids', [])[:4]) or '–'} · {r['trace']}</sub>")
                L.append("")
            with open(os.path.join(out_dir, f"{store.match_id}_commentary_{persona}_{lang}.md"), "w", encoding="utf-8") as f:
                f.write("\n".join(L))


def write_verifier_report(results, path, cfg, lang_samples=5):
    n = len(results)
    by_verdict = collections.Counter(r["verdict"] for r in results)
    by_status = collections.Counter(r.get("status", "verified") for r in results)
    recov = collections.Counter((x.get("agent"), x.get("kind")) for r in results for x in r.get("recovery", []))
    failed_calls = [r for r in results if r["verdict"] == "fallback"]
    results = [r for r in results if r.get("attempts")]   # variants whose narrator text reached the pre-check
    repaired_pre = sum(1 for r in results if len(r["attempts"]) > 1)
    pre_fail_first = sum(1 for r in results if not r["attempts"][0]["precheck"]["passed"])
    num_fail = sum(1 for r in results if not r["attempts"][0]["precheck"]["numbers_ok"])
    name_fail = sum(1 for r in results if not r["attempts"][0]["precheck"]["names_ok"])
    long_fail = sum(1 for r in results if r["attempts"][0]["precheck"]["overlay_too_long"])
    claims = [c for r in results for c in r["attempts"][0]["precheck"]["claims"]]
    claim_by_rule = collections.Counter((c["rule"], c["supported"]) for c in claims)
    claim_items = sum(1 for r in results if r["attempts"][0]["precheck"]["claims"])
    claim_fail_items = sum(1 for r in results if r["attempts"][0]["precheck"]["unsupported_claims"])
    claim_fixed = sum(1 for r in results if r["attempts"][0]["precheck"]["unsupported_claims"] and r["verdict"] != "reject")
    L = ["# Verifier report", "",
         f"Items (text variants) processed: **{n}** · verified ok: {by_verdict['ok']} · repaired by the Verifier LLM: {by_verdict['repaired']} · rejected (fact card stays): {by_verdict['reject']}"
         + (f" · agent call failed (fact card stays): {by_verdict['fallback']}" if by_verdict['fallback'] else ""), "",
         "## Failure recovery", "",
         f"* status of the {n} text variants: verified {by_status['verified']} · recovered {by_status['recovered']} · fallback to the fact card {by_status['fallback']}",
         "* recovered = a step failed (unreadable answer, retried call) but a checked text was still produced; fallback = no verified text, the deterministic fact card stays", "",
         "| agent / step | what happened | count |", "|---|---|---|"]
    L += [f"| {a} | {k} | {c} |" for (a, k), c in sorted(recov.items(), key=lambda x: (-x[1], str(x[0])))] or ["| – | – | 0 |"]
    if failed_calls:
        L += ["", "Variants whose agent call failed after its retries:", ""]
        L += [f"* {r['variant']['persona']}/{r['variant']['lang']} {r['minute']}' ({r['mode']}): {r['reasons']}" for r in failed_calls[:10]]
    L += ["",
         "## Deterministic pre-check (before the Verifier LLM)", "",
         f"* first narrator text failed the pre-check: {pre_fail_first} of {len(results)} ({100 * pre_fail_first / max(1, len(results)):.0f} %); sent back to the Narrator once: {repaired_pre}",
         f"* unsupported numbers: {num_fail} · unknown names: {name_fail} · overlay longer than {cfg['overlay_max_chars']} characters: {long_fail}", "",
         "## Professional claims (config/claim_rules.json)", "",
         f"* texts containing a rule-matched claim: {claim_items} · with at least one unsupported claim: {claim_fail_items} · of those kept after repair: {claim_fixed}, dropped: {claim_fail_items - claim_fixed}", "",
         "| rule | supported | unsupported |", "|---|---|---|"]
    for rule in sorted({c["rule"] for c in claims}):
        L.append(f"| {rule} | {claim_by_rule[(rule, True)]} | {claim_by_rule[(rule, False)]} |")
    L += ["", "### Examples of claim repairs", ""]
    shown = 0
    for r in results:
        a0 = r["attempts"][0]["precheck"]
        if a0["unsupported_claims"] and r["final"] and shown < 3:
            c = a0["unsupported_claims"][0]
            L.append(f"* **{r['variant']['persona']}/{r['variant']['lang']}, {r['minute']}'** – claim \"{c['matched']}\" (rule {c['rule']}) not supported by {json.dumps(c['evidence'], ensure_ascii=False)[:220]}")
            L.append(f"  * before: _{r['attempts'][0]['text'].get('overlay', '')}_ / {r['attempts'][0]['text'].get('commentary', '')}")
            L.append(f"  * after: _{r['final']['overlay']}_ / {r['final']['commentary']}")
            shown += 1
    L += ["", "### Examples of number / name repairs", ""]
    shown = 0
    for r in results:
        a0 = r["attempts"][0]["precheck"]
        if (a0["bad_numbers"] or a0["bad_names"]) and r["final"] and shown < 3:
            L.append(f"* **{r['variant']['persona']}/{r['variant']['lang']}, {r['minute']}'** – bad numbers {a0['bad_numbers']}, bad names {a0['bad_names']}")
            L.append(f"  * before: _{r['attempts'][0]['text'].get('overlay', '')}_ / {r['attempts'][0]['text'].get('commentary', '')}")
            L.append(f"  * after: _{r['final']['overlay']}_ / {r['final']['commentary']}")
            shown += 1
    L += ["", "### Rejected items (the fact card stays on screen)", ""]
    rej = [r for r in results if r["verdict"] == "reject"]
    L += [f"* {r['variant']['persona']}/{r['variant']['lang']} {r['minute']}' ({r['mode']}): {r['reasons']}" for r in rej[:10]] or ["* none"]
    L += ["", "## Language spot-check (5 lines per language)", ""]
    for lang in cfg["languages"]:
        L.append(f"### {lang}")
        for r in [x for x in results if x["final"] and x["variant"]["lang"] == lang and x["variant"]["club_view"] == "neutral"][:lang_samples]:
            L.append(f"* {r['minute']}' [{r['variant']['persona']}] {r['final']['overlay']}")
        L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return dict(items=n, **{k: by_verdict[k] for k in ("ok", "repaired", "reject")}, precheck_failed=pre_fail_first, claim_items=claim_items,
                claim_unsupported=claim_fail_items, **({"call_failed": by_verdict["fallback"]} if by_verdict["fallback"] else {}),
                status=dict(verified=by_status["verified"], recovered=by_status["recovered"], fallback=by_status["fallback"]))
