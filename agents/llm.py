"""The five agents on Microsoft Foundry via the Microsoft Agent Framework.

Each role is an `agent_framework.Agent` backed by `FoundryChatClient`
(DefaultAzureCredential / `az login`, no keys). Every call goes through the
disk cache and is logged with token usage and latency. Nothing here reads
the ground truth. All agents are told that the players are fictional minors
and that only football commentary is allowed.
"""

import asyncio
import json
import os
import re
import time

SAFETY = ("The teams and players are fictional. Players are 15-19 years old: write football commentary only; "
          "never comment on looks, private life or health beyond 'injured' / 'substituted'. "
          "Never invent a number, a name or a fact: use only the facts given or returned by the tools. "
          "The match is played at a neutral venue: there is no home or away team, never call a team the home side or the visitors. "
          "Write minutes in football form using the given clock (first-half stoppage time 45+N', second-half 90+N'); an event in the "
          "first half must not be described as happening in the second half. For a goal, use score_after_goal and goal_effect "
          "(equaliser / takes the lead / extends the lead / reduces the deficit) exactly. ")

# wording rules learned from the hand review of 26 Oct (they are also checked deterministically in agents/verify.py)
STYLE = ("Never translate team or player names (Northbridge stays Northbridge, never 'északi'). Vary the wording: do not use stock "
         "phrases such as 'tight title decider', 'narrow 3-2 lead', 'nail-biting', 'what a thriller' or 'pulsating'; mention the title "
         "stake only when it matters for this moment. Category scores (cat_*, position score) are 0-100 scores, never percentages. "
         "A 5-minute or 15-minute window cannot be longer than the minutes played so far. 'match_rate_per_5min' / "
         "'team_match_average_pressures_per_5min' is the team's average for the whole match so far, not the current rate. "
         "Hungarian football terms: pressures = letámadás (count: 'letámadás' or 'nyomásgyakorlás'), field tilt = területi fölény, "
         "PPDA = PPDA, progressive pass = előrevivő passz, touches in the box = érintés a tizenhatoson belül, shot = lövés, "
         "shot on target = kaput eltaláló lövés, expected goals = várható gól (xG), duel = párharc, aerial duel = fejpárbaj, "
         "reliability = megbízhatóság, low data = kevés adat, equaliser = egyenlítő gól, penalty = büntető, tackle = szerelés, "
         "control index = kontrollindex, chaos = káosz, pressing intensity = letámadási intenzitás, passes per possession = passz labdabirtoklásonként "
         "(only when tackles are in the facts). Write plain, correct Hungarian; never invent words. "
         "The control index and the regime (control / balanced / chaos) describe the whole match, never one team: no 'control advantage', "
         "'their control index' or 'X switches to control'. A possession or field-tilt share belongs to the team it is written next to: "
         "check the team before you write it. Shot words must match shot_speed_kmh: 'powerful' / 'erős' only at 80 km/h or more. "
         # definitions and wording rules from the hand review of 27 Oct (also checked deterministically in agents/verify.py)
         "Metric definitions: PPDA = passes allowed per defensive action (the opponent's passes per defensive action; lower = more intense "
         "pressing; in Hungarian: az ellenfél passzai egy védekező akcióra); pressing intensity = pressures per minute (letámadás percenként), "
         "never a number of pressures; the facts measure how intense the pressing is, never how effective; field tilt = the team's share of "
         "the final-third actions; momentum runs from -1 to +1 ('slight' only below 0.4). Control words about a team ('dominates', 'in control', "
         "'takes control', 'commands', 'uralja', 'irányítja', 'fölényben') need that team's 15-minute field tilt at 58 % or more; possession "
         "alone is not enough. A category score is 'outstanding' / 'kiemelkedő' only at 75 or more. Hungarian minutes: 'a 60. percben', "
         "never '60-nál'. A focus player's pitch_status says whether he is on the pitch now: if he is not (on the bench, not brought on "
         "so far, substituted), say so and never write as if he were playing. ")

