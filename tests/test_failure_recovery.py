#!/usr/bin/env python3
"""Failure-recovery test with artificially induced faults. No Azure, no LLM, no cost.

A fake model replaces Microsoft Foundry (agents/llm.py `backend=`). It answers like
the real agents would (insight card, narrator text, verifier verdict) using the
deterministic fact cards, and injects faults on request: timeout, HTTP 429,
invalid JSON, verifier rejection, service error, an unexpected exception inside
one step, and the whole service being down. The real workflow (Microsoft Agent
Framework fan-out / fan-in), the real pre-check and the real output writers run.

    python3 tests/test_failure_recovery.py          # prints the table, writes data/narration/failure_recovery_test.json

Needs the packages of requirements-agents.txt (agent-framework); no Azure login, no network.
"""

import asyncio
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import factcards as FC          # noqa: E402
from agents import outputs as O             # noqa: E402
from agents import verify as V              # noqa: E402
from agents.cache import ResponseCache      # noqa: E402
from agents.facts import FactStore          # noqa: E402
from agents.llm import LLMRuntime           # noqa: E402
from agents.pipeline import deterministic_card, run_items  # noqa: E402
from agents.selection import load_config    # noqa: E402
import run_agents                           # noqa: E402

TIMEOUT_S = 0.25          # per call in the test (production: config/narration.json llm_timeout_s = 60)
BACKOFF_SCALE = 0.001     # back-off delays scaled down (production: 1.0)


class FakeBackend:
    """Answers like the five agents, from the facts; injects the faults listed in `faults`.

    A fault: dict(agent, item=None|item_id, variant=None|(persona, lang, club_view), kind, times=None|N)
    kind: timeout | rate_limit | invalid_json | reject | service_error."""

    def __init__(self, store, items, faults=()):
        self.store, self.items = store, {it["item_id"]: it for it in items}
        self.faults = [dict(f, used=0) for f in faults]
        self.calls = 0

    def _match(self, agent, meta):
        for f in self.faults:
            if f["agent"] not in (agent, "*"):
                continue
            if f.get("item") and meta.get("item_id") != f["item"]:
                continue
            if f.get("variant") and (meta.get("persona"), meta.get("lang"), meta.get("club_view", "neutral")) != f["variant"]:
                continue
            if f.get("first_draft_only") and meta.get("repair"):
                continue
            if f.get("times") is not None and f["used"] >= f["times"]:
                continue
            f["used"] += 1
            return f["kind"]
        return None

    async def respond(self, agent, prompt, meta):
        self.calls += 1
        fault = self._match(agent, meta)
        if fault == "timeout":
            await asyncio.sleep(TIMEOUT_S * 8)
        elif fault == "rate_limit":
            raise RuntimeError("Error code: 429 - {'error': {'code': 'RateLimitReached', 'message': 'rate limit exceeded'}}")
        elif fault == "service_error":
            raise RuntimeError("503 Service Unavailable")
        elif fault == "invalid_json":
            return self._wrap("Sorry, here is the answer: {broken json")
        await asyncio.sleep(0.005)
        item = self.items.get(meta.get("item_id"))
        if agent == "analyst":
            card = deterministic_card(self.store, item, {})
            card["source_fields"] = ["fake analyst"]
            return self._wrap(json.dumps(card, ensure_ascii=False))
        if agent == "scout":
            return self._wrap(json.dumps(dict(summary_facts=[], strengths=[], weaknesses=[], reliability_note="fake scout note", data={}, source_fields=[])))
        if agent == "narrator":
            fc = dict(FC.fact_card(self.store, item, meta["lang"]))
            if meta.get("focus_player"):
                fc["text"] = f"{self.store.player_name(meta['focus_player'])}: {fc['text']}"[:90]
            # the commentary differs per club view, so each variant gets its own Verifier call (no shared cache entry)
            view = {"neutral": "view a", "T1": "view b", "T2": "view c"}.get(meta.get("club_view"), "view d")
            return self._wrap(json.dumps(dict(overlay=fc["text"], commentary=f"{fc['text']} [{view}]", detail=""), ensure_ascii=False))
        if agent == "verifier":
            if fault == "reject":
                return self._wrap(json.dumps(dict(verdict="reject", reasons=["fake rejection: claim not supported"])))
            vin = json.loads(prompt.split("INPUT:\n", 1)[1])
            return self._wrap(json.dumps(dict(vin["text"], verdict="ok", reasons=["fake verifier: ok"]), ensure_ascii=False))
        return self._wrap("# Recap\n\nfake recap text")

    @staticmethod
    def _wrap(text):
        return dict(text=text, usage=dict(input=10, output=10, total=20))


