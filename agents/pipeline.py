"""Orchestration with the Microsoft Agent Framework workflow engine.

Per narration item:  Analyst -> fan-out to one Narrator executor per variant
(persona x language x club view / focus) -> fan-in Verify executor
(deterministic pre-check, Verifier LLM, one repair round through the
Narrator) -> verified overlays. Scout notes feed the focus variants. The
workflow is built once and run per item; items run concurrently.

Failure recovery: every agent call has a timeout and retries (agents/llm.py).
A call that still fails, an unreadable answer or a rejection is isolated to its
own step: the item or variant falls back to the deterministic fact card, the
recovery is recorded in the result (`status`, `recovery`) and the run goes on.
"""

import asyncio
import json
import time

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from . import factcards as FC
from . import verify as V
from .llm import AgentCallFailed


from .facts import slim_state  # noqa: E402  (kept here for compare_agents.py and older imports)


def variants_for(item, cfg):
    """Which (persona, lang, club_view, focus) texts an item needs."""
    mode = item["mode"]
    out = []
    for lang in cfg["languages"]:
        if mode == "fan":
            for club in cfg["club_views"]:
                out.append(dict(persona="fan", lang=lang, club_view=club, focus_player=None))
        elif mode == "analyst":
            out.append(dict(persona="analyst", lang=lang, club_view="neutral", focus_player=None))
        elif mode == "focus":
            out.append(dict(persona="analyst", lang=lang, club_view="neutral", focus_player=item["focus_player"]))
    if item.get("only_variants"):   # a targeted re-run of single variants (run_agents.py --variants)
        out = [v for v in out if variant_key(v) in item["only_variants"]]
    return out


def variant_key(v):
    return f"{v['lang']}|{v['club_view']}|{v['focus_player'] or ''}"


def build_facts(store, item):
    """The facts of one narration item and the Analyst prompt (also used by compare_agents.py)."""
    st = store.state_at_ms(item["t_ms"])
    tc = store.tournament
    period = item["moment"]["period"] if item["kind"] == "moment" else st["period"]
    clock = store.clock_string(item["minute"], period)
    facts = dict(match=dict(teams=[store.team_name(store.home), store.team_name(store.away)],
                            team_ids=[store.home, store.away], venue=tc["venue"], neutral_venue=True,
                            note="Neutral venue: there is no home or away team; never call a team the home side or the visitors."),
                 clock=dict(display=clock, period=period, half="first half" if period == 1 else "second half",
                            rule="Write minutes in football form: first-half stoppage time as 45+N', second-half stoppage time as 90+N'."),
                 tournament=dict(stake=tc["stake"], standings_before_this_match=[dict(rank=r["rank"], team=r["team"], points=r["points"], gd=r["gd"]) for r in tc["standings_before"]]),
                 state=slim_state(st))
    if item["kind"] == "moment":
        m = dict(item["moment"])
        m["team_name"] = store.team_name(m["team_id"]) if m.get("team_id") else None
        m["player_name"] = store.player_name(m["player_id"]) if m.get("player_id") else None
        if m["type"] == "control_chaos_switch":
            # the regime is one value for the whole match; the event that crossed the threshold belongs to some team,
            # but naming it made the agents write "Northbridge switches to control"
            for k in ("team_id", "team_name", "player_id", "player_name"):
                m.pop(k, None)
            m["scope"] = "whole match (both teams together): never attribute the regime or the control index to one team"
        facts["moment"] = m
        if "score_after_goal" in m["fact"]:
            # the state snapshot is taken before the goal; make the post-goal score explicit
            sh, sa = (int(x) for x in m["fact"]["score"].split("-"))
            facts["state"]["score"] = {store.home: sh, store.away: sa}
            facts["state"]["score_note"] = f"score after this goal: {m['fact']['score_after_goal']} ({m['fact']['goal_effect']} for {m['fact']['scoring_team']})"
        recent = [dict(minute=x["minute"], type=x["type"], team=x.get("team_id"), fact=x["fact"]) for x in
                  store.moments_between(item["t_ms"] - 5 * 60000, item["t_ms"] - 1) if x["importance"] >= 0.4][-3:]
        facts["recent_moments"] = recent
        bm = store.moment_ball_metrics(item["moment"])
        if bm:
            facts["moment"]["ball_metrics"] = bm
        add_tags(store, item, facts)
        prompt = f"Write the insight card for this moment.\nFACTS:\n{json.dumps(facts, ensure_ascii=False)}"
    else:
        add_tags(store, item, facts)
        prompt = f"Write a 'state' insight card describing the match state at minute {item['minute']} (score, control vs chaos, momentum, pressing, notable players).\nFACTS:\n{json.dumps(facts, ensure_ascii=False)}"
    return facts, prompt