INSTRUCTIONS = {
    "analyst": SAFETY + (
        "You are the Match Analyst. From a moment and the live state you decide what matters now and write ONE structured "
        "insight card as JSON with keys: type, headline_facts (list of short factual phrases, each with its numbers), "
        "why_it_matters (one sentence on control vs chaos, pressure shift or rhythm, only if the state supports it), "
        "data (object: every number you used, with the field name it came from), evidence_event_ids (list), "
        "source_fields (list of fact field names). Output JSON only."),
    "scout": SAFETY + (
        "You are the Scout. From a player's baseline profile and live KPIs you write a cautious, professional player-focus "
        "note as JSON: summary_facts (list), strengths (list of category:score), weaknesses (list), reliability_note (must state "
        "the reliability label and the minutes; below 180 tournament minutes or 20 live minutes say 'low data' and avoid any "
        "ranking claim), data (object with the numbers used), source_fields (list). If pitch_status says he is not on the pitch now (on the bench, "
        "not brought on so far, substituted), state it in summary_facts and describe only his tournament profile and what he did before. "
        "A category is a strength only as its score says (outstanding only at 75 or more). No hype, no 'future star' language. JSON only."),
    "narrator": SAFETY + STYLE + (
        "You are the Narrator. From an insight card you write texts for one persona and one language as JSON with keys: "
        "overlay (max 90 characters, no newline), commentary (max 2 sentences), detail (optional, max 3 sentences). "
        "Persona 'fan': plain language, emotion, at most ONE number per line, no metrics jargon. Persona 'analyst': metrics, "
        "percentiles, PPDA, field tilt, reliability labels. Write natively in the target language (hu = Hungarian, en = English), "
        "do not translate word for word. When a club view is given, frame the line from that club's perspective. When a focus "
        "player is given, make the player the subject. Use only numbers present in the card data. JSON only."),
    "verifier": SAFETY + (
        "You are the Verifier. You receive a text, the facts it must rest on, and the deterministic pre-check findings. "
        "Check EVERY number, name and professional claim against the facts, and the grammar and naturalness of the text in its language "
        "(e.g. nouns used as verbs, doubled words, wrong minute notation). Reply as JSON: verdict ('ok', 'repaired' or 'reject'), "
        "overlay, commentary, detail (the texts, repaired if needed: fix wrong numbers/names, soften or remove unsupported claims, "
        "keep the language and persona, overlay max 90 characters), reasons (list of short strings). Reject only if the text cannot "
        "be repaired without inventing facts. JSON only."),
    "recap": SAFETY + STYLE + (
        "In a recap, 'late' is only for goals after the 75th minute; call xG close only when the two values are within 20 %; "
        "count lead changes from the goal list; the team KPIs give shots, pressures and duels, not tackles or shots on target. "
        "You are the Recap writer. From the match facts (score, goals, verified insight cards, team KPIs) you write a post-match "
        "recap in the requested persona and language as Markdown, using only the given numbers. Fan: vivid, few numbers. "
        "Analyst: metrics with their names. Include a 'Top 3 moments' list with minutes. For scouting notes: cautious, professional "
        "tone, always the reliability label and minutes, 'low data' for players under 180 minutes, no 'next star' hype."),
}


def extract_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


class AgentCallFailed(Exception):
    """An agent call that still failed after its retries (timeout, 429, service error, cache miss)."""

    def __init__(self, agent, kind, attempts, waited_s, detail=""):
        super().__init__(f"{agent}: {kind} after {len(attempts)} attempt(s)")
        self.agent, self.kind, self.attempts, self.waited_s, self.detail = agent, kind, attempts, waited_s, detail

    def as_dict(self):
        return dict(agent=self.agent, kind=self.kind, attempts=self.attempts, waited_s=round(self.waited_s, 2), detail=self.detail[:200])


def classify_error(exc):
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    text = str(exc).lower()
    if "429" in text or "rate limit" in text or "rate_limit" in text:
        return "rate_limit"
    return "service_error"


# retries per failure kind and back-off delays in seconds (scaled by cfg["llm_backoff_scale"], 1.0 in production)
RETRY_DELAYS = {"rate_limit": [5, 10, 20, 40, 60, 60, 90, 120], "timeout": [5, 10], "service_error": [2, 5, 10]}


