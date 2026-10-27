"""Deterministic verification of narrator outputs: numbers, names and professional claims.

Runs before the Verifier LLM. Every finding is logged; unsupported claims are
sent back to the Narrator once with the reason (repair), otherwise the item is
dropped. Rules live in config/claim_rules.json.
"""

import json
import re

# sentences end at . ! ? (and ; for short texts), but not after an ordinal number: "a 27. percben" is one sentence
SENT_RE = re.compile(r"(?<=[.!?])(?<!\d\.)\s+|\n")
CLAUSE_END_RE = re.compile(r"(?<=[.!?;])(?<!\d\.)\s+|\n")
# a number, with an optional minus sign; never the tail of another number ("-0,027" is 0.027, not 27)
NUMBER_RE = re.compile(r"(?<![\w.,])-?(\d+(?:[.,]\d+)?)\s*(%|km/h|m\b)?")


def load_rules(path="config/claim_rules.json"):
    with open(path) as f:
        return json.load(f)


def _flatten_numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten_numbers(v, out)
    elif isinstance(obj, str):
        for m in NUMBER_RE.finditer(obj):
            try:
                out.append(float(m.group(1).replace(",", ".")))
            except ValueError:
                pass


def allowed_numbers(facts):
    """All numbers that appear in the facts given to the narrator (plus derived score strings)."""
    nums = []
    _flatten_numbers(facts, nums)
    extra = set()
    for n in nums + [abs(x) for x in nums]:
        extra.add(round(n, 3))
        extra.add(round(n * 100, 3))      # shares given as 0.54 may be written as 54 %
        extra.add(round(n, 0))
        extra.add(round(n, 1))
    return extra


# words that contain a digit but are not numbers: the penalty box ("16-os", "tizenhatos"), the six-yard / 18-yard box
NOT_A_NUMBER_RE = re.compile(r"\b16-os\w*|\b(?:6|18)-yard\b|\bsix-yard\b", re.I)


def check_numbers(text, facts, rel_tol, abs_tol):
    """Return (ok, unsupported_numbers). Minute references like 18' are accepted when the item minute matches."""
    allowed = allowed_numbers(facts)
    bad = []
    text = NOT_A_NUMBER_RE.sub(" box ", text)
    for m in NUMBER_RE.finditer(text):
        raw = m.group(1).replace(",", ".")
        try:
            v = float(raw)
        except ValueError:
            continue
        if any(abs(v - a) <= max(abs_tol, rel_tol * abs(a)) for a in allowed):
            continue
        # score strings "2-1": both digits must be allowed; handled above individually
        bad.append(raw)
    return (not bad), bad


def check_names(text, facts, store):
    """Every player name mentioned must be one of the fact players (fictional roster) and the team names must match."""
    bad = []
    mentioned = [p["name"] for p in store.players.values() if p["name"] in text]
    allowed = set()
    _collect_names(facts, allowed)
    for name in mentioned:
        if name not in allowed and not any(part in allowed for part in name.split()):
            bad.append(name)
    return (not bad), bad