def pick_items(store, cfg):
    """A small, mixed set: a fan goal, an analyst state card and a player-focus item."""
    items = run_agents.build_items(store, cfg)
    fan = next(it for it in items if it["mode"] == "fan" and it["kind"] == "moment" and it["moment"]["type"] == "goal")
    ana = next(it for it in items if it["mode"] == "analyst" and it["kind"] == "state")
    foc = next(it for it in items if it["mode"] == "focus" and it["kind"] == "moment")
    return [fan, ana, foc]


async def run_scenario(store, cfg, items, faults=(), patch=None, budget=None):
    tmp = tempfile.mkdtemp(prefix="sx_fail_")
    c = dict(cfg, llm_timeout_s=TIMEOUT_S, llm_backoff_scale=BACKOFF_SCALE)
    backend = FakeBackend(store, items, faults)
    rt = LLMRuntime(store, c, ResponseCache(os.path.join(tmp, "cache")), os.path.join(tmp, "log.jsonl"), backend=backend, concurrency=3,
                    budget_usd=budget, reserve_usd=0.0)
    undo = patch() if patch else None
    t0 = time.time()
    error = None
    try:
        results, _ = await run_items(rt, store, V.load_rules(), items, c)
    except Exception as exc:  # the run must never stop; recorded as a failure of the test
        results, error = [], f"{type(exc).__name__}: {exc}"
    finally:
        if undo:
            undo()
    elapsed = time.time() - t0
    for r in results:
        it = next(i for i in items if i["item_id"] == r["item_id"])
        r["fact_card"] = FC.checked_fact_card(store, it, r["variant"]["lang"], c)
    fallbacks = O.write_fallbacks(results, os.path.join(tmp, "fallbacks.jsonl"), c)
    overlays = O.write_overlays(results, os.path.join(tmp, "overlays.jsonl"), c)
    return dict(results=results, fallbacks=fallbacks, overlays=overlays, elapsed=elapsed, error=error, rt=rt, backend=backend)


def vkey(r):
    v = r["variant"]
    return (r["item_id"], v["persona"], v["lang"], v["club_view"])


def summarize(res, target):
    """Status of the targeted variants vs. all the others, and whether the fact card stayed where no text exists."""
    hit = [r for r in res["results"] if target(r)]
    rest = [r for r in res["results"] if not target(r)]
    fb_ok = all(any(f["item_id"] == r["item_id"] and f["persona"] == r["variant"]["persona"] and f["lang"] == r["variant"]["lang"]
                    and f["club_view"] == r["variant"]["club_view"] and f["text"] for f in res["fallbacks"])
                for r in res["results"] if not O.is_shown(r))
    st = lambda rs: dict(sorted(__import__("collections").Counter(r["status"] for r in rs).items()))
    marks = sorted({f"{x['agent']}:{x['kind']}" for r in hit for x in r.get("recovery", [])})
    return hit, rest, fb_ok, st(hit), st(rest), marks