def add_tags(store, item, facts):
    """Player tags of the last 5 minutes (very difficult completed pass, fast shot, fastest run so far): deterministic facts."""
    tags = store.tags_between(item["t_ms"] - 5 * 60000, item["t_ms"])
    if tags:
        facts["state"]["player_tags_last_5min"] = [dict(player=store.player_name(t["player_id"]), kind=t["kind"], value=t["value"],
                                                        clock=store.clock_string(t["minute"], t["period"])) for t in tags[-3:]]


def scout_facts(store, item, cfg):
    """The facts the Scout gets for a player-focus item (also used by compare_agents.py)."""
    pid = item["focus_player"]
    prof = store.profiles.get(pid, {})
    live = store.player_live(pid, item["t_ms"])
    return dict(player_id=pid, name=store.player_name(pid), age=store.players[pid]["age"], profile=prof, live=live,
                thresholds=dict(low_data_tournament_minutes=cfg["low_data_minutes_tournament"], low_data_live_minutes=cfg["low_data_minutes_live"]),
                **player_identity(store, pid, "en", item))


focus_is_subject = V.focus_is_subject


def item_clock(store, item):
    period = item["moment"]["period"] if item["kind"] == "moment" else store.period_at_ms(item["t_ms"])
    return store.clock_string(item["minute"], period)


def player_identity(store, pid, lang, item=None):
    """Team, position, whether the player plays in this match and, at the item's moment, whether he is on the pitch:
    facts, so that no text has to guess them."""
    plays = V.plays_in_match(pid, store)
    ident = dict(team=store.team_name(store.players[pid]["team_id"]), position=V.position_label(pid, store, lang),
                 position_code=store.players[pid].get("position_detail") or store.players[pid]["primary_position"], in_this_match=plays)
    if not plays:
        ident["note"] = (f"{store.player_name(pid)} does not play in this match ({store.team_name(store.home)} vs {store.team_name(store.away)}): "
                         "say so and describe only his tournament profile; never tie him to this match's clock, score or teams.")
    elif item is not None:
        st = store.pitch_status(pid, item["t_ms"], item_clock(store, item))
        ident["pitch_status"] = st["text"]
        if not st["on_pitch"]:
            ident["note"] = (f"{store.player_name(pid)} is {st['text']}. Say so in the text (e.g. 'on the bench' / 'not on the pitch yet' / "
                             "'substituted at 70''); describe only his tournament profile and what he did before; never write as if he were playing now.")
    return ident