def _collect_names(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k in ("player", "scorer", "assist_by", "off", "on", "name", "home_team", "away_team", "team", "now_with_name", "shooter"):
                out.add(v)
            else:
                _collect_names(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_names(v, out)
    elif isinstance(obj, str):
        out.add(obj)


# --------------------------------------------------------------- claims
def _team_in_text(text, store):
    found = []
    for tid, t in store.teams.items():
        short = t["team_name"].replace(" U19", "")
        if short.lower() in text.lower() or t["city"].lower() in text.lower() or tid.lower() in text.lower():
            found.append(tid)
    return found


def _fact_value(window_or_state, team, path):
    kind, key, op, val = path
    if kind == "15min" or kind == "5min":
        return window_or_state["teams"][team][kind].get(key)
    if kind == "momentum":
        return window_or_state["teams"][team]["momentum"]
    if kind == "regime":
        return window_or_state["regime"]
    if kind == "control_index":
        return window_or_state["control_index"]
    return None


def _cmp(v, op, target):
    if v is None:
        return False
    if op == ">=":
        return v >= target
    if op == "<=":
        return v <= target
    if op == ">":
        return v > target
    if op == "<":
        return v < target
    if op == "==":
        return v == target
    return False


def check_claims(text, lang, item, store, rules, player_id=None):
    """Return a list of findings: dict(rule, matched, supported, evidence)."""
    findings = []
    state = store.state_at_ms(item["t_ms"])
    # only the two teams of this match have a state window (another team may be named, e.g. an absent player's club)
    teams_in_text = [t for t in _team_in_text(text, store) if t in (store.home, store.away)] or [store.home, store.away]
    # phrases that only look like a claim: the title race being open, the balance "between control and chaos"
    low = re.sub(r"title race (?:\w+ ){0,2}wide open|race for the title (?:\w+ ){0,2}wide open|(?:between )?control and chaos|"
                 r"káosz és (?:a |az )?(?:kontroll|irányítás) között|(?:kontroll|irányítás) és (?:a )?káosz között|nyitott (?:marad )?a bajnoki (?:verseny|cím)", " ", text.lower())
    for rule in rules["rules"]:
        pats = rule["patterns"].get(lang, [])
        # phrases that contain a pattern word but are no claim of this rule (e.g. the metric names "control index", "területi fölény")
        rlow = low
        for x in rule.get("exclude", {}).get(lang, []):
            rlow = re.sub(x, lambda m: " " * len(m.group(0)), rlow)
        # a pattern must start at a word boundary ("settled" must not match "unsettled"); "re:" patterns are regular expressions
        rx = [re.compile(p[3:]) if p.startswith("re:") else re.compile(r"(?<![a-záéíóöőúüű])" + re.escape(p.lower())) for p in pats]
        hits = [m for r_ in rx for m in r_.finditer(rlow)]
        if not hits:
            continue
        hit = min(hits, key=lambda m: m.start()).group(0).strip()
        req = rule["requires"]
        supported, evidence = False, None
        if rule.get("team_claim"):
            # the claim belongs to the team it is written about: the team (or a player's team) named last before it in the
            # same sentence, else the first one after it; every match must be backed
            unbacked = None
            for m in sorted(hits, key=lambda m: m.start()):
                team = _claimed_team(rlow, m.start(), m.end(), store)
                ok, ev = _team_condition(state, team, req["any"])
                if not ok:
                    unbacked = (m.group(0).strip(), ev)
                    break
            supported = unbacked is None
            hit, evidence = (unbacked if unbacked else (hit, ev))
            findings.append(dict(rule=rule["id"], matched=hit, supported=supported, evidence=evidence))
            continue
        if "player" in req:
            pid = player_id or _player_in_text(text, store)
            prof = store.profiles.get(pid) if pid else None
            if prof:
                mins = float(prof["minutes"])
                cats = [float(prof[k]) for k in prof if k.startswith("cat_")]
                strong = max([float(prof["position_score"])] + cats) >= req["player"][0][2]
                if mins >= req["player"][1][2] and strong:
                    supported, evidence = True, dict(player_id=pid, minutes=mins, position_score=prof["position_score"])
                elif any(w in low for w in rule.get("low_data_wording", {}).get(lang, [])):
                    supported, evidence = True, dict(player_id=pid, minutes=mins, note="low-data wording present")
                else:
                    evidence = dict(player_id=pid, minutes=mins, position_score=prof["position_score"], best_category_pct=max(cats) if cats else None)
            else:
                evidence = dict(player_id=pid, note="no profile")
        else:
            for cond in req["any"]:
                if cond[0] == "moment":
                    look = cond[3] * 60000
                    ms = store.moments_between(item["t_ms"] - look, item["t_ms"] + 1000, cond[1])
                    if len(cond) > 4:   # a regime switch supports a mention of the regime it left or entered ("from chaos to control")
                        ms = [x for x in ms if cond[4] in (x["fact"].get("from_regime"), x["fact"].get("to_regime"))]
                    if ms:
                        supported, evidence = True, dict(moment=ms[-1]["moment_id"], type=cond[1])
                        break
                else:
                    for team in teams_in_text:
                        v = _fact_value(state, team, cond)
                        if _cmp(v, cond[2], cond[3]):
                            supported, evidence = True, dict(team=team, fact=cond[0] if cond[1] is None else f"{cond[0]}.{cond[1]}", value=v)
                            break
                    if supported:
                        break
            if not supported:
                evidence = dict(minute=state["minute"], regime=state["regime"], control_index=state["control_index"],
                                teams={t: dict(tilt=state["teams"][t]["15min"]["field_tilt_pct"], possession=state["teams"][t]["15min"]["possession_pct"],
                                               ppda=state["teams"][t]["15min"]["ppda"], momentum=state["teams"][t]["momentum"]) for t in teams_in_text})
        findings.append(dict(rule=rule["id"], matched=hit, supported=supported, evidence=evidence))
    return findings


def _claimed_team(low, start, end, store):
    """The team a claim at low[start:end] is about: the match team (city, or a player of that team) named last before it in the
    same sentence, else the first one named after it in that sentence; None if the sentence names neither team."""
    a = max(low.rfind(c, 0, start) for c in ".!?;\n") + 1
    b = min([i for i in (low.find(c, end) for c in ".!?;\n") if i >= 0] or [len(low)])
    marks = []
    for tid in (store.home, store.away):
        for key in {store.teams[tid]["city"].lower(), store.teams[tid]["team_name"].replace(" U19", "").lower()}:
            marks += [(m.start(), tid) for m in re.finditer(re.escape(key), low[a:b])]
    by_sur = {}
    for p in store.players.values():
        if p["team_id"] in (store.home, store.away):
            by_sur.setdefault(_surname(p["name"]).lower(), set()).add(p["team_id"])
    for sur, tids in by_sur.items():
        if len(tids) == 1 and sur not in {w.lower() for w in WORD_SURNAMES}:
            marks += [(m.start(), next(iter(tids))) for m in re.finditer(r"(?<![\w])" + re.escape(sur) + r"(?![a-z])", low[a:b])]
    before = [t for p, t in sorted(marks) if a + p < start]
    after = [t for p, t in sorted(marks) if a + p >= end]
    if before:
        return before[-1]
    if a > 0:   # "ők irányítják" / "they take control": the team named last in the sentences before
        prev = _claimed_team(low[:a - 1], a - 1, a - 1, store) if a > 1 else None
        if prev:
            return prev
    return after[0] if after else None


def _team_condition(state, team, conds):
    """(supported, evidence) of a team claim: one of the conditions holds for that team (or, if no team is named, for either team)."""
    for tid in ([team] if team else list(state["teams"])):
        for cond in conds:
            v = _fact_value(state, tid, cond)
            if _cmp(v, cond[2], cond[3]):
                return True, dict(team=tid, fact=f"{cond[0]}.{cond[1]}" if cond[1] else cond[0], value=v)
    tids = [team] if team else list(state["teams"])
    return False, dict(minute=state["minute"], claimed_team=team, regime=state["regime"], control_index=state["control_index"],
                       teams={t: dict(tilt_15min=state["teams"][t]["15min"]["field_tilt_pct"], tilt_5min=state["teams"][t]["5min"]["field_tilt_pct"],
                                      possession_15min=state["teams"][t]["15min"]["possession_pct"]) for t in tids})


def _player_in_text(text, store):
    for pid, p in store.players.items():
        if p["name"] in text or p["name"].split()[-1] in text.split():
            return pid
    return None


# --------------------------------------------------------------- semantics
EQUALISER_WORDS = {"en": ["equalis", "equaliz", "level", "ties the", "tie the", "tied", "all square", "draws level"],
                   "hu": ["egyenlít", "kiegyenlít", "döntetlen"]}
# "kiegyenlített" as an adjective ("balanced"): masked before the goal-direction check
BALANCED_HU = re.compile(r"(?:nagyon|teljesen|szinte|rendkívül|meglehetősen|eléggé|elég|igen|továbbra is|egyre|viszonylag|kissé|is|egy)\s+kiegyenlített\w*"
                         r"|kiegyenlített\w*(?=\s+(?:a\s+|az\s+)?(?:játék|meccs|mérkőzés|küzdelem|csata|döntő|erőviszony|játékerő|labdabirtoklás|találkozó|"
                         r"helyzet|párharc|állapot|játékkép|félidő|iram|tempó|mezőny|címmeccs|rangadó|összecsapás|irányítás|kontroll))"
                         r"|(?:játék|meccs|mérkőzés|küzdelem|labdabirtoklás|irányítás|kontroll|erőviszony\w*|állás|fölény\w*|birtoklás\w*|statisztik\w*|iram|tempó|mutató\w*|adat\w*|párharc\w*|csata|nyomásgyakorlás\w*|letámadás\w*|nyomás\w*)\s+(?:\w+\s+)?kiegyenlített\w*")
LEAD_WORDS = {"en": ["takes the lead", "take the lead", "lead", "leads", "ahead", "in front", "go ahead", "goes ahead", "edges ahead"],
              "hu": ["vezet", "vezetés", "vezető gól", "előnybe", "előny", "fordít"]}
SECOND_HALF_WORDS = {"en": ["second half", "second-half", "after the break", "after the restart", "after half-time"],
                     "hu": ["második félidő", "második játékrész", "szünet után", "fordulás után"]}
# neutral venue: word stems, matched at a word boundary so that inflected and compound forms are caught too
# (hazai, hazaiak, hazaiaknak; vendég, vendégek, vendéglátó(k), vendégcsapat; házigazda, házigazdák; hosts, hosting, host side ...)
HOME_AWAY_STEMS = {"en": ["home side", "home team", "home crowd", "home advantage", "home ground", "at home", "the hosts", "host side", "host team",
                          "hosts ", "hosting", "away side", "away team", "away end", "the visitors", "visiting side", "visiting team", "travelling fans"],
                   "hu": ["hazai", "hazaiak", "vendég", "vendéglátó", "vendégcsapat", "házigazd", "idegenben", "otthon", "saját pály"]}
HOME_AWAY_WORDS = HOME_AWAY_STEMS
# a minute is "18'" (not the "19" of "U19's") or "18th minute" / "18. perc"
MINUTE_RE = {"en": re.compile(r"(?:minute\s+(\d{1,3})|(\d{1,3})(?:st|nd|rd|th)\s+minute|(?<![\w.])(\d{1,3})'(?!s\b))"),
             "hu": re.compile(r"(?:(\d{1,3})\.\s*perc|(?<![\w.])(\d{1,3})')")}
SCORE_RE = re.compile(r"(?<![\d+])(\d)\s*[-–:]\s*(\d)(?!\d)")


def check_semantics(text, lang, item, store, cfg):
    """Deterministic football semantics. Returns a list of problem strings (empty = ok)."""
    problems = []
    low = text.lower()
    period = item["moment"]["period"] if item["kind"] == "moment" else store.period_at_ms(item["t_ms"])
    minute = item["minute"]
    clock = store.clock_string(minute, period)
    # 0. stoppage-time notation must match the period: 45+N only in the first half after 45', 90+N only after 90'
    for base, extra in re.findall(r"(45|90)\+(\d{1,2})'?", text):
        wanted = f"{base}+{extra}'"
        if wanted != clock:
            problems.append(f"'{base}+{extra}' is wrong for this event ({'first' if period == 1 else 'second'} half, minute {minute}); the clock is {clock}")
            break
    # 1. goal direction and post-goal score
    if item["kind"] == "moment" and "score_after_goal" in item["moment"]["fact"]:
        fact = item["moment"]["fact"]
        sh, sa = (int(x) for x in fact["score"].split("-"))
        effect = fact.get("goal_effect")
        low_goal = BALANCED_HU.sub(" balanced ", low) if lang == "hu" else low
        equal = any(w in low_goal for w in EQUALISER_WORDS[lang])
        lead = any(re.search(r"(?<![a-záéíóöőúüű])" + re.escape(w), low) for w in LEAD_WORDS[lang])
        if effect == "equaliser" and lead and not equal:
            problems.append(f"the goal is an equaliser ({fact['score_after_goal']}), the text claims a lead")
        if effect != "equaliser" and equal:
            problems.append(f"the goal is not an equaliser (score after the goal {fact['score_after_goal']}: {effect}), the text calls it one")
        for a, b in SCORE_RE.findall(text):
            a, b = int(a), int(b)
            if {a, b} != {sh, sa}:
                problems.append(f"score {a}-{b} in the text does not match the score after the goal {sh}-{sa}")
    # 2. stoppage-time minutes must be written as 45+N / 90+N
    base = 45 if period == 1 else 90
    if minute > base:
        for groups in MINUTE_RE[lang].findall(text):
            n = next((g for g in groups if g), None)
            if n and int(n) == minute:
                problems.append(f"minute {minute} in period {period} must be written as {base}+{minute - base}'")
    # 2b. no invented minutes: "95+" is not a football minute, and no minute after the current clock
    for m in re.finditer(r"(?<![\d.,])(\d{2,3})\s*\+\s*(\d{1,2})?(?![\d%])", text):
        base, extra = int(m.group(1)), int(m.group(2) or 0)
        if base not in (45, 90):
            problems.append(f"'{m.group(0).strip()}' is not a valid minute; stoppage time is written 45+N' or 90+N' (the clock is {clock})")
            break
        cur = (period, minute - (45 if period == 1 else 90) if minute > (45 if period == 1 else 90) else 0)
        when = (1 if base == 45 else 2, extra)
        if when > cur and not (when[0] == period and extra == 0):
            problems.append(f"'{m.group(0).strip()}' is later than the current clock {clock}")
            break
    for groups in MINUTE_RE[lang].findall(text):
        n = next((g for g in groups if g), None)
        if n and int(n) > minute and int(n) <= 130:
            problems.append(f"minute {n} is later than the current clock {clock}")
            break
    # a playing time longer than the match so far ("95 perc játék alatt" at 90')
    elapsed = max(minute, int(item["t_ms"]) // 60000)   # 70' in the second half is 74 whole minutes after kick-off
    for m in re.finditer(r"(?<![\d.,])(\d{2,3})(?![.,]\d)\s*(?:perc(?!ent|ept)\w*|minutes?\b|mins?\b)", text):
        if elapsed < int(m.group(1)) <= 130:
            problems.append(f"'{m.group(0)}' is longer than the match so far (the clock is {clock})")
            break
    problems += check_window_wording(text, lang, item) + check_pressing_average(text, lang, item)
    # 3. "second half" wording only for second-half events; the end of the first half is not the end of the match
    if period == 1 and any(w in low for w in SECOND_HALF_WORDS[lang]):
        problems.append("the event happened in the first half; remove the second-half wording")
    if period == 1 and re.search(r"(?:end|final|closing|dying|last) (?:minutes?|moments?|seconds?|stages?) of the (?:match|game)|"
                                 r"(?:a mérkőzés|a meccs|a találkozó)(?: \w+)? utolsó (?:perc|pillanat|másodperc)\w*|(?:a mérkőzés|a meccs) végén", low):
        problems.append("the event happened at the end of the first half, not at the end of the match")
    # 4. language: the text must be written in the requested language
    hu_marks = bool(re.search(r"[őűáéíóöúü]", low)) or any(w in f" {low} " for w in (" perc", " gól", " és ", " egyenlít", " vezet", " büntető", " helyzet", " lap", " csere", " játékkép", " letámadás", " felé"))
    en_marks = sum(1 for w in (" the ", " and ", " with ", " scores ", " minute", " lead", " goal", " puts ", " at ", " match") if w in f" {low} ")
    if lang == "hu" and (not hu_marks or en_marks >= 2):
        problems.append("the text is not in Hungarian; write it in Hungarian")
    if lang == "en" and (re.search(r"[őűá]", low) or " gól" in low or re.search(r"(?<![a-z])perc(?!ent|ept)", low)):
        problems.append("the text is not in English; write it in English")
    # 4b. grammar smells that the narrator has produced before (nouns used as verbs, doubled words)
    if lang == "en":
        for pat, why in ((r"\b[A-Z][a-z]+ (penalties|goals|headers|braces) [A-Za-z ]*\b(ahead|lead)", "a noun is used as a verb"),
                         (r"\b[A-Z][a-z]+ (penalties|headers|braces|volleys) (?:to|into|past|in|for) ", "a noun is used as a verb"),
                         (r"\b(\w+) \1\b", "a doubled word")):
            if re.search(pat, text):
                problems.append(f"English grammar: {why}; rewrite the sentence")
                break
    # 5. neutral venue: no home / away team wording
    problems.extend(check_neutral_venue(text, lang))
    return problems


def semantic_checks(text, text_obj, lang, item, store, cfg, state, moment=None, focus_pid=None):
    """Every deterministic text check of the pre-check except numbers, names and claim rules, as three lists:
    football semantics (clock, goal, venue, language), player checks (positions, low-data rankings, focus player,
    who is on the pitch) and wording (stock phrases, garbled terms, units, shares, shot words, metric wording).
    Used by the pipeline's pre-check and by compare_agents.py, so that both score with exactly the same checks."""
    # what the UI shows: the overlay and the commentary (or the detail when there is no commentary), agents/outputs.py
    shown = " ".join(str(text_obj.get(k) or "") for k in ("overlay", "commentary")) if text_obj.get("commentary") else \
        " ".join(str(text_obj.get(k) or "") for k in ("overlay", "detail"))
    core = list(check_semantics(text, lang, item, store, cfg))
    player = check_positions(text, lang, store) + check_ranking_low_data(text, lang, store, cfg, focus_pid)
    if focus_pid:
        if focus_is_subject(item, focus_pid, store):
            player += check_focus_subject(text_obj.get("overlay") or "", focus_pid, store, lang)
        player += check_absent_player(text, lang, item, store, focus_pid, shown) + check_player_minutes(text, lang, item, store, focus_pid)
        team_numbers = allowed_numbers(dict(state=state, moment=moment))   # team-level percentages are fine
        player += check_focus_percentages(text, lang, store, focus_pid, item["t_ms"], team_numbers)
        player += check_category_praise(text, lang, store.profiles.get(focus_pid), store.player_name(focus_pid))
    player += check_pitch_status(text, lang, item, store, focus_pid, shown)
    wording = check_stock_phrases(text, lang) + check_garbled(text, lang) + check_not_in_facts(text, lang) + check_units(text, lang)
    wording += check_language_fields(text_obj, lang) + check_team_shares(text, lang, state, store) + check_shot_words(text, lang, moment)
    wording += check_metric_glosses(text, lang) + check_momentum_wording(text, lang, state) + check_pressing_wording(text, lang, pressing_rates(state, moment))
    wording += check_hu_minutes(text, lang) + check_english_sentences(text, lang) + check_team_names(text, store)
    return core, player, wording


def check_neutral_venue(text, lang):
    low = text.lower()
    for w in HOME_AWAY_STEMS[lang]:
        if re.search(r"(?<![a-záéíóöőúüű])" + re.escape(w), low):
            return [f"neutral venue: do not use '{w.strip()}' or any form of it (no home or away team, no hosts)"]
    return []


def check_document(text, lang, store=None):
    """Deterministic checks for long-form outputs (recaps, scouting notes): neutral venue, clock notation, garbled terms,
    the venue's spelling, English terms and the article 'az' before a vowel in Hungarian."""
    problems = check_neutral_venue(text, lang) + check_garbled(text, lang)
    for w in set(re.findall(r"\bHollo\w*", text)):
        if not w.startswith("Hollowmere"):
            problems.append(f"the venue is 'Hollowmere Arena', not '{w}'")
    if lang == "hu":
        m = re.search(r"(?<![\w-])[Aa] ([aáeéiíoóöőuúüű]\w*)", text)
        if m:
            problems.append(f"Hungarian article: 'az {m.group(1)}', not '{m.group(0)}'")
        m = ENGLISH_IN_HU.search(text) or re.search(r"\bcontrol index\b|\bcontrol\s*/\s*chaos\b", text, re.I)
        if m:
            problems.append(f"English words in a Hungarian text: '{m.group(0)}'")
    for base, extra in set(re.findall(r"(45|90)\+(\d{1,2})'?", text)):
        if base == "45" and int(extra) > 6 or base == "90" and int(extra) > 8:
            problems.append(f"implausible stoppage-time notation {base}+{extra}")
    problems += check_metric_glosses(text, lang) + check_pressing_wording(text, lang) + check_momentum_wording(text, lang)
    problems += check_hu_minutes(text, lang) + check_english_sentences(text, lang) + (check_team_names(text, store) if store is not None else [])
    return problems


# --------------------------------------------------------------- players: names kept, focus subject, absent players, positions
def _surname(name):
    return name.split()[-1]


# surnames that are also ordinary words ("nagy" = big in Hungarian): they count as a name only with the full name in the text
WORD_SURNAMES = {"Nagy", "Sow"}


def _named(p, text, words):
    sur = _surname(p["name"])
    return p["name"] in text or (sur in words and (sur not in WORD_SURNAMES or p["name"] in text))


def mentioned_player_ids(text, store):
    """Players named in the text (full name, or a surname as a word when no other player shares it)."""
    words = set(re.findall(r"[\wőűáéíóöúüÁÉÍÓÖŐÚÜŰ'-]+", text))
    shared = {}
    for p in store.players.values():
        shared[_surname(p["name"])] = shared.get(_surname(p["name"]), 0) + 1
    return {pid for pid, p in store.players.items()
            if p["name"] in text or (shared[_surname(p["name"])] == 1 and _named(p, text, words))}


def check_name_changes(before, after, store):
    """Names that appear in `after` but not in `before` (a Verifier repair may remove a name, never add or swap one)."""
    def surnames(t):
        words = set(re.findall(r"[\wőűáéíóöúüÁÉÍÓÖŐÚÜŰ'-]+", t))
        return {_surname(p["name"]) for p in store.players.values() if _named(p, t, words)}
    return sorted(surnames(after) - surnames(before))


def check_focus_subject(overlay, pid, store, lang):
    """A player-focus overlay must name the focus player."""
    name = store.players[pid]["name"]
    if name in overlay or re.search(r"(?<![\w])" + re.escape(_surname(name)) + r"(?![a-z])", overlay):
        return []
    return [f"the focus player {name} must be named in the overlay" if lang == "en" else f"a fókuszjátékost ({name}) meg kell nevezni a feliratban"]


ABSENT_MARKERS = {"en": ["not in this match", "not playing in this match", "does not play in this match", "is not playing", "not involved in this match",
                         "not part of this match", "not on the pitch", "not in action", "not playing today", "doesn't play in this match", "absent from this match"],
                  "hu": ["nem játszik ezen", "nem szerepel ezen", "nem lép pályára", "nincs pályán", "nincs a pályán", "nem a pályán", "nem játszik a mérkőzésen",
                         "nem játszik ma", "nem vesz részt", "nem játszik ebben", "nem szerepel ebben", "nem játszik a meccsen", "nem szerepel a meccsen"]}


ABSENT_RE = {"en": re.compile(r"\b(?:not|n't|never)\s+(?:feature|features|featuring|play|plays|playing|involved|in action|on the pitch|part of|taking part|appear\w*|in the squad)\b"
                               r"|\bdoes not feature\b|\bis absent\b|\bsits out\b|\bnot (?:in|on) (?:this|the|today)"
                               r"|\b(?:not|n't)\b[^.]{0,40}\b(?:this|today's|the) (?:match|game)\b"),
             "hu": re.compile(r"\bnem\s+(?:játszik|játszott|szerepel|lép pályára|vesz részt|tagja)|\bnincs (?:a )?pályán|\bnem a pályán|\bhiányzik")}


def plays_in_match(pid, store):
    return store.players[pid]["team_id"] in (store.home, store.away)


def check_absent_player(text, lang, item, store, pid, shown=None):
    """A focus player whose team does not play this match: the text must say so (in what is shown: overlay and commentary)
    and must not tie him to this match's clock or score."""
    if plays_in_match(pid, store):
        return []
    low = (shown if shown is not None else text).lower()
    name = store.players[pid]["name"]
    problems = []
    if not any(m in low for m in ABSENT_MARKERS[lang]) and not ABSENT_RE[lang].search(low):
        problems.append(f"{name} does not play in this match: say so and describe only his tournament profile")
    period = item["moment"]["period"] if item["kind"] == "moment" else store.period_at_ms(item["t_ms"])
    clock = store.clock_string(item["minute"], period)
    said = any(m in low for m in ABSENT_MARKERS[lang]) or ABSENT_RE[lang].search(low)
    if not said and (clock in text or re.search(r"(?<!\d)" + str(item["minute"]) + r"(?:'|\. perc| minutes?\b|th minute)", text) or SCORE_RE.search(text)):
        problems.append(f"{name} does not play in this match: do not tie him to this match's clock or score")
    return problems


# a player who is not on the pitch at this moment: what a text must say about him (line-ups and substitutions, agents/facts.py pitch_status)
NOT_YET_ON_RE = {"en": re.compile(r"\bon the bench\b|\bnot (?:yet )?on the (?:pitch|field)\b|\bnot (?:yet )?(?:been )?(?:brought|sent) on\b|"
                                  r"\bnot (?:yet )?(?:in|part of) the (?:starting )?(?:line-?up|eleven|xi)\b|\bnot in the starting\b|"
                                  r"\b(?:yet|still) to (?:come on|come off the bench|appear|feature|play|get on)\b|"
                                  r"\bhas(?:n't| not) (?:yet )?(?:come on|appeared|played|featured|entered)\b|\b(?:did not|didn't) start\b|\bunused\b|"
                                  r"\bamong the substitutes\b|\bnot (?:yet )?(?:involved|playing|featured|featuring|in action)\b"),
                 "hu": re.compile(r"kispad\w*|cserepad\w*|nincs (?:még )?(?:a )?pályán|még nem (?:lépett|állt|jött|került) (?:pályára|be)|"
                                  r"nem lépett (?:még )?pályára|nem (?:a )?kezdő\w*|nem kezdett|még nem játsz\w*|egyelőre nem (?:játszik|lépett pályára|állt be)|"
                                  r"nem a pályán|még nem szerepel\w*|nem szerepel (?:még|egyelőre)|a cserék között")}
OFF_RE = {"en": re.compile(r"\bsubstitut\w*|\bsubbed (?:off|out)\b|\btaken off\b|\b(?:was|been|being|is) replaced\b|\breplace[sd]? [^.;]{0,50}\bwith\b|"
                           r"\breplaced by\b|\b(?:came|comes|went|goes|is) off\b(?! the bench)|\bmakes way\b|\bmade way\b|\b[A-Za-z]+ off,? [^.;]{0,40}\bon\b|"
                           r"\bleft the (?:pitch|field|game|match)\b|\bno longer on the (?:pitch|field)\b|\bnot on the (?:pitch|field)\b|"
                           r"\boff the pitch\b|\bsent off\b|\bwithdrawn\b"),
          "hu": re.compile(r"lecserél\w*|\bcsere\w*|lejött|lejön|levitt\w*|elhagyta a pályát|elhagyja a pályát|már nincs a pályán|nincs (?:már )?a pályán|nincs pályán|"
                           r"kiállít\w*|lement a pályáról|lemegy a pályáról|távoz\w*|helyére [^.;]{0,40}(?:áll be|állt be|érkez\w*|jön|jött|lép pályára|lépett pályára)|"
                           r"helyét [^.;]{0,30}(?:vette|veszi) át|leküldt\w*|\ble,? [^.;]{0,40}\bbe\b")}
# "came off the bench" / "a kispadról beállva" mean that he came on: not a bench marker for a player on the pitch
CAME_ON_RE = {"en": re.compile(r"came off the bench|off the bench|as a substitute|from the bench"),
              "hu": re.compile(r"kispadról\w*|cserekén\w*|csereként\w*")}


def check_pitch_status(text, lang, item, store, focus_pid=None, shown=None):
    """A player who is not on the pitch at this moment must not be written about as if he were playing.
    Focus texts: a focus player on the bench (not brought on so far) or substituted must be described as such;
    a focus player on the pitch must not be put on the bench. Every other text: a player of the two teams who has
    not come on yet may not be named without saying so (a player who went off may be named for what he did before)."""
    problems = []
    low = (shown if shown is not None else text).lower()   # the marker must be in what the viewer reads
    period = item["moment"]["period"] if item["kind"] == "moment" else store.period_at_ms(item["t_ms"])
    clock = store.clock_string(item["minute"], period)
    pids = mentioned_player_ids(text, store) | ({focus_pid} if focus_pid else set())
    for pid in sorted(pids):
        if not plays_in_match(pid, store):
            continue          # another team's player: check_absent_player
        st = store.pitch_status(pid, item["t_ms"], clock)
        name = store.players[pid]["name"]
        not_yet = NOT_YET_ON_RE[lang].search(low)
        off = OFF_RE[lang].search(low)
        if st["status"] == "not_on_pitch_yet" and not not_yet:
            problems.append(f"{name} is {st['text']}: say so (e.g. 'on the bench', 'not on the pitch yet') and do not write as if he were playing")
        elif st["status"] == "off" and pid == focus_pid and not (off or not_yet):
            problems.append(f"{name} is {st['text']}: say so and do not write as if he were still playing")
        elif st["on_pitch"] and pid == focus_pid:
            m = NOT_YET_ON_RE[lang].search(CAME_ON_RE[lang].sub(" ", low))
            if m:
                problems.append(f"{name} is {st['text']}: do not write '{m.group(0)}'")
    return problems


# position words -> position codes (group or detail) they are compatible with
POSITION_WORDS = {
    "en": [("left-back", {"LB", "LWB"}), ("left back", {"LB", "LWB"}), ("right-back", {"RB", "RWB"}), ("right back", {"RB", "RWB"}),
           ("full-back", {"FB"}), ("fullback", {"FB"}), ("full back", {"FB"}), ("wing-back", {"FB"}), ("centre-back", {"CB"}), ("center-back", {"CB"}),
           ("central defender", {"CB"}), ("defensive midfielder", {"DM"}), ("holding midfielder", {"DM"}), ("central midfielder", {"CM"}),
           ("attacking midfielder", {"AM"}), ("playmaker", {"AM", "CM"}), ("midfielder", {"DM", "CM", "AM"}), ("winger", {"W"}), ("wide player", {"W"}),
           ("centre-forward", {"ST"}), ("center-forward", {"ST"}), ("striker", {"ST"}), ("defender", {"CB", "FB"}),
           ("goalkeeper", {"GK"}), ("keeper", {"GK"})],
    "hu": [("balhátvéd", {"LB", "LWB"}), ("bal hátvéd", {"LB", "LWB"}), ("jobbhátvéd", {"RB", "RWB"}), ("jobb hátvéd", {"RB", "RWB"}),
           ("szélső hátvéd", {"FB"}), ("oldalhátvéd", {"FB"}), ("középhátvéd", {"CB"}), ("belső védő", {"CB"}), ("hátvéd", {"FB", "CB"}),
           ("védekező középpályás", {"DM"}), ("támadó középpályás", {"AM"}), ("középpályás", {"DM", "CM", "AM"}), ("szélső", {"W"}),
           ("középcsatár", {"ST"}), ("csatár", {"ST"}), ("védő", {"CB", "FB"}), ("kapus", {"GK"})],
}
POSITION_LABEL = {"GK": ("goalkeeper", "kapus"), "CB": ("centre-back", "belső védő"), "FB": ("full-back", "szélső hátvéd"), "DM": ("defensive midfielder", "védekező középpályás"),
                  "CM": ("central midfielder", "középpályás"), "AM": ("attacking midfielder", "támadó középpályás"), "W": ("winger", "szélső"), "ST": ("striker", "csatár")}
DETAIL_LABEL = {"LB": ("left-back", "balhátvéd"), "RB": ("right-back", "jobbhátvéd"), "LW": ("left winger", "bal szélső"), "RW": ("right winger", "jobb szélső")}


_LINEUP_POS = {}


def _lineup_positions(store):
    """Positions played in this match (lineups.csv): a player may play another slot than his primary one."""
    if store.match_id not in _LINEUP_POS:
        import csv
        pos = {}
        with open("data/synthetic/lineups.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["match_id"] == store.match_id:
                    pos.setdefault(r["player_id"], set()).update({r["position_detail"], r["position_group_played"]})
        _LINEUP_POS[store.match_id] = pos
    return _LINEUP_POS[store.match_id]


def player_codes(pid, store):
    p = store.players[pid]
    codes = {p.get("primary_position"), p.get("position_detail"), p.get("secondary_position")} | _lineup_positions(store).get(pid, set())
    return {c for c in codes if c}


def position_label(pid, store, lang):
    p = store.players[pid]
    i = 0 if lang == "en" else 1
    d = DETAIL_LABEL.get(p.get("position_detail"))
    return d[i] if d else POSITION_LABEL.get(p["primary_position"], (p["primary_position"],) * 2)[i]


def check_positions(text, lang, store):
    """A position word next to a player's name must match the player's position in the data (nearest name in the same sentence)."""
    problems = []
    by_surname = {}
    for pid, p in store.players.items():
        by_surname.setdefault(_surname(p["name"]), []).append(pid)
    full_in_text = {pid for pid, p in store.players.items() if p["name"] in text}
    for sent in CLAUSE_END_RE.split(text):
        low = sent.lower()
        names = []
        for sur, pids in by_surname.items():
            cand = pids if (len(pids) == 1 and sur not in WORD_SURNAMES) else [x for x in pids if x in full_in_text]
            if len(cand) != 1:
                continue          # an ambiguous surname (or a word like "Nagy") without the full name: do not guess
            for m in re.finditer(r"(?<![\w])" + re.escape(sur) + r"(?![a-záéíóöőúüű])", sent):   # names are case-sensitive
                names.append((m.start(), cand[0]))
        if not names:
            continue
        taken = []
        for word, codes in POSITION_WORDS[lang]:
            for m in re.finditer(r"(?<![a-záéíóöőúüű-])" + re.escape(word) + (r"(?![a-z])" if lang == "en" else r"(?:ként|ja|je|ok|ek|t|nak|nek|ja|unk)?(?![a-záéíóöőúüű])"), low):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                pos, pid = min(names, key=lambda x: abs(x[0] - m.start()))
                if abs(pos - m.start()) > 60:
                    continue
                if not (codes & player_codes(pid, store)) and not ({"FB"} & codes and player_codes(pid, store) & {"LB", "RB", "LWB", "RWB"}):
                    problems.append(f"{store.players[pid]['name']} is a {position_label(pid, store, 'en')} in the data, not a '{word}'")
    return problems


def check_ranking_low_data(text, lang, store, cfg, focus_pid=None):
    """No ranking or elite claim about a player below the low-data threshold (tournament minutes before this match):
    in a player-focus text about the focus player, otherwise about a low-data player named in the same sentence."""
    problems = []
    for sent in CLAUSE_END_RE.split(text):
        # "his top strengths / categories", "top speed", "top of the table", "top scorer" do not rank the player against others
        low = re.sub(r"\btop (?:strengths?|categor\w*|attributes?|speed|of the table|of the standings|scorer|two|2|three|3)\b", " ", sent.lower())
        hits = [w for w in RANKING_WORDS[lang] if re.search(r"(?<![a-záéíóöőúüű])" + re.escape(w) + (r"(?!\d)" if w[-1].isdigit() else ""), low)]
        if not hits:
            continue
        pids = {focus_pid} if focus_pid else mentioned_player_ids(sent, store)
        for pid in pids:
            prof = store.profiles.get(pid)
            if prof and float(prof["minutes"]) < cfg["low_data_minutes_tournament"]:
                problems.append(f"{store.players[pid]['name']} has only {float(prof['minutes']):.0f} tournament minutes (low data): no ranking or elite claim ('{hits[0]}')")
    return sorted(set(problems))


RANKING_WORDS = {"en": ["top ", "top-", "top fb", "top full-back", "top fullback", "top cb", "top dm", "top cm", "top am", "top winger", "top striker", "top midfielder",
                        "top defender", "top player", "top-tier", "top performer", "top-ranked", "highest-rated", "best fb", "best full-back", "best in his position",
                        "the best", "number one", "ranked first", "ranked 1", "ranked no. 1", "rank 1", "#1", "elite", "world-class", "outstanding", "standout", "star of"],
                 "hu": ["legjobb", "top ", "első számú", "rangsor élén", "a rangsor első", "élvonalbeli", "elit", "kiemelkedő", "kimagasló", "világklasszis", "sztár"]}


# --------------------------------------------------------------- recap facts: points, margins, xG ratios, shots, scores
BEFORE_WORDS = {"en": ["before kick", "before the match", "before the game", "entered the match", "entering the match", "entering the game", "entered the game",
                       "going into", "heading into", "ahead of the match", "coming into", "prior to the match", "entering the final", "entered the final"],
                "hu": ["meccs előtt", "mérkőzés előtt", "kezdés előtt", "előtt álltak", "előtt állt", "a forduló előtt", "érkezett", "érkeztek"]}
NUM_WORDS = {"one": 1, "a": 1, "two": 2, "three": 3, "four": 4, "egy": 1, "két": 2, "kettő": 2, "három": 3, "négy": 4}


def check_recap(text, lang, facts, store):
    """Numbers of a recap against its facts: points, point margins, 'level on points', shots / shots on target, xG ratios, scores."""
    problems = []
    t = facts["tournament"]
    before = sorted((r["points"] for r in t["standings_before"]), reverse=True)
    final = sorted((r["points"] for r in t["final_standings"]), reverse=True)
    pts_ok = set(before) | set(final)
    gap_before, gap_final = before[0] - before[1], final[0] - final[1]
    for sent in SENT_RE.split(text):
        low = sent.lower()
        is_before = any(w in low for w in BEFORE_WORDS[lang])
        for m in re.finditer(r"(\d+)\s*(?:points?\b|pts\b|ponttal|pontot|pontos|pont\b)", low):
            margin = re.search(r"(?:by|with)\s*$", low[:m.start()]) or re.match(r"\s*(?:megelőzve|előnnyel|előnye|ahead|clear|lead|gap|margin|cushion)", low[m.end():])
            if int(m.group(1)) not in pts_ok and not margin:
                problems.append(f"{m.group(1)} points is not in the standings")
        if re.search(r"level on points|equal on points|same number of points|pontegyenlő|azonos pontszám|ugyanannyi pont", low) and gap_before != 0:
            problems.append(f"the teams were not level on points before the match ({before[0]} and {before[1]})")
        for m in re.finditer(r"by (one|a|two|three|four|\d+) points?|(egy|két|kettő|három|négy|\d+) ponttal (?:megelőzve|előzte|előzve|előzték|előnnyel|lett|végzett|nyert)|(one|two|three|\d+)-point (?:lead|gap|margin|cushion)", low):
            w = next(g for g in m.groups() if g)
            n = NUM_WORDS.get(w, int(w) if w.isdigit() else None)
            if n in pts_ok and re.search(r"(?:lett|végzett|nyert)$", m.group(0)):
                continue   # "12 ponttal végzett az élen": finished with 12 points (a total, not a margin)
            want = gap_before if is_before else gap_final
            if n is not None and n != want:
                problems.append(f"the points margin is {want} ({'before' if is_before else 'after'} the match), not {n}")
        shots = {int(float(r["shots"])) for r in facts["team_kpis"]}
        for m in re.finditer(r"(\d+)\s+(?:shots? on target|kapura lövés\w*|kaput eltaláló lövés\w*|kaput eltalál\w*)", low):
            problems.append(f"'{m.group(0)}': shots on target are not in the facts (shots only: {sorted(shots)})")
        for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(?:%|százalék\w*)\s*(?:-?kal|-?kel)?\s*(?:több|kevesebb|more|fewer|less)\s+(lövés\w*|shots?|passz\w*|pass(?:es)?)", low):
            key = "shots" if m.group(2).startswith(("lövés", "shot")) else "passes"
            vals = sorted(float(r[key]) for r in facts["team_kpis"])
            actual = (vals[1] / vals[0] - 1) * 100 if vals[0] else None
            if actual is not None and abs(float(m.group(1).replace(",", ".")) - actual) > 10:
                problems.append(f"'{m.group(0)}': the difference is {actual:.0f} % ({vals[1]:g} vs {vals[0]:g} {key})")
        if re.search(r"tripl|treble|háromszor|megháromszoroz", low) and "xg" in low:
            xg = sorted(float(r["xg"]) for r in facts["team_kpis"])
            if xg[0] and xg[1] / xg[0] < 2.5:
                problems.append(f"xG {xg[1]:.2f} vs {xg[0]:.2f} is not three times as much")
        if re.search(r"doubl|kétszer|megdupláz", low) and "xg" in low:
            xg = sorted(float(r["xg"]) for r in facts["team_kpis"])
            if xg[0] and xg[1] / xg[0] < 1.8:
                problems.append(f"xG {xg[1]:.2f} vs {xg[0]:.2f} is not twice as much")
    scores = {"0-0"}
    for g in facts["goals"]:
        a, b = g["fact"]["score"].split("-")
        scores |= {f"{a}-{b}", f"{b}-{a}"}
    # a standings-table row's "7-7" is goals for - goals against: checked against the final standings, not as a match score
    rows = [ln for ln in text.split("\n") if ln.lstrip().startswith("|")]
    for ln in rows:
        team = next((r for r in t["final_standings"] if r["team"].replace(" U19", "") in ln and "gf" in r), None)
        for a, b in SCORE_RE.findall(ln):
            if team and (int(a), int(b)) != (int(team["gf"]), int(team["ga"])):
                problems.append(f"{team['team']}: goals {a}-{b} in the table, the final standings say {team['gf']}-{team['ga']}")
    for a, b in SCORE_RE.findall("\n".join(ln for ln in text.split("\n") if not ln.lstrip().startswith("|"))):
        if f"{a}-{b}" not in scores:
            problems.append(f"score {a}-{b} never happened in this match")
            break
    problems += check_positions(text, lang, store) + check_team_names(text, store)
    problems += check_recap_wording(text, lang, facts, store)
    return sorted(set(problems))


def focus_is_subject(item, pid, store):
    """A focus text is about the focus player on a state card or a moment he is involved in (a goal by someone else is not)."""
    if item["kind"] == "state":
        return True
    m = item["moment"]
    return m.get("player_id") == pid or store.player_name(pid) in json.dumps(m.get("fact", {}), ensure_ascii=False)


def check_player_minutes(text, lang, item, store, pid):
    """A focus player's playing time: '75 perc játék alatt' at 75' is wrong when he has been on the pitch for 21 minutes."""
    if not plays_in_match(pid, store):
        return []
    live = (store.player_live(pid, item["t_ms"]) or {}).get("minutes")
    if live is None:
        return []
    minute = item["minute"]
    for m in re.finditer(r"(?<![\d.,])(\d{1,3})(?![.,]\d)\s*(?:perc(?!ent|ept)\w*|minutes?\b|mins?\b)", text):
        n = int(m.group(1))
        if abs(n - minute) <= 1 and live < n - 3:
            return [f"{store.players[pid]['name']} has played {live:.0f} minutes so far, not {n} (the match clock is not his playing time)"]
    return []


# --------------------------------------------------------------- wording: stock phrases, garbled words, translated team names (hand review of 26 Oct)
STOCK_PHRASES = {"en": ["tight title decider", "narrow 3-2 lead", "nail-biting", "what a thriller", "pulsating", "thrilling title decider",
                        "intense title decider"],
                 "hu": ["szoros címdöntő", "kiélezett címdöntő", "lélegzetelállító"]}
GARBLED = {"en": ["two foots", "physical duels"],
           "hu": ["presztízs", "sajtószél", "egaliz", "káoszos", "térfélyúlyoz", "kísért xg", "észlelési adat", "finisel", "góltani",
                  "címrámérkőzés", "legiharc", "légiharc", "északi", "északiak", "labdakiért", "góljátszás", "sikarral", "sikarr",
                  "mérkőzés-ellenőrzési", "nyílttá tett", "középső pontszám", "meccsmenedzsment", "irányítási index",
                  "középmezőnyös megbízhatóság", "presszionál", "területi mutató", "kifinomult játéklendület", "kapariórás", "káosszabályozott",
                  "irányítás indexe", "irányítási indexe", "fő esélyesként emelked", "nyitott állás", "nyitott bajnokin", "magát lelépni",
                  "fizikai párharc", "tornagyőztes gól", "kontroll index"]}
# the word to write instead (given to the Narrator in the repair request)
GARBLED_FIX = {"labdakiért": "labdáért", "góljátszás": "gólhoz való hozzájárulás", "sikarral": "sikerrel", "sikarr": "siker",
               "mérkőzés-ellenőrzési": "kontrollindex", "meccsmenedzsment": "kontrollindex", "irányítási index": "kontrollindex",
               "középső pontszám": "pozíciós pontszám", "egaliz": "egyenlít", "káoszos": "kaotikus", "északi": "Northbridge",
               "északiak": "Northbridge", "nyílttá tett": "nyitott", "presztízs": "letámadás", "sajtószél": "szélről",
               "térfélyúlyoz": "területi fölény", "kísért xg": "várható gól (xG)", "észlelési adat": "adat", "finisel": "befejezés",
               "góltani": "gól", "címrámérkőzés": "címdöntő", "légiharc": "fejpárbaj", "legiharc": "fejpárbaj",
               "középmezőnyös megbízhatóság": "közepes megbízhatóság", "presszionál": "letámad",
               "területi mutató": "pozíciós pontszám (position score) or területi fölény (field tilt)", "kifinomult játéklendület": "lendület",
               "kapariórás": "labdabirtoklás", "káosszabályozott": "kaotikus", "irányítás indexe": "kontrollindex", "irányítási indexe": "kontrollindex",
               "fő esélyesként emelked": "a győztes nyeri meg a tornát", "nyitott állás": "döntetlen (egyenlő) állás", "nyitott bajnokin": "a még nyitott bajnoki versenyben",
               "magát lelépni": "nem adta fel", "fizikai párharc": "fizikai mutató (physical, a 0-100 category score; duels are offensive / defensive / aerial)",
               "physical duels": "the physical category score (duels are offensive, defensive or aerial)",
               "tornagyőztes gól": "első gólja a tornán (a tornagyőztes gól a 49. perces volt)", "kontroll index": "kontrollindex"}
# facts the data never has: a defending champion, an empty net / open goal (checked in every text)
NOT_IN_FACTS = {"en": [(r"defending champion|title holders?|reigning champion", "there is no defending champion in this tournament"),
                       (r"empty net|open goal|empty goal", "an empty net / open goal is not in the facts")],
                "hu": [(r"címvéd", "there is no defending champion in this tournament"), (r"üres kapu", "an empty net / open goal is not in the facts")]}
ENGLISH_IN_HU = re.compile(r"(?<![a-záéíóöőúüű])(?:chaos|pressures|the match|title decider|equaliser|goal kick|passes per possession|field tilt|possession\w*|match)(?![a-záéíóöőúüű])", re.I)


TEAM_SUFFIXES = r"United|FC|SV|BK|City|Athletic|Town|Rovers|Wanderers|Albion|Sporting|AC|SC"


def check_team_names(text, store):
    """A team name written with another club's suffix ('Northbridge United' for Northbridge FC)."""
    for t in store.teams.values():
        name = t["team_name"].replace(" U19", "")
        city = t["city"]
        own = name[len(city):].strip()
        for m in re.finditer(re.escape(city) + r"\s+(" + TEAM_SUFFIXES + r")\b", text):
            if m.group(1) != own:
                return [f"the team is '{name}', not '{m.group(0)}'"]
    return []


def check_stock_phrases(text, lang):
    low = text.lower()
    hits = [p for p in STOCK_PHRASES[lang] if p in low]
    return [f"stock phrase '{hits[0]}': say it in your own words or leave it out"] if hits else []


def check_not_in_facts(text, lang):
    low = text.lower()
    return [why for pat, why in NOT_IN_FACTS[lang] if re.search(pat, low)][:1]


# PPDA explained wrongly ("Pressures allowed", "engedett passzok nyomás alatt"): the agents had no definition (fixed in agents/llm.py STYLE)
PPDA_GLOSS = {"en": "PPDA = passes allowed per defensive action (the opponent's passes per defensive action; lower = more intense pressing)",
              "hu": "PPDA = az ellenfél passzai egy védekező akcióra (alacsonyabb = intenzívebb letámadás)"}


def check_metric_glosses(text, lang):
    """A metric explained in the text must be explained right: PPDA is passes allowed per defensive action."""
    low = text.lower()
    bad = re.search(r"pressures? allowed|pressure allowed|engedett passz\w* nyomás alatt|nyomás alatt engedett|engedett nyomás", low)
    if not bad:
        m = re.search(r"ppda\s*\(([^)]{3,80})\)", low)
        if m and not re.search(r"pass" if lang == "en" else r"passz", m.group(1)):
            bad = m
    return [f"wrong explanation of PPDA ('{bad.group(0)}'): {PPDA_GLOSS[lang]}"] if bad else []


PRESS_EFFECTIVE = {"en": r"(?:more|less) effective (?:press\w*|pressure)|(?:press\w*|pressure)[^.;]{0,30}(?:more|less) effective|effective(?:ness)? of (?:the |their |his )?press\w*",
                   "hu": r"hatékonyabb (?:a )?(?:letámadás|nyomásgyakorlás|pressing)\w*|(?:letámadás|nyomásgyakorlás|pressing)\w*[^.;]{0,25}hatékonyabb\w*|"
                         r"hatékony (?:letámadás|nyomásgyakorlás|pressing)\w*|(?:letámadás|nyomásgyakorlás)\w* hatékonyság\w*"}
PRESS_COUNT = {"en": r"pressures?\b", "hu": r"letámadás\w*|nyomásgyakorlás\w*"}
PER_MINUTE = {"en": r"per minute|a minute|/\s*min|per min\b|intens\w*|\brate\b|\blevel\b|ppda",
              "hu": r"percenként|percente|/\s*perc|egy perc(?!\s+alatt)|intenzitás\w*|intenzív\w*|mérték\w*|szint\w*|ppda"}


def pressing_rates(state, moment=None):
    """The pressing intensities (pressures per minute) and per-5-minute averages in an item's facts."""
    rates = set()
    for t in ((state or {}).get("teams") or {}).values():
        for w in ("5min", "15min"):
            v = (t.get(w) or {}).get("pressing_intensity")
            if v is not None:
                rates.add(round(float(v), 2))
    for k, v in (((moment or {}).get("fact")) or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and ("rate" in k or "per_5min" in k or "intensity" in k):
            rates.add(round(float(v), 2))
    return rates


def check_pressing_wording(text, lang, rates=None):
    """The facts measure how intense the pressing is (pressures per minute, PPDA), never how effective; a decimal pressing
    intensity is a rate per minute, not a number of pressures ('174 pressures overall and 1.87 in the last 15 minutes').
    `rates`: the item's pressing intensities (only these decimals are checked); without them, decimals below 10."""
    low = text.lower()
    problems = []
    m = re.search(PRESS_EFFECTIVE[lang], low)
    if m:
        problems.append(f"'{m.group(0)}': the facts measure the intensity of the pressing (pressures per minute, PPDA), not its effectiveness: "
                        + ("write 'more intense'" if lang == "en" else "írd: 'intenzívebb'"))
    for sent in CLAUSE_END_RE.split(low):
        if not re.search(PRESS_COUNT[lang], sent) or re.search(PER_MINUTE[lang], sent):
            continue
        for d in re.finditer(r"(?<![\w.,])(\d+[.,]\d+)(?!\s*%|[\d])", sent):
            v = float(d.group(1).replace(",", "."))
            if (rates is not None and not any(abs(v - r) <= 0.051 for r in rates)) or (rates is None and v >= 10):
                continue
            near = [w for w in re.finditer(PRESS_COUNT[lang], sent) if abs(w.start() - d.start()) <= 40]
            if near and not re.search(r"(?:xg|ppda|momentum|lendület|index)\W{0,12}$", sent[:d.start()]):
                problems.append(f"'{d.group(1)}' next to '{near[0].group(0)}': pressing intensity is pressures per minute "
                                + ("(write 'X pressures per minute')" if lang == "en" else "(írd: 'X letámadás percenként')"))
                break
        if len(problems) > 1:
            break
    return problems[:2]


SLIGHT = {"en": r"\bslight\w*|\bmarginal\w*|\bsmall edge|\bnarrow edge|\bminimal", "hu": r"\benyh[eé]\w*|\bkissé|\bkis mértékű|\bminimális|\bcsekély"}


def check_momentum_wording(text, lang, state=None):
    """'A slight edge' for a momentum of 0.51 (scale -1 … +1): a slight momentum is below 0.4. Without a number in the
    sentence the state's momentum is used (home perspective: the same size for both teams)."""
    for sent in CLAUSE_END_RE.split(text.lower()):
        mom = [m.start() for m in re.finditer(r"momentum|lendület", sent)]
        if mom and any(min(abs(w.start() - x) for x in mom) <= 35 for w in re.finditer(SLIGHT[lang], sent)):   # 'slight' next to the momentum word
            nums = [float(d.group(1).replace(",", ".")) for d in re.finditer(r"(?<![\w.,])[+-]?(0[.,]\d+|1[.,]0+)(?![\d%])", sent)]
            if not nums and state and state.get("teams") and not re.search(r"shift|swing|swung|elmozdul|eltol|változ", sent):   # a slight change is no level
                nums = [abs(t.get("momentum") or 0) for t in state["teams"].values()][:1]
            for v in nums:
                if 0.4 <= v <= 1.0:
                    return [f"momentum {v:g} is not slight (the scale is -1 … +1; slight is below 0.4)"]
    return []


def _hu_vowel_number(n):
    """Does the Hungarian word of this number start with a vowel (egy, öt, ötven…, ezer)? Then the article is 'az'."""
    return n == 1 or n == 5 or 50 <= n <= 59 or 500 <= n <= 599 or 1000 <= n <= 1999


def check_hu_minutes(text, lang):
    """Hungarian minutes: 'a 60. percben', not '60-nál' or "2'-nál" ('3-2-nél' for a score and '60-nál több' for a comparison
    are fine); the article before a number follows its spoken form ('az 54.', 'a 49.')."""
    if lang != "hu":
        return []
    problems = []
    for m in re.finditer(r"(?<![\d+–\-.,])((?:45|90)\+\d{1,2}|\d{1,3})(?:'|’)?-?n[aáeé]l\b(?!\s+(?:\w+\s+)?(?:nagyobb|több|kevesebb|magasabb|alacsonyabb|jobb|rosszabb|kisebb|erősebb|gyengébb))", text):
        if "+" in m.group(1) or int(m.group(1)) <= 130:
            problems.append(f"'{m.group(0)}': a minute is written 'a {m.group(1).replace('+', '+')}. percben' in Hungarian")
            break
    for m in re.finditer(r"(?<![\w-])([Aa]z?) (\d{1,4})(?=[.%,\s'’-])", text):
        art, n = m.group(1).lower(), int(m.group(2))
        if (art == "az") != _hu_vowel_number(n):
            problems.append(f"Hungarian article: '{'az' if _hu_vowel_number(n) else 'a'} {n}', not '{m.group(0)}'")
            break
    return problems


EN_FUNCTION_WORDS = re.compile(r"\b(?:the|and|with|of|at|is|are|in|to|for|his|their|above|below|scores?)\b")


def check_english_sentences(text, lang):
    """An English sentence inside a Hungarian text ('category scores above 79.5 and 84.4')."""
    if lang != "hu":
        return []
    for sent in CLAUSE_END_RE.split(text):
        low = sent.lower()
        if len(EN_FUNCTION_WORDS.findall(low)) >= 3 and not re.search(r"[őűáéíóöúü]", low) and not re.search(r"\b(?:és|az?|egy|nem|is|meg)\b", low):
            return [f"English sentence in a Hungarian text: '{sent.strip()[:60]}': write it in Hungarian"]
    return []


# category praise: "Novak's ball winning and pressing stand out (41.9 and 46.4)" — a standout category needs a score of 75 or more
PRAISE = {"en": r"stand(?:s|ing)? out|standout|outstanding|excel\w*|exceptional|impressive|elite|remarkable|superb|excellent",
          "hu": r"kiemelked\w*|kimagasló\w*|kiváló\w*|kitűnő\w*|lenyűgöző\w*|elit\b|parádés\w*"}
PRAISE_MIN = 75.0
CAT_WORDS = {"cat_finishing": ("finishing", "befejez"), "cat_goal_contribution": ("goal contribution", "gólhoz való hozzájárul"),
             "cat_chance_creation": ("chance creation", "helyzetteremt"), "cat_passing": ("passing", "passz"), "cat_progression": ("progression", "előrevi"),
             "cat_offensive_duels": ("offensive duel", "támadó párharc"), "cat_defensive_duels": ("defensive duel", "védekező párharc"),
             "cat_aerial_play": ("aerial", "fejpárbaj"), "cat_defensive_activity": ("defensive activity", "védekező aktivitás"),
             "cat_pressing": ("pressing", "letámad"), "cat_physical": ("physical", "fizikai")}
CLAUSE_SPLIT = re.compile(r",(?=\s)|;| but | while | whereas | though | although | yet | de | míg | viszont | azonban | ugyanakkor | miközben | bár ")   # "68,2" is a number


def check_category_praise(text, lang, profile, name):
    """A category called outstanding / 'kiemelkedő' must have a category score of at least 75 in the profile the text uses
    (the numbers in the same clause, else the category named in it)."""
    if not profile:
        return []
    cats = {k: float(v) for k, v in profile.items() if k.startswith("cat_") and v not in ("", None)}
    i = 0 if lang == "en" else 1
    for sent in SENT_RE.split(text):
        for clause in CLAUSE_SPLIT.split(sent.lower()):
            if not re.search(PRAISE[lang], clause):
                continue
            nums = [float(x.replace(",", ".")) for x in re.findall(r"(?<![\w.,])(\d{1,2}[.,]\d)(?![\d%])", clause)]
            low_cats = [(k, v) for k, v in cats.items() if any(abs(v - n) <= 0.05 for n in nums) and v < PRAISE_MIN]
            if not nums and not re.search(r"\d\s*%", clause):   # a clause with a percentage praises a live rate, not a category score
                low_cats = [(k, v) for k, v in cats.items() if CAT_WORDS.get(k) and CAT_WORDS[k][i] in clause and v < PRAISE_MIN]
            if low_cats:
                k, v = low_cats[0]
                return [f"{name}'s {CAT_WORDS.get(k, (k,))[0]} score is {v:g}: not outstanding (a standout category needs {PRAISE_MIN:g} or more)"]
    return []


def check_units(text, lang):
    """Units the facts never use: possession changes per second, the control index as one team's advantage."""
    low = text.lower()
    problems = []
    if re.search(r"(?:possession changes?|turnovers?)[^.;]{0,30}per second|másodpercenként[^.;]{0,40}(?:labdabirtokl|váltás|labdavesztés)|"
                 r"(?:labdabirtokl|váltás)\w*[^.;]{0,40}másodpercenként", low):
        problems.append("possession changes are counted per minute, not per second")
    if re.search(r"control index(?:(?!\.\s|tilt|possession|momentum|press|territor)[^;]){0,40}(?:favou?r(?:s|ing)?\b|in favou?r of|advantage|edge|dominan\w*)|(?:favou?ring|in favou?r of|advantage|edge|lead)\w*[^.;,]{0,25}control index|"
                 r"control (?:advantage|edge)|(?:advantage|edge) in (?:the )?control(?! regime)|(?:their|its) control index|"
                 r"(?:northbridge|vallora)[^.;,]{0,40}(?:switch|shift|mov)\w* (?:from [^.;,]{0,40})?to (?:a )?control|"
                 r"kontrollindex\w*(?:(?!\.\s|fölény|birtokl|lendület|nyomás|letámad)[^;]){0,60}(?:javára|kedvez)|kontrollindex\w*[^.;,]{0,25}(?:előny|fölény)|(?:előny|fölény)\w*[^.;,]{0,25}kontrollindex|kontroll ?előny|"
                 r"(?:northbridge|vallora)\w*[^.;,]{0,30}felé billen\w* a kontrollindex|"
                 r"(?:northbridge|vallora)[^.;,]{0,50}(?:kontrollra|kontrollált játékra)", low):
        problems.append("the control index and the regime describe the whole game (control vs chaos), not one team's advantage: "
                        "write e.g. 'the match is in a controlled / balanced / chaotic phase (control index X)'")
    if re.search(r"\d+[.,]\d+\s*(?:nyomás|letámadás)\w*\s*/\s*5\s*perc|\d+[.,]\d+\s*pressures?\s*(?:per|/|every)\s*(?:5|five)\s*min", low):
        problems.append("pressing intensity is pressures per minute (e.g. 2.27 per minute), not per 5 minutes")
    if lang == "hu" and re.search(r"passz\w* száma(?! (?:labda)?birtoklásonként)[^.;]{0,25}\d+,\d", low):
        problems.append("passes per possession is 'passz labdabirtoklásonként', not the number of passes")
    return problems


SHARE_WORDS = {"possession_pct": {"en": ("possession", "of the ball"), "hu": ("birtokl", "labdát")},
               "field_tilt_pct": {"en": ("field tilt", "tilt", "territor"), "hu": ("területi fölény", "területet")}}
PCT_RE = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(?:%|százal|per ?cent)")
MORE_SHARE = {"possession_pct": {"en": r"more (?:of the )?(?:ball|possession)|possession (?:edge|advantage)|(?:edge|advantage) in possession|dominat\w* possession",
                                 "hu": r"többet (?:tartja|birtokolja) a labdát|több labdabirtokl\w*|labdabirtoklásban (?:vezet|előny|áll jobban)"},
              "field_tilt_pct": {"en": r"more (?:of the )?(?:field|territory)|territorial (?:edge|advantage|dominance)|(?:edge|advantage) in (?:field tilt|territory)",
                                 "hu": r"többet birtokolja a területet|több területi fölény\w*|területi fölényben van"}}


def _team_marks(sentence, store):
    """(position, team_id) of every mention of one of the two match teams in a lower-case sentence."""
    out = []
    for tid in (store.home, store.away):
        key = store.teams[tid]["city"].lower()
        out += [(m.start(), tid) for m in re.finditer(re.escape(key), sentence)]
    return sorted(out)


def _team_before(marks, pos):
    """The team named last before this position ('A csapat …, míg a Northbridge-é …' names no team before the first share: not checked)."""
    before = [t for p, t in marks if p < pos]
    return before[-1] if before else None


def check_team_shares(text, lang, state, store):
    """A possession or field-tilt share must belong to the team it is written next to (5-min, 15-min or match window):
    '60 % possession' of one team written for the other is a swap the number check cannot see. Wordy claims
    ('more of the ball', 'többet tartja a labdát') need that team above 50 % in at least one window."""
    problems = []
    if not state or not state.get("teams"):
        return problems
    other = {store.home: store.away, store.away: store.home}
    def values(tid, key, windows=("5min", "15min", "match")):
        return [state["teams"][tid][w].get(key) for w in windows if state["teams"][tid].get(w, {}).get(key) is not None]
    name = lambda tid: store.teams[tid]["city"]
    for sent in CLAUSE_END_RE.split(text):
        low = sent.lower()
        marks = _team_marks(low, store)
        if not marks:
            continue
        for m in PCT_RE.finditer(low):
            n = float(m.group(1).replace(",", "."))
            near = []
            for key, words in SHARE_WORDS.items():
                for w in words[lang]:
                    near += [(min(abs(x.start() - m.start()), abs(x.start() - m.end())), key) for x in re.finditer(re.escape(w), low)]
            near = [x for x in near if x[0] <= 45]
            if not near:
                continue
            key = min(near)[1]
            right_after = [t for p, t in marks if 0 <= p - m.end() <= 3 and not low[m.end():p].strip()]   # "48.76% Northbridge", not "49.2%, Northbridge"
            tid = right_after[0] if right_after else _team_before(marks, m.start())
            if right_after:
                if not any(abs(n - v) <= 0.6 for v in values(tid, key)) and any(abs(n - v) <= 0.6 for v in values(other[tid], key)):
                    what = "possession" if key == "possession_pct" else "field tilt"
                    problems.append(f"{m.group(1)}% {what} is {name(other[tid])}'s, not {name(tid)}'s")
                continue
            if tid is None or other[tid] in [t for p, t in marks if p < m.start()]:
                continue   # no team before, or both teams before ("Vallora holds … compared to Northbridge's 0.208 and had 56.1 %"): not decidable
            if not any(abs(n - v) <= 0.6 for v in values(tid, key)) and any(abs(n - v) <= 0.6 for v in values(other[tid], key)):
                what = "possession" if key == "possession_pct" else "field tilt"
                problems.append(f"{m.group(1)}% {what} is {name(other[tid])}'s, not {name(tid)}'s")
        for key, pats in MORE_SHARE.items():
            for m in re.finditer(pats[lang], low):
                tid = _team_before(marks, m.start())
                if tid is None:
                    continue
                vals = values(tid, key)
                if vals and max(vals) < 50:
                    what = "possession" if key == "possession_pct" else "field tilt"
                    problems.append(f"{name(tid)} has less {what} ({' / '.join(f'{v:.0f}%' for v in vals)} in the last 5 min / 15 min / match): "
                                    f"'{m.group(0)}' belongs to {name(other[tid])}")
    return problems


POWER_WORDS = {"en": r"(?:powerful|thunderous|rocket|blistering|fierce|thumping|bullet|ferocious|piledriver|stunning|unstoppable)\W+(?:(?:\d+[.,]?\d*\s*(?:km/h|m)?|\w+)\W+){0,3}?(?:header|headed|shot|strike|finish|volley|effort|drive|goal)",
               "hu": r"(?:erős|erőteljes|bomba|hatalmas|kemény|ágyú)\w*\W+(?:(?:\d+[.,]?\d*\s*(?:km/h|m)?|\w+)\W+){0,3}?(?:fejes|lövés|lövéssel|találat|gól)"}
POWER_MIN_KMH = 70.0   # "powerful" needs a fast shot (U19 match shots are usually 80-100 km/h with the foot, headers far slower)


def check_shot_words(text, lang, moment):
    """'A powerful header' when the facts give the shot speed as 30 km/h: the word must match the measured speed."""
    speed = (((moment or {}).get("ball_metrics") or {}).get("shot") or {}).get("shot_speed_kmh")
    if speed is None or speed >= POWER_MIN_KMH:
        return []
    m = re.search(r"(?<![a-záéíóöőúüű])" + POWER_WORDS[lang], text.lower())
    if not m:
        return []
    return [f"the shot was {speed:.0f} km/h: do not call it '{m.group(0)}' (a powerful shot is 80 km/h or more); say what the facts say"]


def hu_decimal_commas(text):
    """Hungarian typography: 57.1 % is written 57,1 % (the number stays the same; used when a Hungarian text is shown)."""
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text or "")


def check_language_fields(text_obj, lang):
    """Each field in the requested language: an English overlay in the Hungarian feed is not caught by the whole-text check."""
    if lang != "hu":
        return []
    ov = (text_obj.get("overlay") or "")
    low = f" {ov.lower()} "
    en_marks = sum(1 for w in (" the ", " and ", " in ", " with ", " leads ", " pressures ", " mins", " scores ", " at ") if w in low)
    hu_marks = bool(re.search(r"[őűáéíóöúü]", low)) or any(w in low for w in (" vezet", " gól", " perc", " letámad", " és "))
    problems = []
    if en_marks >= 2 and not hu_marks:
        problems.append("the overlay is in English; write it in Hungarian")
    joined = " ".join(str(text_obj.get(k) or "") for k in ("overlay", "commentary", "detail"))
    if ENGLISH_IN_HU.search(joined):
        w = ENGLISH_IN_HU.search(joined).group(0)
        hu = {"chaos": "káosz", "pressures": "letámadás", "the match": "a mérkőzés", "title decider": "címdöntő", "equaliser": "egyenlítő gól", "goal kick": "kirúgás",
              "passes per possession": "passz labdabirtoklásonként", "field tilt": "területi fölény"}.get(w.lower(), "")
        problems.append(f"English word '{w}' in a Hungarian text" + (f": write '{hu}'" if hu else ""))
    return problems


def check_garbled(text, lang):
    low = text.lower()
    hits = [w for w in GARBLED[lang] if re.search(r"(?<![a-záéíóöőúüű])" + re.escape(w), low)]
    out = []
    for w in hits[:3]:
        if w.startswith("észak"):
            out.append("do not translate team names ('északi' for Northbridge): write Northbridge")
            continue
        fix = GARBLED_FIX.get(w)
        what = "is not a Hungarian football term" if lang == "hu" else "is not the term the facts use"
        out.append(f"'{w}…' {what}: write '{fix}'" if fix else f"'{w}…' {what}: use the glossary word")
    return out


WINDOW_WORDS = {"en": r"(?:first|last|past|opening)\s+(five|5|ten|10|fifteen|15)\s+minutes",
                "hu": r"(?:első|elmúlt|utolsó)\s+(öt|5|tíz|10|tizenöt|15)\s+perc"}
NUMBER_WORD = {"five": 5, "ten": 10, "fifteen": 15, "öt": 5, "tíz": 10, "tizenöt": 15}


def check_window_wording(text, lang, item):
    """'the first five minutes' at 2': a time window cannot be longer than the minutes played."""
    for m in re.finditer(WINDOW_WORDS[lang], text.lower()):
        n = NUMBER_WORD.get(m.group(1), int(m.group(1)) if m.group(1).isdigit() else 0)
        if n > item["minute"] + 1:
            return [f"'{m.group(0)}' at {item['minute']}': only {item['minute']} minutes have been played"]
    return []


def check_pressing_average(text, lang, item):
    """A pressing surge: the match average per 5 minutes must be called an average, not the current rate."""
    if item["kind"] != "moment" or item["moment"]["type"] != "pressing_surge":
        return []
    avg = item["moment"]["fact"].get("match_rate_per_5min")
    if avg is None:
        return []
    forms = {f"{avg:g}", f"{avg:g}".replace(".", ",")}
    for sent in CLAUSE_END_RE.split(text):
        if any(re.search(r"(?<![\d.,])" + re.escape(f) + r"(?![\d])", sent) for f in forms):
            if not re.search(r"average|átlag", sent.lower()):
                return [f"{avg:g} is the team's match average per 5 minutes, not the current rate: say 'average'"]
            if re.search(r"(?:last|past|previous) (?:15|fifteen) minutes|(?:utolsó|elmúlt) (?:15|tizenöt) perc", sent.lower()):
                return [f"{avg:g} is the average per 5 minutes over the whole match so far, not over the last 15 minutes"]
    return []


def check_focus_percentages(text, lang, store, pid, t_ms, other_numbers=()):
    """A focus player's category scores are not percentages; a percentage 'under pressure' must be his under-pressure accuracy."""
    problems = []
    prof = store.profiles.get(pid) or {}
    cats = [float(v) for k, v in prof.items() if k.startswith("cat_") and v not in ("", None)]
    live = (store.player_live(pid, t_ms) or {}).get("raw_per90", {})
    live_pcts = [float(v) for k, v in live.items() if k.endswith("_pct") and v is not None]
    for m in re.finditer(r"(?<![\d.,])(\d{1,3}(?:[.,]\d)?)\s*(%|percent|százalék)", text):
        v = float(m.group(1).replace(",", "."))
        if any(abs(v - c) <= 0.05 for c in cats) and not any(abs(v - p) <= 0.6 for p in live_pcts) and not any(abs(v - a) <= 0.6 for a in other_numbers):
            problems.append(f"{v:g} is a category score (0-100), not a percentage")
            break
    up = live.get("pass_accuracy_under_pressure_pct")
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d)?)\s*%[^.;]{0,40}?(under pressure|nyomás alatt)", text):
        v = float(m.group(1).replace(",", "."))
        gap = text[m.end(1):m.start(2)].lower()
        if re.search(r"\band\b|\bés\b|,|\d|perfect|tökéletes|while|míg|overall|összes", gap):
            continue   # another statistic sits between the number and 'under pressure'
        if up is not None and abs(v - up) > 1.0:
            problems.append(f"{v:g}% is not his pass accuracy under pressure ({up:g}%)")
            break
    return problems


# --------------------------------------------------------------- recap wording against the facts
LATE_WORDS = {"en": r"\blate\b|dying minutes|last-gasp|at the death|closing minutes",
              "hu": r"késői|kései|a hajrában|az utolsó percekben|a lefújás előtt|hajrával|az utolsó pillanat"}
GOAL_WORDS = {"en": r"penalt|goal|winner|strike|header|equali|brace|comeback", "hu": r"büntet|tizenegyes|gól|találat|fejes|egyenlít|dupl|fordít"}


def _lead_changes(goals):
    changes, leader = 0, 0
    for g in goals:
        a, b = (int(x) for x in g["fact"]["score"].split("-"))
        now = (a > b) - (a < b)
        if now and leader and now != leader:
            changes += 1
        if now:
            leader = now
    return changes


def check_recap_wording(text, lang, facts, store=None):
    problems = []
    goals = facts.get("goals", [])
    pens = [g for g in goals if g["fact"].get("penalty")]
    kpi_keys = {k for r in facts.get("team_kpis", []) for k in r}
    xg = sorted(float(r["xg"]) for r in facts.get("team_kpis", []) if r.get("xg") not in (None, ""))
    for sent in SENT_RE.split(text):
        low = sent.lower()
        first_half = re.search(r"first half|first-half|before the break|before half-time|half-time|szünet|első félidő|félidő végén|45\+", low)
        if re.search(LATE_WORDS[lang], low) and re.search(GOAL_WORDS[lang], low) and not first_half:
            mins = [int(a) + int(b or 0) for a, b in re.findall(r"(\d{1,3})(?:\+(\d{1,2}))?(?:'|’|\. perc|th minute)", sent)]
            if not mins:
                if re.search(r"penalt|büntet|tizenegyes", low) and pens:
                    mins = [int(g["fact"].get("minute") or 0) or int(re.match(r"\d+", g["clock"]).group(0)) for g in pens]
                elif re.search(r"winner|győztes|brace|comeback|turned|dupl|fordít", low) and goals:
                    mins = [int(re.match(r"\d+", goals[-1]["clock"]).group(0))]
            if mins and max(mins) < 75:
                problems.append(f"'late' for a goal in minute {max(mins)}: late is only after the 75th minute")
        if re.search(LATE_WORDS[lang], low) and re.search(r"bajnoki cím|címet|előrelép|title|crown", low) and not first_half and goals:
            win_min = int(re.match(r"\d+", goals[-1]["clock"]).group(0))
            if win_min < 75:
                problems.append(f"the title was decided by the goal in minute {win_min}, not in the closing minutes")
        if re.search(r"[a-záéíóöőúüű]+-négyes\w*|\b(?:league|cup) of the (?:north|south|east|west)", low):
            problems.append("the tournament has no name in the facts: write 'a torna' / 'the tournament'")
        if re.search(r"\blate (?:\d-\d )?(?:win|victory|winner)|késői (?:győzelem|győztes)", low):
            win_min = int(re.match(r"\d+", goals[-1]["clock"]).group(0)) if goals else 0
            if win_min < 75:
                problems.append(f"'late win': the winning goal came in minute {win_min}")
        if re.search(r"\btackl|szerelés", low) and not any("tackl" in k for k in kpi_keys):
            problems.append("tackles are not in the facts (the team KPIs give pressures and duels)")
        # "a close-range header (xG 0.65) to level the score" says nothing about the xG totals being close
        low_xg = re.sub(r"close[- ]range|from close|close to (?:the )?goal|level(?:l?ing|l?ed|s)? (?:the )?(?:score|match|it|things)|draws? level", " ", low)
        if "xg" in low_xg and re.search(r"\bclose\b|\btight\b|evenly|\blevel\b|szoros|kiegyenlített|hasonló", low_xg) and len(xg) == 2 and xg[0] and xg[1] / xg[0] >= 1.5:
            problems.append(f"xG {xg[1]:.2f} vs {xg[0]:.2f} is not close")
        if re.search(r"lead changed hands (?:several|many|multiple|\d+) times|swapped the lead several|többször (?:is )?cseréltek vezetést|többször változott a vezetés|többszörös vezetés", low) and _lead_changes(goals) < 2:
            problems.append(f"the lead changed hands {_lead_changes(goals)} time(s) in this match, not several times")
    problems += check_recap_leads(text, lang, facts) + check_recap_counts(text, lang, facts, store) + check_recap_dominance(text, lang, facts)
    for m in re.finditer(r"(\d+[.,]\d+)-sz[oeö]r[oeö]s", text):
        v = float(m.group(1).replace(",", "."))
        if any(abs(v - x) <= 0.01 for x in xg):
            problems.append(f"'{m.group(0)}': {m.group(1)} is the xG itself, not a ratio" + (f" (the ratio is {xg[1] / xg[0]:.2f})" if len(xg) == 2 and xg[0] else ""))
    return sorted(set(problems + check_garbled(text, lang) + check_not_in_facts(text, lang) + check_units(text, lang)
                      + check_recap_duels(text, lang, facts) + check_recap_shots(text, lang, facts)))


AGAIN_LEAD = {"en": r"(?:regain\w*|retook|retake\w*|re-took|restor\w*)\s+(?:the\s+|their\s+)?lead|back in front|ahead again|again (?:took|takes) the lead",
              "hu": r"vissza(?:vette|veszi|szerezte|állította|hozta)\w*\s+(?:a\s+)?(?:\w+\s+)?vezetés\w*|(?:újra|ismét) (?:a\s+)?(?:\w+\s+){0,2}?vezet\w*|(?:újra|ismét) vezetéshez"}
EXTEND_LEAD = {"en": r"extend\w*\s+(?:the\s+|their\s+)?lead|increas\w*\s+(?:the\s+|their\s+)?lead|doubl\w*\s+(?:the\s+|their\s+)?lead",
               "hu": r"növel\w*\s+(?:az?\s+)?(?:\w+\s+)?előny\w*|megdupláz\w* (?:az?\s+)?előny\w*"}


def _goals_in_sentence(sent, goals):
    """The goals a sentence is about: by its minute, else by the scorer (a penalty or a 'second goal' picks the right one)."""
    mins = [int(a) + int(b or 0) for a, b in re.findall(r"(\d{1,3})(?:\+(\d{1,2}))?(?:'|’|\. perc| ?th minute|-?(?:ik|ös|es|as|ös) perc)", sent)]
    by_min = [g for g in goals if sum(int(x) for x in re.findall(r"\d+", g["clock"])) in mins]
    if by_min:
        return by_min
    cands = [g for g in goals if g["fact"].get("scorer") and g["fact"]["scorer"].split()[-1] in sent]
    low = sent.lower()
    if len(cands) > 1 and re.search(r"penalt|büntet|tizenegyes", low):
        cands = [g for g in cands if g["fact"].get("penalty")] or cands
    elif len(cands) > 1 and re.search(r"brace|second|dupl|második", low):
        cands = cands[1:]
    return cands


def check_recap_leads(text, lang, facts):
    """'Andreou retook the lead at 27'' when Vallora had never led; 'növelte előnyét' for a goal that only takes the lead."""
    goals = facts.get("goals", [])
    home, away = (facts.get("teams") or [None, None])[:2]
    led, led_before = set(), {}
    for g in goals:   # did the scoring team lead at any moment before this goal?
        team = g["fact"].get("scoring_team") or g.get("team")
        led_before[g["clock"]] = team in led
        a, b = (int(x) for x in g["fact"]["score"].split("-"))
        if a > b:
            led.add(home)
        elif b > a:
            led.add(away)
    problems = []
    for sent in SENT_RE.split(text):
        low = sent.lower()
        if re.search(AGAIN_LEAD[lang], low):
            gs = _goals_in_sentence(sent, goals)
            if gs and all(not led_before.get(g["clock"]) and g["fact"].get("goal_effect") == "takes the lead" for g in gs):
                problems.append(f"{gs[0]['fact']['scoring_team']} had not led before {gs[0]['clock']}: not 'again' / 'retook the lead'")
        if re.search(EXTEND_LEAD[lang], low):
            gs = _goals_in_sentence(sent, goals)
            if gs and all(g["fact"].get("goal_effect") != "extends the lead" for g in gs):
                problems.append(f"the goal at {' / '.join(g['clock'] for g in gs)} {gs[0]['fact'].get('goal_effect')} ({gs[0]['fact']['score']}): it does not extend a lead")
    return problems


KPI_WORDS = {"touches_in_box": r"touch\w*|érint\w*", "pressures": r"pressures?|press\w* actions|letámad\w*|nyomás\w*",
             "progressive_passes": r"progressive pass\w*|előrevivő passz\w*", "key_passes": r"key pass\w*|kulcspassz\w*",
             "defensive_duels_won": r"defensive duels?|védekező párharc\w*|szerelés\w*", "aerial_duels_won": r"aerial duels?|fejpárbaj\w*|fejpárharc\w*",
             "dribbles_completed": r"dribbles?|csel\w*"}


def check_recap_counts(text, lang, facts, store=None):
    """A player's running count from a moment ('touches in the box #8 at 41'') written as his match total."""
    problems = []
    for m in (store.moments if store is not None else facts.get("top_moments", [])):
        f = m.get("fact") or {}
        if m.get("type") != "player_threshold" or not f.get("player") or f.get("count") is None:
            continue
        sur, n = f["player"].split()[-1], int(f["count"])
        nums = [str(n)] + list({8: ("eight", "nyolc"), 10: ("ten", "tíz"), 20: ("twenty", "húsz"), 5: ("five", "öt")}.get(n, ()))
        kpi = KPI_WORDS.get(f.get("kpi"), (f.get("kpi") or "x").replace("_", " "))
        near = re.compile(r"(?<![\w.,])(?:" + "|".join(nums) + r")(?:-?(?:szor|szer|ször|t|et|es|as|ös))?\s+(?:[\w-]+\s+){0,2}?(?:" + kpi + ")", re.I)
        for sent in SENT_RE.split(text):
            if sur in sent and near.search(sent) and m["clock"] not in sent \
                    and not re.search(r"\b(?:by|until|up to|at)\s+(?:the\s+)?\d{1,3}|\d{1,3}\.\s*perc(?:ig|re)|-?ig\b", sent):
                problems.append(f"{f['player']}'s {n} ({f.get('kpi', '').replace('_', ' ')}) is his count at {m['clock']}, not his match total: say 'by {m['clock']}'")
                break
    return problems


DOMINANCE_RX = None


def check_recap_dominance(text, lang, facts, rules=None):
    """Control / dominance words about a team in a recap need that team's match field tilt of 58 % or more (possession
    alone is not enough; the same patterns as the live claim rule)."""
    global DOMINANCE_RX
    if DOMINANCE_RX is None:
        r = next(x for x in (rules or load_rules())["rules"] if x["id"] == "dominance")
        DOMINANCE_RX = {l: ([re.compile(p[3:]) if p.startswith("re:") else re.compile(re.escape(p.lower())) for p in r["patterns"][l]], r.get("exclude", {}).get(l, []))
                        for l in ("en", "hu")}
    pats, excl = DOMINANCE_RX[lang]
    tilt = {r.get("team_id"): float(r["field_tilt_pct"]) for r in facts.get("team_kpis", []) if r.get("field_tilt_pct") not in (None, "")}
    names = dict(zip(facts.get("match_team_ids", []), facts.get("teams", [])))
    if not tilt:
        return []
    low = text.lower()
    for x in excl:
        low = re.sub(x, lambda m: " " * len(m.group(0)), low)
    hits = []
    for rx in pats:
        for m in rx.finditer(low):
            a = max(low.rfind(c, 0, m.start()) for c in ".!?;\n") + 1
            seg = low[a:m.start()]
            team = None
            for tid, nm in names.items():
                key = nm.replace(" U19", "").split()[0].lower()
                pos = seg.rfind(key)
                if pos >= 0 and (team is None or pos > team[1]):
                    team = (tid, pos)
            tids = [team[0]] if team else list(tilt)
            if not any(tilt.get(t, 0) >= 58 for t in tids) and m.group(0).strip() not in hits:
                hits.append(m.group(0).strip())
    if not hits:
        return []
    top = ", ".join(f"{names.get(t, t).replace(' U19', '')} {v:.1f} %" for t, v in tilt.items())
    return [f"control / dominance words without the field tilt to back them ({'; '.join(repr(h) for h in hits[:6])}): the match field tilt was {top}; "
            "control / dominance words need 58 % or more (possession alone is not enough): describe what the numbers show instead"]


DUEL_MORE = {"en": r"(?:more|higher|greater|better)[^.;]{0,40}duels? won|won more duels|more duels|(?:higher|better) duel",
             "hu": r"több párharcot nyer\w*|párharc\w*[^.;]{0,30}(?:jobb|több|fölény)\w*"}
DUEL_EVEN = {"en": r"matched in duels|(?:equal|even|level|matched)[^.;]{0,20}duels? won|duels? won[^.;]{0,20}(?:equal|even|level|matched)",
             "hu": r"(?:kiegyenlített|egyforma|azonos)[^.;]{0,20}párharc\w* (?:nyer|siker)|párharc\w* (?:nyer|siker)\w*[^.;]{0,20}(?:kiegyenlített|egyforma|azonos)"}


def check_recap_duels(text, lang, facts):
    """'Both teams matched in duels won' / 'Northbridge's higher number of duels won' against duels_won_pct of the team KPIs."""
    rows = {r["team_id"]: float(r["duels_won_pct"]) for r in facts.get("team_kpis", []) if r.get("duels_won_pct") not in (None, "")}
    names = {tid: n for tid, n in zip(facts.get("match_team_ids", []), facts.get("teams", []))}
    if len(rows) != 2:
        return []
    problems = []
    (a, pa), (b, pb) = sorted(rows.items(), key=lambda x: x[1])
    for sent in SENT_RE.split(text):
        low = sent.lower()
        if re.search(DUEL_EVEN[lang], low) and pb - pa >= 5:
            problems.append(f"duels won are not even: {pb:.1f}% vs {pa:.1f}%")
        m = re.search(DUEL_MORE[lang], low)
        if m:
            loser = (names.get(a) or "").replace(" U19", "").split()[0].lower() if names.get(a) else ""
            before = low[:m.start()]
            winner = (names.get(b) or "").replace(" U19", "").split()[0].lower() if names.get(b) else ""
            if loser and loser in before and (not winner or before.rfind(loser) > before.rfind(winner)):
                problems.append(f"{names[a]} won fewer duels ({pa:.1f}% vs {pb:.1f}%)")
    return problems


OUTSIDE_BOX = {"en": r"outside the (?:box|area|penalty area)|long[- ]range|from range", "hu": r"tizenhatoson kívül\w*|büntetőterületen kívül\w*|nagy távolságból"}
BOX_DEPTH_M = 16.5


def check_recap_shots(text, lang, facts):
    """'A powerful header' in a recap for a goal whose shot speed was 30 km/h, 'from outside the box' for a goal from
    10.6 m (goals carry shot_speed_kmh and shot_distance_m)."""
    problems = []
    for g in facts.get("goals", []):
        dist, scorer = g.get("shot_distance_m"), g["fact"].get("scorer")
        if dist is not None and dist < BOX_DEPTH_M and scorer and all((x.get("shot_distance_m") or 0) < BOX_DEPTH_M for x in facts["goals"] if x["fact"].get("scorer") == scorer):
            for sent in SENT_RE.split(text):
                m = re.search(OUTSIDE_BOX[lang], sent.lower())
                if scorer.split()[-1] in sent and m:
                    problems.append(f"{scorer}'s goal ({g['clock']}) was from {dist:.1f} m, inside the box: not '{m.group(0)}'")
    for g in facts.get("goals", []):
        speed, scorer = g.get("shot_speed_kmh"), g["fact"].get("scorer")
        if speed is None or speed >= POWER_MIN_KMH or not scorer:
            continue
        sur = scorer.split()[-1]
        if any(speed2 is not None and speed2 >= POWER_MIN_KMH for speed2 in (x.get("shot_speed_kmh") for x in facts["goals"] if x["fact"].get("scorer") == scorer)):
            continue   # the same player also scored a fast goal: the sentence may mean that one
        for sent in SENT_RE.split(text):
            m = re.search(r"(?<![a-záéíóöőúüű])" + POWER_WORDS[lang], sent.lower())
            if sur in sent and m:
                problems.append(f"{scorer}'s goal ({g['clock']}) was {speed:.0f} km/h: not '{m.group(0)}'")
    return sorted(set(problems))


def check_scouting(text, lang, store):
    """Scouting notes: each player's section names the player's own position ('támadó középpályásként' for a
    defensive midfielder is wrong). 'Szerelés' for the defensive-duel category is accepted (a defensive duel is a tackle attempt)."""
    problems = []
    name_to_pid = {p["name"]: pid for pid, p in store.players.items()}
    as_word = {"en": r"\bas an? ({})\b", "hu": r"({})ként"}[lang]
    words = sorted((w for w, _ in POSITION_WORDS[lang]), key=len, reverse=True)
    for sec in re.split(r"\n(?=#|\*\*)", text):
        first = min(((sec.find(n), pid) for n, pid in name_to_pid.items() if n in sec), default=None)
        if not first or first[0] < 0:
            continue
        pid = first[1]
        for m in re.finditer(as_word.format("|".join(re.escape(w) for w in words)), sec.lower()):
            codes = dict(POSITION_WORDS[lang])[m.group(1)]
            if not (codes & player_codes(pid, store)) and not ({"FB"} & codes and player_codes(pid, store) & {"LB", "RB", "LWB", "RWB"}):
                problems.append(f"{store.players[pid]['name']} is a {position_label(pid, store, 'en')} in the data, not a '{m.group(1)}'")
        if not sec.lstrip().startswith("|"):
            problems += check_category_praise(sec, lang, store.profiles_final.get(pid), store.players[pid]["name"])
    return problems


STOCK_TRIM = {"en": [(r"\bnarrow (\d)-(\d) lead", r"\1-\2 lead"), (r"\b(?:tight|intense|thrilling|nail-biting) title decider", "title decider"),
                     (r"\bnail-biting ", ""), (r"\bpulsating ", "")],
              "hu": [(r"\b(?:szoros|kiélezett) címdöntő", "címdöntő"), (r"\blélegzetelállító ", "")]}


def trim_stock_phrases(text_obj, lang):
    """Remove the known stock phrases from a narrator text (deterministic, recorded); returns (new text, list of trims)."""
    out, trims = dict(text_obj), []
    for k in ("overlay", "commentary", "detail"):
        s = out.get(k)
        if not isinstance(s, str):
            continue
        for pat, rep_ in STOCK_TRIM[lang]:
            s2 = re.sub(pat, rep_, s, flags=re.I)
            if s2 != s:
                trims.append(re.search(pat, s, flags=re.I).group(0))
                s = s2
        out[k] = s
    return out, trims