async def main_async():
    cfg = load_config()
    store = FactStore("M12")
    items = pick_items(store, cfg)
    fan, ana, foc = items
    one = (fan["item_id"], ("fan", "hu", "neutral"))
    is_one = lambda r: r["item_id"] == one[0] and (r["variant"]["persona"], r["variant"]["lang"], r["variant"]["club_view"]) == one[1]
    is_item = lambda iid: (lambda r: r["item_id"] == iid)

    def patch_check_claims():
        orig = V.check_claims
        def boom(text, lang, item, *a, **k):
            if item["item_id"] == ana["item_id"] and lang == "en":
                raise ValueError("injected bug inside the pre-check")
            return orig(text, lang, item, *a, **k)
        V.check_claims = boom
        return lambda: setattr(V, "check_claims", orig)

    def patch_item_crash():
        orig = store.state_at_ms
        def boom(t_ms):
            if t_ms == foc["t_ms"]:
                raise KeyError("injected bug while building the facts of one item")
            return orig(t_ms)
        store.state_at_ms = boom
        return lambda: setattr(store, "state_at_ms", orig)

    S = [
        ("baseline", "no fault", lambda r: True, [], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"verified": len(hit)}, "all variants verified"),
        ("timeout, once", "Narrator (1 variant): first call exceeds the time limit", is_one,
         [dict(agent="narrator", item=one[0], variant=one[1], kind="timeout", times=1)], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"recovered": 1} and "narrator:retried" in m, "retried after the time limit, text verified → recovered"),
        ("timeout, persistent", "Analyst (1 item): every call exceeds the time limit", is_item(fan["item_id"]),
         [dict(agent="analyst", item=fan["item_id"], kind="timeout")], None,
         lambda hit, rest, fb, sh, sr, m: set(sh) == {"recovered"} and "analyst:timeout" in m, "3 attempts, then deterministic insight card; narration and verification continue → recovered"),
        ("timeout, verifier", "Verifier (1 variant): every call exceeds the time limit", is_one,
         [dict(agent="verifier", item=one[0], variant=one[1], kind="timeout")], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"fallback": 1} and fb and "verifier:timeout" in m, "no verified text → fact card stays (fallback)"),
        ("429, transient", "Narrator (1 variant): HTTP 429 twice, then OK", is_one,
         [dict(agent="narrator", item=one[0], variant=one[1], kind="rate_limit", times=2)], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"recovered": 1} and "narrator:retried" in m, "back-off and retry, text verified → recovered"),
        ("429, persistent", "Narrator (1 variant): HTTP 429 on every call", is_one,
         [dict(agent="narrator", item=one[0], variant=one[1], kind="rate_limit")], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"fallback": 1} and fb and "narrator:rate_limit" in m, "9 attempts with back-off, then fact card stays (fallback)"),
        ("invalid JSON, Analyst", "Analyst (1 item): unreadable answer", is_item(ana["item_id"]),
         [dict(agent="analyst", item=ana["item_id"], kind="invalid_json")], None,
         lambda hit, rest, fb, sh, sr, m: set(sh) == {"recovered"} and "analyst:invalid_json" in m, "deterministic insight card, narration continues → recovered"),
        ("invalid JSON, Narrator", "Narrator (1 variant): first draft unreadable", is_one,
         [dict(agent="narrator", item=one[0], variant=one[1], kind="invalid_json", first_draft_only=True)], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"recovered": 1} and "narrator:invalid_json" in m, "empty draft fails the pre-check, one repair round → recovered"),
        ("invalid JSON, Verifier", "Verifier (1 variant): unreadable answer", is_one,
         [dict(agent="verifier", item=one[0], variant=one[1], kind="invalid_json")], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"recovered": 1} and "verifier:invalid_json" in m, "keeps the text that passed the deterministic pre-check → recovered"),
        ("verifier rejection", "Verifier (1 variant): verdict reject", is_one,
         [dict(agent="verifier", item=one[0], variant=one[1], kind="reject")], None,
         lambda hit, rest, fb, sh, sr, m: sh == {"fallback": 1} and fb and "verifier:rejected" in m, "text dropped and logged, fact card stays (fallback)"),
        ("bug inside one step", "pre-check raises an exception (1 item, EN)", lambda r: r["item_id"] == ana["item_id"] and r["variant"]["lang"] == "en",
         [], patch_check_claims,
         lambda hit, rest, fb, sh, sr, m: set(sh) == {"fallback"} and fb and "verify step:exception" in m, "only that variant falls back to the fact card"),
        ("bug inside one item", "building the facts of one item raises an exception", is_item(foc["item_id"]),
         [], patch_item_crash,
         lambda hit, rest, fb, sh, sr, m: set(sh) == {"fallback"} and any(x.startswith("workflow:") for x in m), "the item's variants fall back; the other items are not affected"),
        ("service down", "every agent call fails (503)", lambda r: True,
         [dict(agent="*", kind="service_error")], None,
         lambda hit, rest, fb, sh, sr, m: set(sh) == {"fallback"} and fb, "every variant keeps its fact card; the run still finishes"),
        ("spending limit", "the cost limit is reached after about 10 calls", lambda r: r["status"] != "verified",
         [], None,
         lambda hit, rest, fb, sh, sr, m: bool(hit) and "fallback" in sh and fb and any(x.endswith(":budget") for x in m),
         "no new paid call starts; the variants still waiting keep their fact card, the run finishes", 0.0002),
    ]
    rows = []
    base_keys = None
    for name, fault, target, faults, patch, expect, expected_text, *budget in S:
        res = await run_scenario(store, cfg, items, faults, patch, budget[0] if budget else None)
        hit, rest, fb_ok, sh, sr, marks = summarize(res, target)
        if base_keys is None:
            base_keys = {vkey(r) for r in res["results"]}
        complete = res["error"] is None and {vkey(r) for r in res["results"]} == base_keys
        rest_ok = all(r["status"] == "verified" for r in rest)
        ok = complete and rest_ok and expect(hit, rest, fb_ok, sh, sr, marks)
        rows.append(dict(scenario=name, injected_fault=fault, expected=expected_text, run_completed=complete,
                         affected_variants=len(hit), affected_status=sh, other_variants=len(rest), other_status=sr,
                         trace_marks=marks, fact_card_in_place=fb_ok, elapsed_s=round(res["elapsed"], 2), calls=res["backend"].calls,
                         passed=ok, error=res["error"]))
    # documents (recap / scouting notes): agent unavailable -> deterministic fallback text
    c = dict(cfg, llm_timeout_s=TIMEOUT_S, llm_backoff_scale=BACKOFF_SCALE)
    tmp = tempfile.mkdtemp(prefix="sx_fail_doc_")
    rt = LLMRuntime(store, c, ResponseCache(os.path.join(tmp, "cache")), os.path.join(tmp, "log.jsonl"),
                    backend=FakeBackend(store, items, [dict(agent="recap", kind="service_error")]))
    t0 = time.time()
    text = await run_agents.checked_document(rt, "recap", "Write the recap.", "en", dict(kind="recap", persona="fan", lang="en"),
                                             fallback=run_agents.fallback_recap(store, "en"))
    doc_ok = text.startswith("# Recap (fallback") and any(e.get("status") == "fallback" for e in rt.log if e.get("agent") == "document_check")
    rows.append(dict(scenario="recap agent down", injected_fault="Recap writer: every call fails (503)", expected="deterministic recap (score and goals) is written; the run goes on",
                     run_completed=True, affected_variants=1, affected_status={"fallback": 1} if doc_ok else {}, other_variants=0, other_status={},
                     trace_marks=["document_check:fallback"] if doc_ok else [], fact_card_in_place=doc_ok, elapsed_s=round(time.time() - t0, 2),
                     calls=rt.backend.calls, passed=doc_ok, error=None))
    return rows, items