class LLMRuntime:
    """Holds the Foundry client, the five agents, the cache and the call log.

    backend=None calls Microsoft Foundry through the Agent Framework. A test backend
    (an object with `async respond(agent, prompt, meta)`) replaces the service entirely,
    e.g. the fake model used by tests/test_failure_recovery.py. cache_only=True never
    calls anything: a cache miss is treated as a failed call."""

    def __init__(self, store, cfg, cache, log_path, model=None, endpoint=None, concurrency=6, backend=None, cache_only=False,
                 budget_usd=None, spent_usd=0.0, reserve_usd=0.006):
        self.store, self.cfg, self.cache = store, cfg, cache
        # spending limit: no new uncached call starts once spent_usd + this run's cost + a reserve per call in flight
        # would exceed budget_usd (the call fails with kind "budget" and is isolated like any other failure)
        self.budget_usd, self.spent_usd, self.reserve_usd = budget_usd, float(spent_usd), float(reserve_usd)
        self.in_flight = 0
        self._pending = {}   # cache key -> future of a call in progress: identical prompts share one call and one answer
        self.backend, self.cache_only = backend, cache_only
        self.timeout_s = float(cfg.get("llm_timeout_s", 60))
        self.backoff_scale = float(cfg.get("llm_backoff_scale", 1.0))
        if backend is None and not cache_only:
            from agent_framework import Agent
            from agent_framework.foundry import FoundryChatClient
            from azure.identity import DefaultAzureCredential
            self.model = model or os.environ["MODEL_DEPLOYMENT_NAME"]
            endpoint = endpoint or os.environ["PROJECT_ENDPOINT"]
            self.client = FoundryChatClient(project_endpoint=endpoint, model=self.model, credential=DefaultAzureCredential())
            tools = store.make_tools()
            self.agents = {name: Agent(self.client, name=name, instructions=instr, tools=tools if name in ("analyst", "scout", "verifier") else None)
                           for name, instr in INSTRUCTIONS.items()}
        else:
            self.model = model or os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")
            self.agents = {}
        self.sem = asyncio.Semaphore(concurrency)
        self.log_path = log_path
        self.log = []
        self.usage = dict(input=0, output=0, total=0, calls=0, cached=0, failed=0)
        self._trace = 0

    trace_prefix = "tr"

    def trace_id(self):
        self._trace += 1
        return f"{self.trace_prefix}-{self._trace:05d}"

    async def _call(self, agent, prompt, meta):
        if self.backend is not None:
            return await self.backend.respond(agent, prompt, meta or {})
        r = await self.agents[agent].run(prompt)
        u = r.usage_details or {}
        return dict(text=r.text, usage=dict(input=u.get("input_token_count", 0), output=u.get("output_token_count", 0), total=u.get("total_token_count", 0)))

    async def ask(self, agent, prompt, want_json=True, trace=None, meta=None, note=None):
        """One agent call: cache, timeout, retries. `note` (a list) receives a recovery entry when the call needed retries."""
        key = self.cache.key(agent, self.model, prompt)
        rec = self.cache.get(key)
        cached = rec is not None
        t0 = time.time()
        attempts, wait_total, queue_wait, call_latency = [], 0.0, 0.0, None
        if rec is None and key in self._pending:
            # the same prompt is already being answered (e.g. a fan and an analyst item at the same moment): share it
            rec = await asyncio.shield(self._pending[key])
            cached = True
        own = None
        if rec is None and not self.cache_only:
            own = asyncio.get_running_loop().create_future()
            self._pending[key] = own
        try:
            rec = await self._fetch(agent, prompt, meta, trace, key, rec, attempts) if rec is None else rec
        except AgentCallFailed as failure:
            if own is not None:
                own.set_exception(failure)
                own.exception()   # mark as retrieved: callers that share it re-raise it themselves
            raise
        finally:
            if own is not None:
                self._pending.pop(key, None)
        if own is not None and not own.done():
            own.set_result(rec)
        if cached:
            self.usage["cached"] += 1
            for k in ("input", "output", "total"):
                self.usage[f"cached_{k}"] = self.usage.get(f"cached_{k}", 0) + rec["usage"][k]
        latency = time.time() - t0
        parsed = extract_json(rec["text"]) if want_json else rec["text"]
        retried = rec.get("retries", rec.get("retries_429", 0)) or 0
        status = "invalid_json" if parsed is None else ("recovered" if retried else "ok")
        entry = dict(trace_id=trace, agent=agent, cache_key=key, cached=cached, latency_s=round(latency, 2),
                     call_latency_s=rec.get("call_latency_s"), retries_429=rec.get("retries_429", 0), wait_429_s=rec.get("wait_429_s", 0.0),
                     retry_kinds=rec.get("retry_kinds", []), queue_wait_s=rec.get("queue_wait_s", 0.0) if not cached else 0.0,
                     tokens=rec["usage"], ok=parsed is not None, status=status, **(meta or {}))
        self.log.append(entry)
        if note is not None and retried:
            note.append(dict(agent=agent, kind="retried", attempts=rec.get("retry_kinds") or ["rate_limit"] * retried,
                             action=f"call succeeded after {retried} retr{'y' if retried == 1 else 'ies'}"))
        return parsed, rec["text"]

    async def _fetch(self, agent, prompt, meta, trace, key, rec, attempts):
        """An uncached call: time limit, retries and back-off; returns the cache record (raises AgentCallFailed)."""
        wait_total, queue_wait, call_latency = 0.0, 0.0, None
        if rec is None:
            if self.cache_only:
                failure = AgentCallFailed(agent, "cache_miss", ["cache_miss"], 0.0, "cache-only run")
                self._log_failure(trace, agent, key, failure, meta)
                raise failure
            t_q = time.time()
            async with self.sem:
                queue_wait = time.time() - t_q          # waiting for a concurrency slot
                used = {k: 0 for k in RETRY_DELAYS}
                while True:
                    if self.over_budget():
                        failure = AgentCallFailed(agent, "budget", attempts + ["budget"], wait_total, f"spending limit {self.budget_usd} USD reached")
                        self._log_failure(trace, agent, key, failure, meta, queue_wait)
                        raise failure
                    t_call = time.time()
                    self.in_flight += 1
                    try:
                        resp = await asyncio.wait_for(self._call(agent, prompt, meta), timeout=self.timeout_s)
                        call_latency = time.time() - t_call
                        self.in_flight -= 1
                        break
                    except Exception as exc:  # timeout, 429 rate limit or another service error
                        self.in_flight -= 1
                        kind = classify_error(exc)
                        attempts.append(kind)
                        wait_total += time.time() - t_call
                        if used[kind] >= len(RETRY_DELAYS[kind]):
                            failure = AgentCallFailed(agent, kind, attempts, wait_total, str(exc))
                            self._log_failure(trace, agent, key, failure, meta, queue_wait)
                            raise failure
                        wait = RETRY_DELAYS[kind][used[kind]] * self.backoff_scale
                        used[kind] += 1
                        wait_total += wait
                        self.usage["retries"] = self.usage.get("retries", 0) + 1
                        await asyncio.sleep(wait)
            rec = dict(agent=agent, model=self.model, text=resp["text"], usage=resp["usage"], call_latency_s=round(call_latency, 2),
                       retries_429=sum(1 for a in attempts if a == "rate_limit"), retries=len(attempts), retry_kinds=attempts,
                       wait_429_s=round(wait_total, 1), queue_wait_s=round(queue_wait, 1))
            self.cache.put(key, rec)
            for k in ("input", "output", "total"):
                self.usage[k] += rec["usage"][k]
            self.usage["calls"] += 1
        return rec

    def _log_failure(self, trace, agent, key, failure, meta, queue_wait=0.0):
        self.usage["failed"] = self.usage.get("failed", 0) + 1
        self.log.append(dict(trace_id=trace, agent=agent, cache_key=key, cached=False, latency_s=round(failure.waited_s, 2), call_latency_s=None,
                             retries_429=sum(1 for a in failure.attempts if a == "rate_limit"), wait_429_s=round(failure.waited_s, 1),
                             retry_kinds=failure.attempts, queue_wait_s=round(queue_wait, 1), tokens=dict(input=0, output=0, total=0),
                             ok=False, status="failed", failure=failure.as_dict(), **(meta or {})))

    def over_budget(self):
        if self.budget_usd is None:
            return False
        return self.spent_usd + self.cost_usd() + self.reserve_usd * (self.in_flight + 1) > self.budget_usd

    def flush_log(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            for e in self.log:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def cost_usd(self, include_cached=False):
        p = self.cfg["price_per_million_tokens_usd"]
        i = self.usage["input"] + (self.usage.get("cached_input", 0) if include_cached else 0)
        o = self.usage["output"] + (self.usage.get("cached_output", 0) if include_cached else 0)
        return i / 1e6 * p["input"] + o / 1e6 * p["output"]