class AnalystExecutor(Executor):
    def __init__(self, rt, store):
        super().__init__(id="analyst")
        self.rt, self.store = rt, store

    @handler
    async def run(self, item: dict, ctx: WorkflowContext[dict]) -> None:
        facts, prompt = build_facts(self.store, item)
        trace = self.rt.trace_id()
        recovery = []
        try:
            card, raw = await self.rt.ask("analyst", prompt, trace=trace, meta=dict(item_id=item["item_id"]), note=recovery)
            if card is None:
                card = deterministic_card(self.store, item, self.rt.cfg)
                recovery.append(dict(agent="analyst", kind="invalid_json", action="deterministic insight card from the facts"))
        except AgentCallFailed as f:
            card = deterministic_card(self.store, item, self.rt.cfg)
            recovery.append(dict(agent="analyst", kind=f.kind, attempts=f.attempts, action="deterministic insight card from the facts"))
        if item["kind"] == "moment" and not card.get("evidence_event_ids"):
            card["evidence_event_ids"] = list(item["moment"]["evidence_event_ids"])
        card.setdefault("evidence_event_ids", [])
        scout = None
        if item["mode"] == "focus":
            try:
                scout = await self.scout_note(item, trace, recovery)
                if scout["note"] is None:
                    recovery.append(dict(agent="scout", kind="invalid_json", action="narrated without the scout note"))
            except AgentCallFailed as f:
                recovery.append(dict(agent="scout", kind=f.kind, attempts=f.attempts, action="narrated without the scout note"))
        await ctx.send_message(dict(item=item, card=card, facts=facts, scout=scout, trace=trace, recovery=recovery))

    async def scout_note(self, item, trace, recovery=None):
        pid = item["focus_player"]
        facts = scout_facts(self.store, item, self.rt.cfg)
        note, _ = await self.rt.ask("scout", f"Write the player-focus note.\nFACTS:\n{json.dumps(facts, ensure_ascii=False)}", trace=trace, meta=dict(item_id=item["item_id"], player_id=pid), note=recovery)
        return dict(note=note, facts=facts)


class NarratorExecutor(Executor):
    def __init__(self, rt, store, variant_index):
        super().__init__(id=f"narrator_{variant_index}")
        self.rt, self.store, self.idx = rt, store, variant_index

    @handler
    async def run(self, msg: dict, ctx: WorkflowContext[dict]) -> None:
        variants = variants_for(msg["item"], self.rt.cfg)
        if self.idx >= len(variants):
            await ctx.send_message(dict(skip=True, idx=self.idx))
            return
        v = variants[self.idx]
        recovery = list(msg.get("recovery", []))
        text = await narrate(self.rt, self.store, msg, v, note=recovery)
        await ctx.send_message(dict(idx=self.idx, variant=v, text=text, item=msg["item"], card=msg["card"], facts=msg["facts"], scout=msg["scout"],
                                    trace=msg["trace"], recovery=recovery))


async def narrate(rt, store, msg, v, feedback=None, note=None, previous=None):
    item = msg["item"]
    payload = dict(persona=v["persona"], language=v["lang"], club_view=(store.team_name(v["club_view"]) if v["club_view"] != "neutral" else "neutral"),
                   focus_player=(store.player_name(v["focus_player"]) if v["focus_player"] else None),
                   clock=msg["facts"]["clock"], match=msg["facts"]["match"], tournament_stake=msg["facts"]["tournament"]["stake"],
                   insight_card=msg["card"], state=msg["facts"]["state"])
    if msg["facts"].get("moment"):
        payload["moment"] = dict(type=msg["facts"]["moment"]["type"], clock=msg["facts"]["moment"]["clock"], half=msg["facts"]["moment"]["half"], fact=msg["facts"]["moment"]["fact"])
    if msg.get("scout"):
        payload["scout_note"] = msg["scout"]["note"]
    if v["focus_player"]:
        prof = store.profiles.get(v["focus_player"], {})
        payload["focus_player_facts"] = dict(player_identity(store, v["focus_player"], v["lang"], item), tournament_minutes=prof.get("minutes"),
                                             reliability=prof.get("reliability"),
                                             rule="Use this position wording. Below the low-data threshold make no ranking or elite claim (no 'top', 'best', 'outstanding').")
    prompt = f"Write the texts.\nINPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    if feedback:
        if previous:
            prev = {k: previous.get(k) for k in ("overlay", "commentary", "detail") if previous.get(k)}
            prompt += f"\nYOUR PREVIOUS TEXT:\n{json.dumps(prev, ensure_ascii=False)}"
        prompt += f"\nREPAIR REQUEST: your previous text had problems: {json.dumps(feedback, ensure_ascii=False)}. Rewrite it without those problems and keep what was correct."
    try:
        out, raw = await rt.ask("narrator", prompt, trace=msg["trace"], meta=dict(item_id=item["item_id"], persona=v["persona"], lang=v["lang"], club_view=v["club_view"], focus_player=v["focus_player"], repair=bool(feedback)), note=note)
    except AgentCallFailed as f:
        return dict(overlay="", commentary="", detail="", _failure=dict(agent="narrator", kind=f.kind, attempts=f.attempts))
    if not out:
        out = dict(overlay="", commentary="", detail="", _invalid_json=True)
    return out