def to_markdown(rows):
    L = ["| # | scenario | injected fault | what the system did | affected | others | trace mark | fact card in place | result |",
         "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        st = ", ".join(f"{k} {v}" for k, v in r["affected_status"].items()) or "–"
        ot = ", ".join(f"{k} {v}" for k, v in r["other_status"].items()) or "–"
        fc = "yes" if r["fact_card_in_place"] else ("n/a" if not any(k == "fallback" for k in r["affected_status"]) else "NO")
        L.append(f"| {i} | {r['scenario']} | {r['injected_fault']} | {r['expected']} | {st} | {ot} | {', '.join(r['trace_marks']) or '–'} | {fc} | {'PASS' if r['passed'] else 'FAIL'} |")
    return "\n".join(L)


def main():
    rows, items = asyncio.run(main_async())
    md = to_markdown(rows)
    print(md)
    out = dict(note="tests/test_failure_recovery.py: fake model, no Azure, no cost. Time limit per call in the test "
                    f"{TIMEOUT_S}s, back-off scaled by {BACKOFF_SCALE} (production: 60 s and 1.0).",
               items=[it["item_id"] for it in items], timeout_s=TIMEOUT_S, backoff_scale=BACKOFF_SCALE, rows=rows,
               passed=sum(r["passed"] for r in rows), total=len(rows))
    with open("data/narration/failure_recovery_test.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n{out['passed']}/{out['total']} scenarios passed")
    return 0 if out["passed"] == out["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