def deterministic_card(store, item, cfg):
    """Insight card built from the facts alone (used when the Analyst fails or answers with invalid JSON)."""
    fc = FC.fact_card(store, item, "en") or dict(text="", data={}, evidence_event_ids=[])
    return dict(type=item["moment"]["type"] if item["kind"] == "moment" else "state", headline_facts=[fc["text"]] if fc["text"] else [],
                why_it_matters="", data=fc["data"], evidence_event_ids=list(fc["evidence_event_ids"]), source_fields=["fact_card"], deterministic=True)


def fallback_record(store, cfg, item, variant, trace, reason, recovery, card=None, facts=None, attempts=None):
    """Result for a variant whose agent text could not be produced or verified: the fact card stays."""
    clock = store.clock_string(item["minute"], item["moment"]["period"] if item["kind"] == "moment" else store.period_at_ms(item["t_ms"]))
    return dict(item_id=item["item_id"], mode=item["mode"], kind=item["kind"], minute=item["minute"], clock=clock,
                period=item["moment"]["period"] if item["kind"] == "moment" else store.period_at_ms(item["t_ms"]), t_ms=item["t_ms"],
                variant=variant, verdict="fallback", status="fallback", reasons=[reason], recovery=recovery, attempts=attempts or [],
                trace=trace, card=card or deterministic_card(store, item, cfg), final=None, facts=facts or {}, claims=[],
                fact_card=FC.checked_fact_card(store, item, variant["lang"], cfg))


class VerifyExecutor(Executor):
    def __init__(self, rt, store, rules, n_variants):
        super().__init__(id="verify")
        self.rt, self.store, self.rules, self.n = rt, store, rules, n_variants
        self.report = []

    @handler
    async def run(self, msgs: list[dict], ctx: WorkflowContext[None, list]) -> None:
        results = []
        for m in msgs:
            if m.get("skip"):
                continue
            try:
                results.append(await self.verify_one(m))
            except Exception as exc:  # isolate an unexpected error to this variant
                results.append(fallback_record(self.store, self.rt.cfg, m["item"], m["variant"], m["trace"], f"unexpected error: {type(exc).__name__}",
                                               list(m.get("recovery", [])) + [dict(agent="verify step", kind="exception", action="fact card stays")],
                                               card=m.get("card"), facts=m.get("facts")))
        await ctx.yield_output(results)

    def precheck(self, text_obj, m):
        v, item = m["variant"], m["item"]
        facts = dict(card=m["card"], state=m["facts"]["state"], moment=m["facts"].get("moment"), scout=(m["scout"] or {}).get("facts"), minute=item["minute"])
        cfg = self.rt.cfg
        text = " ".join(str(text_obj.get(k) or "") for k in ("overlay", "commentary", "detail"))
        ok_n, bad_n = V.check_numbers(text, facts, cfg["number_tolerance_relative"], cfg["number_tolerance_absolute"])
        ok_names, bad_names = V.check_names(text, facts, self.store)
        claims = V.check_claims(text, v["lang"], item, self.store, self.rules, player_id=v["focus_player"])
        unsupported = [c for c in claims if not c["supported"]]
        too_long = len(text_obj.get("overlay") or "") > cfg["overlay_max_chars"]
        core, player, wording = V.semantic_checks(text, text_obj, v["lang"], item, self.store, cfg, m["facts"]["state"], m["facts"].get("moment"), v["focus_player"])
        semantic = core + player + wording
        if not (text_obj.get("overlay") or "").strip():
            semantic = list(semantic) + ["empty overlay text"]
        return dict(numbers_ok=ok_n, bad_numbers=bad_n, names_ok=ok_names, bad_names=bad_names, claims=claims,
                    unsupported_claims=unsupported, overlay_too_long=too_long, semantic=semantic,
                    passed=ok_n and ok_names and not unsupported and not too_long and not semantic), facts

    async def verify_one(self, m):
        v, item = m["variant"], m["item"]
        recovery = list(m.get("recovery", []))
        text = m["text"]
        if text.get("_failure"):
            f = text["_failure"]
            return fallback_record(self.store, self.rt.cfg, item, v, m["trace"], f"narrator unavailable: {f['kind']}",
                                   recovery + [dict(f, action="fact card stays")], card=m["card"], facts=m["facts"])
        text, trims = V.trim_stock_phrases(text, v["lang"])
        if trims:
            recovery.append(dict(agent="pre-check", kind="stock_phrase_trimmed", action=f"removed: {', '.join(trims)}"))
        pre, facts = self.precheck(text, m)
        attempts = [dict(stage="narrator", precheck=pre, text=text)]
        if text.get("_invalid_json"):
            recovery.append(dict(agent="narrator", kind="invalid_json", action="treated as a failed pre-check; one repair round"))
        if not pre["passed"]:
            feedback = dict(wrong_numbers=pre["bad_numbers"], unknown_names=pre["bad_names"],
                            unsupported_claims=[dict(claim=c["matched"], rule=c["rule"], facts=c["evidence"]) for c in pre["unsupported_claims"]],
                            overlay_too_long=pre["overlay_too_long"], semantic_problems=pre["semantic"])
            text = await narrate(self.rt, self.store, m, v, feedback=feedback, note=recovery, previous=text)
            if text.get("_failure"):
                f = text["_failure"]
                return fallback_record(self.store, self.rt.cfg, item, v, m["trace"], f"narrator repair unavailable: {f['kind']}",
                                       recovery + [dict(f, action="fact card stays")], card=m["card"], facts=facts, attempts=attempts)
            if text.get("_invalid_json"):
                recovery.append(dict(agent="narrator", kind="invalid_json", action="repair answer unreadable"))
            text, trims = V.trim_stock_phrases(text, v["lang"])
            if trims:
                recovery.append(dict(agent="pre-check", kind="stock_phrase_trimmed", action=f"removed: {', '.join(trims)}"))
            pre, facts = self.precheck(text, m)
            attempts.append(dict(stage="narrator_repair", precheck=pre, text=text))
        verdict, verified_text, reasons = "reject", None, ["pre-check failed after repair"]
        if pre["passed"]:
            vin = dict(language=v["lang"], persona=v["persona"], text=text, facts=facts, precheck=dict(claims=pre["claims"]))
            try:
                out, raw = await self.rt.ask("verifier", f"Verify this text.\nINPUT:\n{json.dumps(vin, ensure_ascii=False)}", trace=m["trace"],
                                             meta=dict(item_id=item["item_id"], persona=v["persona"], lang=v["lang"], club_view=v["club_view"], focus_player=v["focus_player"]), note=recovery)
            except AgentCallFailed as f:
                return fallback_record(self.store, self.rt.cfg, item, v, m["trace"], f"verifier unavailable: {f.kind}",
                                       recovery + [dict(f.as_dict(), action="fact card stays")], card=m["card"], facts=facts, attempts=attempts)
            if out and out.get("verdict") in ("ok", "repaired"):
                cand = dict(overlay=out.get("overlay") or text.get("overlay"), commentary=out.get("commentary") or text.get("commentary"), detail=out.get("detail") or text.get("detail"))
                cand, _ = V.trim_stock_phrases(cand, v["lang"])
                pre2, _ = self.precheck(cand, m)
                join = lambda t: " ".join(str(t.get(k) or "") for k in ("overlay", "commentary", "detail"))
                added = V.check_name_changes(join(text), join(cand), self.store)
                if v["focus_player"] and not V.check_focus_subject(join(text), v["focus_player"], self.store, "en") and V.check_focus_subject(join(cand), v["focus_player"], self.store, "en"):
                    added = added + [f"removed {self.store.player_name(v['focus_player'])}"]
                if added:
                    # the Verifier may soften or remove, but never add or swap a player name
                    verdict, verified_text, reasons = "ok", text, [f"verifier repair changed player names ({', '.join(added)}); kept the pre-checked narrator text"]
                    recovery.append(dict(agent="verifier", kind="name_change_blocked", action="kept the pre-checked narrator text"))
                elif pre2["passed"]:
                    verdict, verified_text, reasons = out["verdict"], cand, out.get("reasons", [])
                else:
                    verdict, verified_text, reasons = "ok", text, ["verifier repair re-failed the pre-check; kept the pre-checked narrator text"]
            elif out:
                verdict, reasons = "reject", out.get("reasons", ["rejected by verifier"])
            else:
                verdict, verified_text, reasons = "ok", text, ["verifier output unparsable; kept the pre-checked narrator text"]
                recovery.append(dict(agent="verifier", kind="invalid_json", action="kept the text that passed the deterministic pre-check"))
        if verdict == "reject":
            recovery.append(dict(agent="verifier" if pre["passed"] else "pre-check", kind="rejected", action="fact card stays"))
        status = "fallback" if verdict == "reject" else ("recovered" if recovery else "verified")
        rec = dict(item_id=item["item_id"], mode=item["mode"], kind=item["kind"], minute=item["minute"], clock=m["facts"]["clock"]["display"],
                   period=m["facts"]["clock"]["period"], t_ms=item["t_ms"], variant=v, verdict=verdict, status=status, recovery=recovery,
                   reasons=reasons, attempts=attempts, trace=m["trace"], card=m["card"], final=verified_text, facts=facts,
                   claims=[c for a in attempts for c in a["precheck"]["claims"]], fact_card=FC.checked_fact_card(self.store, item, v["lang"], self.rt.cfg))
        self.report.append(rec)
        return rec


def build_workflow(rt, store, rules, n_variants):
    analyst = AnalystExecutor(rt, store)
    narrators = [NarratorExecutor(rt, store, i) for i in range(n_variants)]
    verify = VerifyExecutor(rt, store, rules, n_variants)
    wf = (WorkflowBuilder(start_executor=analyst)
          .add_fan_out_edges(analyst, narrators)
          .add_fan_in_edges(narrators, verify)
          .build())
    return wf, verify


async def run_items(rt, store, rules, items, cfg, progress=None):
    results = []

    async def one(it):
        t0 = time.time()
        try:
            # one workflow instance per item (the engine does not allow concurrent runs on one instance)
            # at least two narrator branches: the workflow's fan-out / fan-in needs two edges (a single-variant re-run skips the spare one)
            wf, _ = build_workflow(rt, store, rules, max(2, len(variants_for(it, cfg))))
            r = await wf.run(it)
            outs = r.get_outputs()
            recs = outs[0] if outs else []
            if not recs:
                raise RuntimeError("workflow produced no result")
        except Exception as exc:  # isolate a failing item: its variants fall back to the fact card, the run continues
            rec_kind = exc.kind if isinstance(exc, AgentCallFailed) else "exception"
            recs = [fallback_record(store, cfg, it, v, None, f"item failed: {type(exc).__name__}",
                                    [dict(agent="workflow", kind=rec_kind, detail=str(exc)[:160], action="fact card stays")]) for v in variants_for(it, cfg)]
        for rec in recs:
            rec["item_latency_s"] = round(time.time() - t0, 2)
        results.extend(recs)
        if progress:
            progress(it, recs)
    await asyncio.gather(*(one(it) for it in items))
    results.sort(key=lambda r: (r["t_ms"], r["mode"], r["variant"]["persona"], r["variant"]["lang"], r["variant"]["club_view"], str(r["variant"]["focus_player"])))
    return results, None
