#!/usr/bin/env python3
"""Free test cases for the checker fixes of 26 Oct (no Azure, no LLM, no cost).

    python3 tests/test_checks.py        # standard library only; the pipeline case (a2) also needs agent-framework

Each case names the fix it covers:
 a) the Verifier may never add or swap a player name; the focus player must be named
 b) a focus player who does not play in this match; positions must match the data
 c) recap numbers: points, margins, 'level on points', shots on target, xG ratios, scores, positions
 d) no ranking claim about a low-data player
 e) no invented minutes ('95+', minutes after the clock)
 f) false positives: 'percentile', 'kiegyenlített' (balanced), '16-os' (the penalty box)
 g-m) the fixes after the hand review of the night of 26-27 Oct (README, "Checker fixes")
 n) who is on the pitch: a focus player on the bench or substituted must be described as such (line-ups, no future facts)
 o) control / dominance words need the claimed team's field tilt (possession alone is not enough)
 p) wording found in the hand review of 27 Oct: PPDA explained, pressing intensity and effectiveness, 'slight' momentum,
    Hungarian minutes, English sentences in Hungarian, garbled terms, category praise below 75
 q) the comparison scores with exactly the pre-check's text checks
 r) false positives found in the day's re-run p1
 s) errors found in the hand review after re-runs p1-p3
 t) recaps: team names, 'retook the lead', 'extended the lead', an xG written as a ratio, a running count as a match total,
    control / dominance words with the match field tilt; a Hungarian ordinal does not end a sentence
 u) the targeted text fixes of 27 Oct (config/targeted_edits.json): every edit applied, every edited text passes the
    full rule set; 'their control' is a control word
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import verify as V              # noqa: E402
from agents.facts import FactStore          # noqa: E402
from agents.selection import load_config    # noqa: E402

STORE = FactStore("M12")
CFG = load_config()
RESULTS = []


def item_at(minute, kind="state", mtype=None):
    """A narration item of the committed run near this minute (for the clock / goal context)."""
    import run_agents
    items = run_agents.build_items(STORE, CFG)
    for it in items:
        if it["kind"] == kind and it["minute"] == minute and (mtype is None or it["moment"]["type"] == mtype):
            return it
    raise LookupError(minute)


def case(fix, name, got, want):
    ok = got == want
    RESULTS.append(dict(fix=fix, case=name, expected=want, got=got, passed=ok))


def has(problems, word):
    return any(word in p for p in problems)


def recap_facts():
    import run_agents  # noqa: F401  (recap facts are built in run_agents.recap_and_scouting; rebuilt here from the store)
    tc = STORE.tournament
    goals = [dict(clock=m["clock"], fact=m["fact"]) for m in STORE.moments if m["type"] == "goal"]   # same shape as run_agents.recap_and_scouting
    return dict(tournament=dict(standings_before=[dict(team=r["team"], points=r["points"]) for r in tc["standings_before"]],
                                final_standings=[dict(team=r["team"], points=r["points"]) for r in tc["standings_after"]]),
                goals=goals, team_kpis=[r for r in STORE.team_kpis if r["match_id"] == STORE.match_id])


def main():
    st30 = item_at(30)
    st90 = item_at(90, kind="moment")
    goal2 = item_at(2, kind="moment", mtype="goal")
    # a) name changes and the focus subject
    case("a", "Verifier swaps Petrovic for Vermeulen", V.check_name_changes("Ilyes Petrovic drives Northbridge", "Ilyes Vermeulen drives Northbridge", STORE), ["Vermeulen"])
    case("a", "Verifier only removes a name", V.check_name_changes("Petrovic and Vermeulen press", "Petrovic presses", STORE), [])
    case("a", "focus overlay without the focus player", has(V.check_focus_subject("Northbridge press high at 30'", "T1P09", STORE, "en"), "focus player"), True)
    case("a", "focus overlay with the surname", V.check_focus_subject("Petrovic presses high at 30'", "T1P09", STORE, "en"), [])
    focus_is_subject = V.focus_is_subject
    goal27 = item_at(27, kind="moment", mtype="goal")
    case("a", "a goal by Andreou in Novak's focus feed need not name Novak", focus_is_subject(goal27, "T2P12", STORE), False)
    case("a", "a state card in Novak's focus feed must name Novak", focus_is_subject(st30, "T2P12", STORE), True)
    # b) a focus player who does not play in M12; positions from the data
    case("b", "Ferris (T3) tied to the match clock", has(V.check_absent_player("At 30', Ferris drives Vallora's pressure.", "en", st30, STORE, "T3P20"), "does not play"), True)
    case("b", "Ferris profile text that says he is not in this match", V.check_absent_player(
        "Abdoulaye Ferris is not in this match; his tournament profile shows strong chance creation.", "en", st30, STORE, "T3P20"), [])
    case("b", "'does not feature in this ... vs ... match' is understood", V.check_absent_player(
        "Abdoulaye Ferris is a striker with 222.8 tournament minutes. He does not feature in the Vallora United U19 vs Northbridge FC U19 match.", "en", st30, STORE, "T3P20"), [])
    case("b", "'not involved in this Vallora vs Northbridge match' is understood", V.check_absent_player(
        "Though he is not involved in this Vallora United U19 vs Northbridge FC U19 match, Blanchard has 217 tournament minutes.", "en", st30, STORE, "T4P11"), [])
    case("b", "'He does not participate in this match' is understood", V.check_absent_player(
        "Abdoulaye Ferris has 222.8 tournament minutes. He does not participate in this match.", "en", st30, STORE, "T3P20"), [])
    case("b", "naming the absent player's own club does not crash the claim check", isinstance(V.check_claims(
        "Szymon Blanchard a Kalmarsund BK U19 jobbhátvédje, nem játszik ezen a mérkőzésen; uralja a pályát.", "hu", st30, STORE, V.load_rules(), player_id="T4P11"), list), True)
    case("b", "Petrovic (T1) plays: no absent-player rule", V.check_absent_player("At 30', Petrovic presses.", "en", st30, STORE, "T1P09"), [])
    case("b", "Ferris called a defender (he is a striker)", has(V.check_positions("Abdoulaye Ferris: erős védő, közepes passzokkal", "hu", STORE), "striker"), True)
    case("b", "Blanchard called a left-back (right-back)", has(V.check_positions("Szymon Blanchard egy fiatal, 15 éves balhátvéd", "hu", STORE), "right-back"), True)
    case("b", "Blanchard called a full-back (correct)", V.check_positions("Szymon Blanchard, a 15-year-old fullback, offers solid value.", "en", STORE), [])
    case("b", "Nagy called a striker (winger)", has(V.check_positions("a milestone first tournament goal for Alvaro Nagy, the young striker.", "en", STORE), "winger"), True)
    case("b", "'Nagy helyzet ... csatár' (nagy = big) is not about Alvaro Nagy", V.check_positions("Nagy helyzet maradt ki, a csatár lövése mellé ment.", "hu", STORE), [])
    case("a", "'Nagy helyzet' in a Verifier repair is not a new name", V.check_name_changes("Winther lövése mellé ment.", "Nagy helyzet: Winther lövése mellé ment.", STORE), [])
    case("b", "Petrovic as left-back: he played LB in M12 (primary RB)", V.check_positions("Ilyes Petrovic, balhátvéd, még nincs élő adat", "hu", STORE), [])
    case("b", "Winther as striker: secondary ST, played ST in M12", V.check_positions("Winther, a ranked striker with medium reliability", "en", STORE), [])
    case("b", "'védőpárharc' is not a position", V.check_positions("Ferris erős a védőpárharcokban.", "hu", STORE), [])
    it75 = next(it for it in __import__("run_agents").build_items(STORE, CFG) if it["item_id"] == "M12-IT-042")
    case("b", "Petrovic '75 perc játék alatt' at 75' (on the pitch for 21 minutes)", has(V.check_player_minutes("Ilyes Petrovic 75 perc játék alatt 5 passzt adott", "hu", it75, STORE, "T1P09"), "has played"), True)
    case("b", "Petrovic 'just over 20 minutes' at 75' (correct)", V.check_player_minutes("At 75', Ilyes Petrovic has played just over 20 minutes", "en", it75, STORE, "T1P09"), [])
    # c) recap numbers
    rf = recap_facts()
    rf_full = dict(rf)
    case("c", "'level on points before kickoff' (10 and 9)", has(V.check_recap("With both sides level on points before kickoff, this clash decided the title.", "en", rf, STORE), "level on points"), True)
    case("c", "'egy ponttal megelőzve' after the match (margin 2)", has(V.check_recap("Vallora 12 ponttal, egy ponttal megelőzve lett bajnok.", "hu", rf, STORE), "margin is 2"), True)
    case("c", "'within a point' before the match (correct)", V.check_recap("Both sides entered the match within a point of each other.", "en", rf, STORE), [])
    case("c", "'tripling' the xG (2.35 vs 1.27)", has(V.check_recap("Vallora took 16 shots, tripling their xG at 2.35 compared to 1.27.", "en", rf, STORE), "three times"), True)
    case("c", "'16 kapura lövés' (shots on target are not in the facts)", has(V.check_recap("Vallora 16 kapura lövéssel dolgozott.", "hu", rf, STORE), "on target"), True)
    case("c", "'21 százalékkal több lövés' (16 vs 8 is 100 % more)", has(V.check_recap("Vallora United 21 százalékkal több lövést vezetett.", "hu", rf, STORE), "difference is 100"), True)
    case("c", "'4 % more passes' (328 vs 316, correct)", V.check_recap("Vallora made 4% more passes.", "en", rf, STORE), [])
    case("c", "final standings 12 and 10 points (correct)", V.check_recap("1. Vallora United U19 – 12 points. 2. Northbridge FC U19 – 10 points.", "en", rf, STORE), [])
    case("c", "a score that never happened (3-1)", has(V.check_recap("Vallora led 3-1 at one point.", "en", rf, STORE), "never happened"), True)
    # d) ranking claims about a low-data player (Petrovic: 172.5 tournament minutes before M12)
    case("d", "'top FB' about Petrovic (low data)", has(V.check_ranking_low_data("Ilyes Petrovic strong at 75', top FB with high pressing work", "en", STORE, CFG, "T1P09"), "low data"), True)
    case("d", "'kiemelkedő' about Novak (low data) in a non-focus text", has(V.check_ranking_low_data("Dominik Novak kiemelkedő passzokkal segít.", "hu", STORE, CFG), "low data"), True)
    case("d", "'top pressing and finishing skills' about Petrovic (low data)", has(V.check_ranking_low_data("Ilyes Petrovic: low data reliability but top pressing and finishing skills", "en", STORE, CFG, "T1P09"), "low data"), True)
    case("d", "'top of the table' without a low-data player: allowed", V.check_ranking_low_data("Northbridge stay top of the table.", "en", STORE, CFG), [])
    case("d", "'top ... Alessandro Novak' is not about Dominik Novak (low data)", V.check_ranking_low_data("Top defensive players include Alessandro Novak for Vallora.", "en", STORE, CFG), [])
    case("d", "'his top strengths include' (his own best traits) about Petrovic: allowed", V.check_ranking_low_data("His top strengths include goal contribution and pressing.", "en", STORE, CFG, "T1P09"), [])
    case("d", "no ranking word: allowed", V.check_ranking_low_data("Ilyes Petrovic presses well; low data, 172 minutes.", "en", STORE, CFG, "T1P09"), [])
    # e) clock
    case("e", "'95+ minutes' at 90'", has(V.check_semantics("Bence Sarr delivers 10 progressive passes in 95+ minutes", "en", st90, STORE, CFG), "not a valid minute"), True)
    case("e", "'90+2'' at 90' (later than the clock)", has(V.check_semantics("A late chance at 90+2'", "en", st90, STORE, CFG), "later than"), True)
    case("e", "'97 perc játék alatt' at 90' (95 minutes have been played, stoppage time included)", has(V.check_semantics("Bence Sarr 10 előrevivő passzt adott 97 perc játék alatt", "hu", st90, STORE, CFG), "longer than the match"), True)
    case("e", "'95 perc játék alatt' at 90' is the elapsed time (first-half stoppage included)", has(V.check_semantics("Bence Sarr 10 előrevivő passzt adott 95 perc játék alatt", "hu", st90, STORE, CFG), "longer than the match"), False)
    case("e", "'78 percentile' is not a playing time", has(V.check_semantics("strengths in defensive duels (78 percentile)", "en", st30, STORE, CFG), "longer than"), False)
    case("e", "'222.8 tournament minutes' is not a match time", has(V.check_semantics("Ferris has 222.8 tournament minutes", "en", st30, STORE, CFG), "longer than"), False)
    case("e", "'Vallora United U19's pressing' at 18' is not minute 19", has(V.check_semantics("Vallora United U19's pressing intensity stays high at 18'", "en", item_at(18, kind="moment", mtype="goal"), STORE, CFG), "later than"), False)
    case("e", "the 45+3' equaliser mentioned at 90' (earlier: fine)", has(V.check_semantics("Winther's 45+3' header still matters", "en", st90, STORE, CFG), "later than"), False)
    # f) false positives
    case("f", "'92 percentile' in English is English", has(V.check_semantics("Novak has a 92 percentile in passing", "en", st30, STORE, CFG), "not in English"), False)
    case("f", "Hungarian 'perc' in an English text is still caught", has(V.check_semantics("Novak played 30 percet today", "en", st30, STORE, CFG), "not in English"), True)
    case("f", "'kiegyenlített döntőben' (balanced) is not an equaliser", has(V.check_semantics("Byrne vezetést szerzett egy kiegyenlített döntőben.", "hu", goal2, STORE, CFG), "equaliser"), False)
    case("f", "'egy kiegyenlített, de ... mérkőzésen' is not an equaliser", has(V.check_semantics("Byrne vezetést szerzett egy kiegyenlített, de feszült mérkőzésen.", "hu", goal2, STORE, CFG), "equaliser"), False)
    case("f", "'a labdabirtoklás egyenlő' is not an equaliser", has(V.check_semantics("Byrne vezetést szerzett, a labdabirtoklás egyenlő.", "hu", goal2, STORE, CFG), "equaliser"), False)
    case("f", "a real 'egyenlített' for a lead goal is still caught", has(V.check_semantics("Byrne egyenlített a 2. percben.", "hu", goal2, STORE, CFG), "equaliser"), True)
    case("f", "'16-oson belül' is not a number", V.check_numbers("Andreou 6 érintés a 16-oson belül", {"x": 6}, 0.06, 0.6), (True, []))
    # g) wording (night of 27 Oct): stock phrases, garbled words, translated team names, windows, averages, percentages, recap wording
    case("g", "'tight title decider' is a stock phrase", has(V.check_stock_phrases("Vallora lead in this tight title decider", "en"), "stock phrase"), True)
    case("g", "'title decider' alone is fine", V.check_stock_phrases("Vallora lead the title decider 2-1", "en"), [])
    case("g", "63': 'presztízspresszió' is not a Hungarian football term", has(V.check_garbled("Alvaro De Vries 20 presztízspresszió 63'-nál", "hu"), "not a Hungarian"), True)
    case("g", "'északi vezetés' translates the team name", has(V.check_garbled("Elemzés: északi vezetés, Vallora területfölény", "hu"), "translate"), True)
    case("g", "normal Hungarian ('letámadás', 'területi fölény') passes", V.check_garbled("Northbridge letámadása erős, a területi fölény a Valloráé.", "hu"), [])
    goal2_item = goal2
    case("g", "'the first five minutes' at 2'", has(V.check_window_wording("holding full field tilt in the first five minutes", "en", goal2_item), "only 2 minutes"), True)
    case("g", "'the last 15 minutes' at 30' is fine", V.check_window_wording("Vallora pressed more in the last 15 minutes", "en", st30), [])
    surge59 = next(it for it in __import__("run_agents").build_items(STORE, CFG) if it["kind"] == "moment" and it["moment"]["type"] == "pressing_surge" and it["minute"] == 59)
    case("g", "59': '9.2 per 5 minutes' as the current rate", has(V.check_pressing_average("15 attempts in the last 5 minutes with a pressing rate of 9.2 per 5 minutes", "en", surge59), "average"), True)
    case("g", "59': '9.2 on average' is fine", V.check_pressing_average("15 pressures in the last 5 minutes, against a match average of 9.2", "en", surge59), [])
    it35 = next(it for it in __import__("run_agents").build_items(STORE, CFG) if it["item_id"] == "M12-IT-046")
    case("g", "Novak '93% pass accuracy under pressure' (93 % overall, 100 % under pressure)", has(V.check_focus_percentages("Novak maintains 93% pass accuracy under pressure", "en", STORE, "T2P12", it35["t_ms"]), "under pressure"), True)
    case("g", "Petrovic '78.4%' offensive duels (a category score)", has(V.check_focus_percentages("an offensive duel success of 78.4%", "en", STORE, "T1P09", it75["t_ms"]), "category score"), True)
    st_at = STORE.state_at_ms(it75["t_ms"]); team_nums = V.allowed_numbers(dict(state=st_at))
    case("g", "team possession 48 % in a Petrovic focus text is not a category score", V.check_focus_percentages(
        "Vallora United 0–1 Northbridge FC · possession 48%", "en", STORE, "T1P09", it75["t_ms"], {48.0}), [])
    case("d", "'progressive passes #10' is not '#1'", V.check_ranking_low_data("Dominik Novak: progressive passes #10, 35'", "en", STORE, CFG, "T2P12"), [])
    case("g", "recap: 'late second-half penalty' at 49'", has(V.check_recap_wording("Vallora's late second-half penalty sealed the triumph.", "en", rf_full), "late"), True)
    case("g", "recap: 'late first-half equaliser' (45+3') is fine", V.check_recap_wording("Winther's late first-half equaliser kept Northbridge alive.", "en", rf_full), [])
    case("g", "recap: 'Szerelések száma' (pressures are not tackles)", has(V.check_recap_wording("| Szerelések száma | 160 | 189 |", "hu", rf_full), "tackles"), True)
    case("g", "recap: 'xG alapján is szoros' (2.35 vs 1.27)", has(V.check_recap_wording("A várható gólértékek (xG) alapján is szoros volt a mérkőzés.", "hu", rf_full), "not close"), True)
    case("g", "recap: 'többször cseréltek vezetést' (once)", has(V.check_recap_wording("A szünet előtt többször is cseréltek vezetést a csapatok.", "hu", rf_full), "1 time"), True)
    # h) after the night run's rejections: false positives and stock-phrase trimming
    rules = V.load_rules()
    case("h", "'keeping the title race wide open' is not a chaos claim", [c for c in V.check_claims("Nagy levels it, keeping the title race wide open.", "en", st30, STORE, rules) if c["rule"] == "chaos"], [])
    case("h", "'balanced between control and chaos' is not a chaos claim", [c for c in V.check_claims("The match remains balanced between control and chaos.", "en", st30, STORE, rules) if c["rule"] == "chaos"], [])
    case("h", "a real 'chaotic, end-to-end' claim is still checked", bool([c for c in V.check_claims("A chaotic, end-to-end game.", "en", st30, STORE, rules) if c["rule"] == "chaos"]), True)
    goal49 = item_at(49, kind="moment", mtype="goal")
    case("h", "'a területi fölénye kiegyenlített' (balanced) is not an equaliser", has(V.check_semantics("Andreou góljával 3-2-re vezet a Vallora. A mérkőzés eddigi területi fölénye kiegyenlített.", "hu", goal49, STORE, CFG), "equaliser"), False)
    case("h", "an absent player's text that says so may carry the item clock", V.check_absent_player(
        "Szymon Blanchard tournament profile at 30'. He is not involved in this match.", "en", st30, STORE, "T4P11"), [])
    tt, tr = V.trim_stock_phrases(dict(overlay="Vallora hold a narrow 3-2 lead", commentary="A 3-2 lead in this intense title decider."), "en")
    case("h", "stock phrases are trimmed: 'narrow 3-2 lead' -> '3-2 lead', 'intense title decider' -> 'title decider'",
         (tt["overlay"], tt["commentary"], len(tr)), ("Vallora hold a 3-2 lead", "A 3-2 lead in this title decider.", 2))
    # i) after the night run's hand review
    case("i", "an English overlay in the Hungarian feed (63')", has(V.check_language_fields(dict(overlay="Alvaro De Vries 20 pressures in 67.8 mins, Vallora leads 3-2", commentary="A mérkőzés kaotikus."), "hu"), "English"), True)
    case("i", "a Hungarian overlay passes the field check", V.check_language_fields(dict(overlay="Northbridge letámadása nőtt a 59. percben", commentary="Az elmúlt 5 percben 15 letámadás."), "hu"), [])
    case("i", "'Chaos uralja a játékot' (English word in Hungarian)", has(V.check_language_fields(dict(overlay="Chaos uralja a játékot", commentary=""), "hu"), "English word"), True)
    case("i", "'másodpercenként 3,13' possession changes", has(V.check_units("a labdabirtoklás változékonysága másodpercenként 3,13", "hu"), "per minute"), True)
    case("i", "'control index favoring them' (the index is not one team's)", has(V.check_units("a slight match control index favoring them at -0.282", "en"), "whole game"), True)
    case("i", "'a címvédő Northbridge' (no defending champion)", has(V.check_not_in_facts("fokozza a nyomást a címvédő Northbridge számára", "hu"), "defending"), True)
    case("i", "'az üres kapu mellé' (not in the facts)", has(V.check_not_in_facts("Winther közelről az üres kapu mellé lőtt", "hu"), "empty net"), True)
    case("i", "'labdakiért', 'góljátszás' are not Hungarian words", has(V.check_garbled("mindkét csapat küzd a labdakiért", "hu"), "not a Hungarian"), True)
    case("i", "recap: 'late 3-2 win' (winner at 49')", has(V.check_recap_wording("Vallora clinch the title with late 3-2 win over Northbridge.", "en", rf_full), "late win"), True)
    case("i", "dominance claim 'átvéve a mérkőzés irányítását' is checked", bool([c for c in V.check_claims("átvéve a mérkőzés irányítását Northbridge számára", "hu", st30, STORE, V.load_rules()) if c["rule"] == "dominance"]), True)
    # j) number parsing: negative decimals
    case("j", "'-0,027' is read as 0.027 (facts -0.027), not as 27", V.check_numbers("a kontrollindex -0,027", {"control_index": -0.027}, 0.06, 0.6), (True, []))
    case("j", "'-0.075' is read as 0.075 (facts -0.075)", V.check_numbers("control index -0.075", {"control_index": -0.075}, 0.06, 0.6), (True, []))
    case("j", "a wrong number is still caught ('2.4' when the facts say -0.075)", V.check_numbers("control index 2.4", {"control_index": -0.075}, 0.06, 0.6), (False, ["2.4"]))
    case("j", "a score '2-1' is two numbers 2 and 1", V.check_numbers("Vallora lead 2-1", {"score": {"T1": 1, "T2": 2}}, 0.06, 0.6), (True, []))
    case("i", "'passes per possession' in a Hungarian text", has(V.check_language_fields(dict(overlay="Northbridge kontrollal", commentary="a passes per possession 2,49-es értéke"), "hu"), "passz labdabirtoklásonként"), True)
    case("j", "'az irányítás és a káosz között' (between control and chaos) is not a chaos claim",
         [c for c in V.check_claims("Kiegyensúlyozott játék jellemzi a mérkőzést az irányítás és a káosz között.", "hu", st30, STORE, rules) if c["rule"] == "chaos"], [])
    # k) after the night hand review: team shares, the control index of the whole game, shot words, more garbled terms
    st56, st60 = STORE.state_at_ms(item_at(56, kind="moment")["t_ms"]), STORE.state_at_ms(item_at(60)["t_ms"])
    case("k", "56': 'Northbridge 60%-ban birtokolja a labdát' (60 % is Vallora's)", has(V.check_team_shares(
        "Northbridge FC U19 60%-ban birtokolja a labdát az utóbbi 15 percben.", "hu", st56, STORE), "Vallora's, not Northbridge's"), True)
    case("k", "56': 'Vallora United U19 has held 60% possession in the last 15 minutes' is right", V.check_team_shares(
        "Vallora United U19 has held 60% possession in the last 15 minutes while leading 3-2 against Northbridge FC U19.", "en", st56, STORE), [])
    case("k", "'A csapat … 51,2%, míg a Northbridge-é 48,7%' names no team before the first share: not checked", V.check_team_shares(
        "A csapat labdabirtoklási aránya 51,2%, míg a Northbridge FC U19-é 48,7%.", "hu", st56, STORE), [])
    case("k", "60': 'Northbridge többet tartja a labdát' (26 / 34 / 47 %)", has(V.check_team_shares(
        "Bár Northbridge többet tartja a labdát és erősen letámad, Vallora hatékony.", "hu", st60, STORE), "belongs to Vallora"), True)
    case("k", "60': 'Vallora having slightly more possession' is right", V.check_team_shares(
        "The game remains chaotic with Vallora having slightly more possession but Northbridge applying much stronger pressure.", "en", st60, STORE), [])
    for txt in ("Vallora United U19 leads 2-1 and hold a slight control advantage (-0.035 index) despite the miss.",
                "Northbridge FC U19 switches from a less structured phase to a control regime, raising their control index to 0.173.",
                "Vallora United U19 holds a slight advantage in possession and control index at -0.282.",
                "The control index favors Northbridge slightly at -0.105."):
        case("k", f"control index as one team's: '{txt[:60]}…'", has(V.check_units(txt, "en"), "whole game"), True)
    case("k", "'Northbridge FC U19 átállt a kontrollált játékra'", has(V.check_units("47'-ben Northbridge FC U19 átállt a kontrollált játékra.", "hu"), "whole game"), True)
    case("k", "'At 31' the match shifted into a chaos regime with a control index of -0.215' is fine", V.check_units(
        "At 31', the match shifted into a chaos regime with a control index of -0.215, indicating more volatility despite Vallora United U19 leading 2-1.", "en"), [])
    case("k", "'a területi fölénye kiegyenlített, a kontrollindex -0,39' (a comma between) is fine", V.check_units(
        "A mérkőzés területi fölénye kiegyenlített, a kontrollindex -0,39 értéke kaotikus játékot jelez.", "hu"), [])
    case("k", "'A passzolások száma tartósan 2,14' (passes per possession)", has(V.check_units("A passzolások száma tartósan 2,14.", "hu"), "labdabirtoklásonként"), True)
    case("k", "'a passzok száma birtoklásonként 1,43' is right", V.check_units("a passzok száma birtoklásonként 1,43-ra emelkedett", "hu"), [])
    head = dict(ball_metrics=dict(shot=dict(shot_speed_kmh=30.2, body_part="head")))
    case("k", "'a powerful header' at 30 km/h", has(V.check_shot_words("Alvaro Nagy scores a powerful header from close range.", "en", head), "30 km/h"), True)
    case("k", "'erős fejes' at 30 km/h", has(V.check_shot_words("Alvaro Nagy erős fejessel egyenlített.", "hu", head), "30 km/h"), True)
    case("k", "'erőteljesebb letámadással' in a goal text is not a shot word", V.check_shot_words("A Vallora erőteljesebb letámadással próbálkozik.", "hu", head), [])
    case("k", "'a powerful right-footed shot' at 98 km/h is fine", V.check_shot_words("Byrne scores with a powerful right-footed shot.", "en",
         dict(ball_metrics=dict(shot=dict(shot_speed_kmh=98.1)))), [])
    for w, fix in (("középmezőnyös megbízhatóság", "közepes megbízhatóság"), ("presszionál", "letámad"), ("területi mutató", "pozíciós pontszám")):
        case("k", f"garbled '{w}' gets '{fix}'", has(V.check_garbled(f"Northbridge erősen {w}.", "hu"), fix), True)
    case("k", "Hungarian decimal comma: '57.1%-kal' is shown as '57,1%-kal', the clock '45+3'' stays", V.hu_decimal_commas("57.1%-kal a 45+3'-ben, 0.455 xG"), "57,1%-kal a 45+3'-ben, 0,455 xG")
    case("k", "'control index of -0.168, slightly favoring Northbridge' (a comma between)", has(V.check_units(
        "The match remains in a chaotic phase with a control index of -0.168, slightly favoring Northbridge FC U19.", "en"), "whole game"), True)
    case("k", "'A kontrollindex -0,282, ami még mindig a Vallora United U19-nek kedvez'", has(V.check_units(
        "A kontrollindex -0,282, ami még mindig a Vallora United U19-nek kedvez.", "hu"), "whole game"), True)
    case("k", "'enyhén Northbridge FC felé billen a kontrollindex'", has(V.check_units(
        "A mérkőzés kiegyensúlyozott, enyhén Northbridge FC felé billen a kontrollindex.", "hu"), "whole game"), True)
    case("k", "'a 0,027-es kontrollindex mellett, a mezőnyfölény azonban a Vallora felé billen' (the tilt leans, not the index)", V.check_units(
        "A mérkőzés kiegyensúlyozott kontrollt mutat a 0,027-es kontrollindex mellett, a mezőnyfölény azonban a Vallora United U19 felé billen 57,6%-kal.", "hu"), [])
    case("k", "'control index of 0.02, with field tilt favoring Vallora' (the tilt favours, not the index)", V.check_units(
        "The control index of 0.02, with field tilt favoring Vallora, shows a balanced game.", "en"), [])
    case("k", "'2.27 nyomás/5 perc' (pressing intensity is per minute)", has(V.check_units("A Vallora erőteljesebb letámadással (2.27 nyomás/5 perc) próbálkozik.", "hu"), "per minute"), True)
    case("k", "'15 pressures in the last 5 minutes' (a count) is fine", V.check_units("Northbridge made 15 pressures in the last 5 minutes.", "en"), [])
    # recaps and scouting notes after the night hand review
    rk = dict(rf_full, teams=[STORE.team_name(STORE.home), STORE.team_name(STORE.away)], match_team_ids=[STORE.home, STORE.away],
              goals=[dict(g, shot_speed_kmh=30.2 if "Nagy" in str(g["fact"].get("scorer")) else 88.0) for g in rf_full["goals"]])
    case("k", "recap: 'Both teams matched in duels won' (54.0 % vs 45.5 %)", has(V.check_recap_duels("Both teams matched in duels won, but Vallora passed better.", "en", rk), "not even"), True)
    case("k", "recap: 'Northbridge's higher pressing and number of duels won'", has(V.check_recap_duels(
        "Northbridge's higher pressing and number of duels won illustrate their commitment.", "en", rk), "fewer duels"), True)
    case("k", "recap: 'Vallora won more duels' is right", V.check_recap_duels("Vallora won more duels (54.0%).", "en", rk), [])
    case("k", "recap: 'a powerful header' for Nagy's 30 km/h goal", has(V.check_recap_shots("Alvaro Nagy equalised with a powerful header at 18'.", "en", rk), "30 km/h"), True)
    case("k", "recap: 'a hajrában … Andreou duplájával megfordította' (the winner came at 49')", has(V.check_recap_wording(
        "A Vallora United a hajrában nyújtott teljesítményével, Iker Andreou duplájával megfordította a mérkőzést.", "hu", rk), "late"), True)
    case("k", "recap: 'two foots the winning margin' is garbled", has(V.check_garbled("a brace that two foots the winning margin", "en"), "two foots"), True)
    case("k", "scouting: Novak (DM) 'támadó középpályásként' in his own section", has(V.check_scouting(
        "**Dominik Novak (16, Vallora United U19, DM)**  Erősségei a passzok (89,0), ami támadó középpályásként különösen előnyös.", "hu", STORE), "defensive midfielder"), True)
    case("k", "scouting: Novak 'védekező középpályásként' is right", V.check_scouting(
        "**Dominik Novak (16, Vallora United U19, DM)**  Védekező középpályásként a passzai erősek (89,0).", "hu", STORE), [])
    case("k", "document: 'Hollomere Arénában' (the venue is Hollowmere)", has(V.check_document("A Vallora győzött a Hollomere Arénában.", "hu"), "Hollowmere"), True)
    case("k", "document: 'a alakítások' (az before a vowel)", has(V.check_document("A győzelem a alakítások miatt jött.", "hu"), "az alakítások"), True)
    case("k", "document: '(control index közel nulla)' is English in Hungarian", has(V.check_document("Újra kiegyensúlyozott (control index közel nulla).", "hu"), "control index"), True)
    case("k", "document: 'kapariórás birtoklás' is garbled", has(V.check_garbled("Vallora 51,9%-os kapariórás birtoklással játszott.", "hu"), "kapariórás"), True)
    rk2 = dict(rk, goals=[dict(g, shot_distance_m=10.6 if "Byrne" in str(g["fact"].get("scorer")) else 19.6) for g in rk["goals"]])
    case("k", "recap: Byrne's 10.6 m goal 'from outside the box'", has(V.check_recap_shots("Mathis Byrne fired a 98 km/h shot from outside the box.", "en", rk2), "inside the box"), True)
    case("k", "recap: Andreou's 19.6 m goal 'from distance' is fine", V.check_recap_shots("Iker Andreou scored with a strike from outside the box.", "en", rk2), [])
    case("k", "recap: 'a close-range header (xG 0.65) to level the score' is not 'xG close'", V.check_recap_wording(
        "At 18', Alvaro Nagy marked his first tournament goal with a close-range header (xG 0.65) to level the score.", "en", rk), [])
    case("k", "recap: 'the xG was close (2.35 vs 1.27)' is still caught", has(V.check_recap_wording("The xG was close: 2.35 vs 1.27.", "en", rk), "not close"), True)
    case("k", "recap: 'egy fantasztikus hajrával szerezte meg a bajnoki címet' (winner at 49')", has(V.check_recap_wording(
        "Vallora egy fantasztikus hajrával szerezte meg a bajnoki címet.", "hu", rk), "minute 49"), True)
    case("k", "recap: 'a Nyugat-négyes utolsó fordulója' (an invented competition name)", has(V.check_recap_wording(
        "Ez a mérkőzés döntött: a Nyugat-négyes utolsó fordulójának csúcstalálkozója volt.", "hu", rk), "no name"), True)
    case("k", "recap: 'Winther fejese az utolsó pillanatokban egyenlített (45+3')' is a first-half stoppage-time goal", V.check_recap_wording(
        "45+3' – Szymon Winther fejese az utolsó pillanatokban kiegyenlített 2-2-re.", "hu", rk), [])
    case("k", "recap: '12 ponttal végzett az élen, két ponttal megelőzve' (a total and the right margin)", V.check_recap(
        "Vallora 12 ponttal végzett az élen, két ponttal megelőzve Northbridge-ot.", "hu", rf, STORE), [])
    case("k", "recap: 'három ponttal megelőzve' after the match is still caught (margin 2)", has(V.check_recap(
        "Vallora három ponttal megelőzve lett bajnok.", "hu", rf, STORE), "margin is 2"), True)
    st38 = STORE.state_at_ms(item_at(38, kind="moment")["t_ms"])
    case("k", "38': 'Vallora … compared to Northbridge's 0.208 and had 56.1% possession' (both teams before the share): not flagged", V.check_team_shares(
        "Vallora U19 holds a cumulative xG of 0.719 compared to Northbridge's 0.208 and had 56.1% possession in the last five minutes.", "en", st38, STORE), [])
    sw = item_at(47, kind="moment", mtype="control_chaos_switch")
    try:
        from agents.pipeline import build_facts   # needs agent-framework
        f47, _ = build_facts(STORE, sw)
        case("k", "47' regime switch: the facts name no team (the regime is the whole match)", [k for k in ("team_id", "team_name", "player_name") if k in f47["moment"]], [])
    except ImportError:
        case("k", "47' regime switch facts (skipped: agent-framework not installed)", True, True)
    case("k", "47' switch from chaos to control: 'the match shifts from chaos to a control regime' is supported", [c for c in V.check_claims(
        "At 47', the match shifts from chaos to a control regime overall.", "en", sw, STORE, rules) if not c["supported"]], [])
    # n) who is on the pitch (line-ups; Petrovic comes on at 54', Novak goes off at 70')
    st15, st60, st75 = item_at(15), item_at(60), item_at(75)
    case("n", "15': Petrovic (on the bench so far) written as playing", has(V.check_pitch_status("At 15', Petrovic shows strong pressing (85.9).", "en", st15, STORE, "T1P09"), "not on the pitch"), True)
    case("n", "15': 'Petrovic, still on the bench' is right", V.check_pitch_status("Ilyes Petrovic, still on the bench, has 172.5 tournament minutes: low data.", "en", st15, STORE, "T1P09"), [])
    case("n", "15' HU: a profile text that does not say he is on the bench", has(V.check_pitch_status("Ilyes Petrovic 172,5 percet játszott a tornán.", "hu", st15, STORE, "T1P09"), "not on the pitch"), True)
    case("n", "15' HU: 'Petrovic a kispadon ül' is right", V.check_pitch_status("Ilyes Petrovic a kispadon ül, a tornán 172,5 percet játszott.", "hu", st15, STORE, "T1P09"), [])
    case("n", "60': Petrovic is on the pitch since 54': not 'still on the bench'", has(V.check_pitch_status("Petrovic, still on the bench, waits.", "en", st60, STORE, "T1P09"), "do not write"), True)
    case("n", "60': 'Petrovic came off the bench at 54'' is right", V.check_pitch_status("Petrovic came off the bench at 54' and presses high.", "en", st60, STORE, "T1P09"), [])
    case("n", "75': Novak (substituted at 70') written as playing", has(V.check_pitch_status("At 75', Novak keeps Vallora's midfield moving.", "en", st75, STORE, "T2P12"), "substituted at 70'"), True)
    case("n", "75': 'Novak, substituted at 70'' is right", V.check_pitch_status("Dominik Novak, substituted at 70', had 109.5 tournament minutes before this match.", "en", st75, STORE, "T2P12"), [])
    sub70 = next(it for it in __import__("run_agents").build_items(STORE, CFG) if it["kind"] == "moment" and it["moment"]["type"] == "substitution" and it["moment"]["fact"].get("off") == "Dominik Novak")
    case("n", "70' substitution: 'Novak off, Fernandes on' is right", V.check_pitch_status("Substitution at 70': Novak off, Fernandes on for Vallora.", "en", sub70, STORE, "T2P12"), [])
    case("n", "70' substitution HU: 'Dominik Novak le, Viggo Fernandes be' is right", V.check_pitch_status("70': Dominik Novak le, Viggo Fernandes be.", "hu", sub70, STORE, "T2P12"), [])
    case("n", "30': any text naming a player who has not come on yet must say so", has(V.check_pitch_status("At 30', Petrovic and Winther combine on the right.", "en", st30, STORE, None), "Ilyes Petrovic is not on the pitch"), True)
    case("n", "75': a player who went off may be named for what he did ('Andreou's brace')", V.check_pitch_status("Andreou's brace still decides the game.", "en", st75, STORE, None), [])
    case("n", "the facts never reveal a later substitution (no '54'' at 15')", "54" in STORE.pitch_status("T1P09", st15["t_ms"])["text"], False)
    case("n", "after 54' the facts say since when he plays", "since 54'" in STORE.pitch_status("T1P09", st60["t_ms"])["text"], True)
    try:
        from agents.pipeline import player_identity, scout_facts   # needs agent-framework
        case("n", "focus facts carry the pitch status and the rule (Petrovic at 30')", "not on the pitch" in player_identity(STORE, "T1P09", "en", st30).get("note", ""), True)
        case("n", "the Scout's facts carry it too", "not on the pitch" in scout_facts(STORE, dict(st30, focus_player="T1P09"), CFG).get("pitch_status", ""), True)
    except ImportError:
        case("n", "focus facts carry the pitch status (skipped: agent-framework not installed)", True, True)
    # o) control / dominance needs the claimed team's field tilt (15-minute window >= 58 %)
    rules = V.load_rules()
    dom = lambda text, lang, it: [c["matched"] for c in V.check_claims(text, lang, it, STORE, rules) if c["rule"] == "dominance" and not c["supported"]]
    g49, g48 = item_at(49, kind="moment", mtype="goal"), item_at(48, kind="moment", mtype="goal")
    case("o", "49': 'Vallora takes control' (field tilt 33 %, possession 60 %)", bool(dom("The title race intensifies as Vallora takes control at Hollowmere Arena.", "en", g49)), True)
    case("o", "49': 'Vallora now commands 61.7% possession' (possession alone is not enough)", bool(dom("Vallora now commands 61.7% possession in the last 5 minutes.", "en", g49)), True)
    case("o", "49': 'growing territorial dominance' for Vallora", bool(dom("Vallora United U19 lead, showing growing territorial dominance.", "en", g49)), True)
    case("o", "45+3': Northbridge (field tilt 67 %) 'átvette a mérkőzés irányítását' is backed", dom("Winther egyenlítő góljával a Northbridge átvette a mérkőzés irányítását.", "hu", g48), [])
    case("o", "49': the claim belongs to the team it is written about ('Northbridge press, while Vallora take control')", bool(dom("Northbridge press hard, while Vallora take control.", "en", g49)), True)
    case("o", "an attempt is no claim: 'their effort to regain control'", dom("Northbridge press, showing their effort to regain control.", "en", g49), [])
    case("o", "HU: 'próbálja visszavenni az irányítást' is no claim", dom("A Vallora aktív letámadással próbálja visszavenni az irányítást.", "hu", g49), [])
    case("o", "metric names are no claim ('control index', 'kontrollindex', 'területi fölény')", dom("With a control index of -0.168 the game is open.", "en", g49) + dom("A kontrollindex -0,168, a területi fölény 55%.", "hu", g49), [])
    case("o", "a regime switch is no team claim ('shifted from control to chaos', 'kontrollról káoszra')", dom("At 56' the match has shifted from control to chaos.", "en", g49) + dom("Váltás: kontrollról káoszra.", "hu", g49), [])
    case("o", "27' HU: 'ők irányítják a játékot' after 'Vallora' (field tilt 66 %) is backed", dom("A Vallora vezet. A vezetés után ők irányítják a játékot.", "hu", item_at(27, kind="moment", mtype="goal")), [])
    case("o", "'a nearly even contest for dominance' is no claim", dom("The index indicates a nearly even contest for dominance.", "en", g49), [])
    # p) wording from the hand review of 27 Oct
    case("p", "'PPDA (Pressures allowed per defensive action)' explains PPDA wrongly", has(V.check_metric_glosses("PPDA (Pressures allowed per defensive action): 4.89", "en"), "passes allowed"), True)
    case("p", "'PPDA (passes allowed per defensive action)' is right", V.check_metric_glosses("PPDA (passes allowed per defensive action) 4.89", "en"), [])
    case("p", "HU: 'PPDA (engedett passzok nyomás alatt)' is wrong", has(V.check_metric_glosses("PPDA (engedett passzok nyomás alatt) | 6,44", "hu"), "védekező akcióra"), True)
    case("p", "HU: 'PPDA (az ellenfél passzai egy védekező akcióra)' is right", V.check_metric_glosses("PPDA (az ellenfél passzai egy védekező akcióra): 6,44", "hu"), [])
    case("p", "85' HU: 'hatékonyabb nyomásgyakorlással' (the facts measure intensity)", has(V.check_pressing_wording("A Northbridge hatékonyabb nyomásgyakorlással játszik.", "hu"), "intenzívebb"), True)
    case("p", "'more intense pressing' is right", V.check_pressing_wording("Northbridge show more intense pressing (2.4 pressures per minute).", "en"), [])
    case("p", "85': '174 pressures overall and 1.87 in the last 15 minutes' (a rate written as a count)", has(V.check_pressing_wording(
        "Northbridge made 174 pressures overall and 1.87 in the last 15 minutes.", "en", {1.87}), "per minute"), True)
    case("p", "'1.87 pressures per minute' is right", V.check_pressing_wording("Northbridge make 1.87 pressures per minute.", "en", {1.87}), [])
    case("p", "a pressing category score is no rate ('a letámadás (32,7)')", V.check_pressing_wording("Gyengébb pontjai közé tartozik a letámadás (32,7).", "hu", {1.87}), [])
    case("p", "40': 'a slight edge' for a momentum of 0.511", has(V.check_momentum_wording("Northbridge hold a slight edge in momentum (0.511).", "en"), "not slight"), True)
    case("p", "a slight momentum of 0.21 is fine", V.check_momentum_wording("Vallora have a slight momentum edge (0.21).", "en"), [])
    case("p", "HU minute '3-2-nél 60-nál' (write 'a 60. percben')", has(V.check_hu_minutes("3-2-nél 60-nál Northbridge támad.", "hu"), "60. percben"), True)
    case("p", "HU: '3-2-nél' (a score) and '60-nál több passz' (a comparison) are fine", V.check_hu_minutes("3-2-nél a Vallora 60-nál több passzt adott.", "hu"), [])
    case("p", "15' HU: an English sentence in a Hungarian text", has(V.check_english_sentences("Novak erős. His category scores are above 79.5 and 84.4 in the two areas.", "hu"), "English sentence"), True)
    case("p", "garbled: 'a győztes fő esélyesként emelkedett ki'", has(V.check_garbled("A győztes fő esélyesként emelkedett ki a bajnokság végén.", "hu"), "fő esélyesként"), True)
    case("p", "garbled: 'nyitott állásnál vonultak pihenőre' (at 2-2)", has(V.check_garbled("Nyitott állásnál vonultak pihenőre a csapatok.", "hu"), "döntetlen"), True)
    case("p", "garbled: 'nem hagyta magát lelépni', 'nyitott bajnokin', 'fizikai párharcokban'", len(V.check_garbled("Nem hagyta magát lelépni a nyitott bajnokin, a fizikai párharcokban.", "hu")), 3)
    case("p", "English in Hungarian: 'possessionnel'", has(V.check_language_fields(dict(overlay="Vallora több possessionnel játszik"), "hu"), "possessionnel"), True)
    nov = STORE.profiles["T2P12"]
    case("p", "27' HU: 'Novak labdaszerzése és letámadása kiemelkedik (41,9 és 46,4)' (both below 75)", has(V.check_category_praise(
        "Novak labdaszerzése és letámadása kiemelkedik (41,9 és 46,4).", "hu", dict(nov, cat_defensive_activity="41.9", cat_pressing="46.4"), "Dominik Novak"), "not outstanding"), True)
    case("p", "'Petrovic's pressing (85.9) stands out, while his passing (48.0) lags' is right", V.check_category_praise(
        "Petrovic's pressing (85.9) stands out, while his passing (48.0) lags behind.", "en", STORE.profiles["T1P09"], "Ilyes Petrovic"), [])
    case("p", "scouting HU: Blanchard 'Védekezési aktivitása viszont kiemelkedő (68,2)'", has(V.check_scouting(
        "**Szymon Blanchard (15, Kalmarsund BK U19, FB)**  Védekezési aktivitása viszont kiemelkedő (68,2).", "hu", STORE), "68.2"), True)
    # r) false positives found in re-run p1
    g27 = item_at(27, kind="moment", mtype="goal")
    case("r", "27': '92.3% pass accuracy and perfect passing under pressure' is two statistics", V.check_focus_percentages(
        "Dominik Novak excels with 92.3% pass accuracy and perfect passing under pressure.", "en", STORE, "T2P12", g27["t_ms"]), [])
    st49 = STORE.state_at_ms(g49["t_ms"])
    case("r", "49': '51.24% Vallora to 48.76% Northbridge' (the team follows the share)", V.check_team_shares(
        "Overall match possession is close: 51.24% Vallora to 48.76% Northbridge.", "en", st49, STORE), [])
    case("r", "'Vallora 49.2%, Northbridge 50.8%' (team before, comma after) stays right", V.check_team_shares(
        "Despite a close possession split (Vallora 49.2%, Northbridge 50.8% in the last 5 minutes), Vallora pressed.", "en", STORE.state_at_ms(g27["t_ms"]), STORE), [])
    case("r", "49': '48.76% Vallora' is still caught when the team follows the share", has(V.check_team_shares(
        "Overall possession: 48.76% Vallora.", "en", st49, STORE), "Northbridge's"), True)
    case("r", "49': 'puts Vallora United on top of the tournament standings' is no dominance claim", dom("This goal puts Vallora United on top of the tournament standings.", "en", g49), [])
    case("r", "HU: 'az irányítás egyik csapatnál sem domináns', 'kiegyensúlyozott játék uralkodik' are no claims", dom(
        "Kiegyensúlyozott játékkörnyezet uralkodik, az irányítás egyik csapatnál sem domináns.", "hu", st30), [])
    case("r", "49' HU: 'a birtoklás és nyomásgyakorlás kiegyenlített' is no equaliser", V.check_semantics(
        "Vallora United átvette a vezetést 3-2-re. A csapatok között a birtoklás és nyomásgyakorlás kiegyenlített.", "hu", g49, STORE, CFG), [])
    case("r", "70': Novak 'played about 74 minutes' (70' is 74.8 minutes after kick-off)", [p for p in V.check_semantics(
        "At 70', Vallora substitute Dominik Novak, who played about 74 minutes.", "en", sub70, STORE, CFG) if "longer than the match" in p], [])
    rf_gf = dict(rf, tournament=dict(rf["tournament"], final_standings=[dict(r, gf=x["gf"], ga=x["ga"]) for r, x in zip(rf["tournament"]["final_standings"], STORE.tournament["standings_after"])]))
    case("r", "recap table: Sankt Albrecht's goals '7-7' (goals for - against) are no match score", [p for p in V.check_recap(
        "| 3 | Sankt Albrecht SV U19 | 6 | 1 | 3 | 2 | 7-7 |", "hu", rf_gf, STORE) if "never happened" in p or "goals" in p], [])
    case("r", "recap table: '7-9' for Sankt Albrecht is caught against the final standings", has(V.check_recap(
        "| 3 | Sankt Albrecht SV U19 | 6 | 1 | 3 | 2 | 7-9 |", "hu", rf_gf, STORE), "final standings say 7-7"), True)
    # s) the hand review after re-runs p1-p3
    m18 = item_at(18, kind="moment", mtype="goal")
    m18["moment"] = dict(m18["moment"], ball_metrics=dict(shot=dict(shot_speed_kmh=30.2)))
    case("s", "18': 'a powerful 30.2 km/h header' (a number between the words)", has(V.check_shot_words(
        "Vallora United equalize with a powerful 30.2 km/h header from Nagy.", "en", m18["moment"]), "30 km/h"), True)
    st40 = STORE.state_at_ms(item_at(40, kind="moment")["t_ms"])
    case("s", "40': 'Northbridge holds a slight momentum edge' without a number (momentum 0.51)", has(V.check_momentum_wording(
        "Northbridge FC holds a slight momentum edge.", "en", st40), "not slight"), True)
    case("s", "40' HU: 'a lendület enyhén a Northbridge javára billen' (0,51)", has(V.check_momentum_wording(
        "A pillanatnyi lendület enyhén a Northbridge FC U19 javára billen.", "hu", st40), "not slight"), True)
    case("s", "47': 'a control index of 0.173 indicating a slight dominance' (the index is no team's dominance)", has(V.check_units(
        "The control index of 0.173 indicating a slight dominance in structure.", "en"), "whole game"), True)
    case("s", "49': 'Iker Andreou penalties to 3-2' (a noun used as a verb)", has(V.check_semantics("Iker Andreou penalties to 3-2, Vallora takes lead", "en", g49, STORE, CFG), "noun is used as a verb"), True)
    case("s", "60': 'Vallora controlling slightly more possession' (possession alone)", bool(dom(
        "The match is chaotic, with Vallora controlling slightly more possession.", "en", item_at(60))), True)
    case("s", "63': 'pressing intensity is higher but less effective'", has(V.check_pressing_wording(
        "Northbridge FC's pressing intensity is higher but less effective.", "en"), "intensity"), True)
    case("s", "HU minutes: \"2'-nál\", \"38'-nál\", \"45+3'-nál\"", [bool(V.check_hu_minutes(t, "hu")) for t in ("0-1 az állás 2'-nál", "helyzetet hagyott ki 38'-nál", "egyenlít 45+3'-nál")], [True, True, True])
    case("s", "HU minutes: \"38'-ban\" and 'a 38. percben' are fine", V.check_hu_minutes("kimaradt 38'-ban, a 38. percben", "hu"), [])
    case("s", "HU article before a number: 'az 49. percben', 'a 54. percben' are wrong", [bool(V.check_hu_minutes(t, "hu")) for t in ("átvette a vezetést az 49. percben", "a 54. percben érkezett")], [True, True])
    case("s", "HU article before a number: 'a 49.', 'az 54.', 'az 5.', 'a 18.' are right", V.check_hu_minutes("a 49. percben, az 54. percben, az 5. percben, a 18. percben", "hu"), [])
    case("s", "45+3' HU: 'a mérkőzés utolsó pillanataiban' for a first-half goal", has(V.check_semantics(
        "Szymon Winther fejessel egyenlít a mérkőzés utolsó pillanataiban, 2-2.", "hu", g48, STORE, CFG), "end of the first half"), True)
    surge = next(it for it in __import__("run_agents").build_items(STORE, CFG) if it["kind"] == "moment" and it["moment"]["type"] == "pressing_surge" and it["moment"]["fact"].get("match_rate_per_5min"))
    avg = surge["moment"]["fact"]["match_rate_per_5min"]
    case("s", "pressing surge: the match average 'over the last 15 minutes' (it is the whole match so far)", has(V.check_pressing_average(
        f"A nyomás 15-re nőtt, meghaladva a mérkőzés utolsó 15 percére átlagolt {str(avg).replace('.', ',')}-t.", "hu", surge), "whole match"), True)
    m75 = item_at(75)
    case("s", "an absent player's marker only in the hidden detail is not enough (what the viewer reads must say it)", has(V.check_absent_player(
        "Szymon Blanchard: 217 tournament minutes. Szymon Blanchard is a right-back with 217.1 minutes. His profile does not reflect this match.",
        "en", m75, STORE, "T4P11", shown="Szymon Blanchard: 217 tournament minutes. Szymon Blanchard is a right-back with 217.1 minutes."), "does not play"), True)
    case("s", "'slightly' next to another word is no momentum claim ('Northbridge's slightly stronger pressing, Vallora carries the momentum')", V.check_momentum_wording(
        "Despite Northbridge's slightly stronger pressing, Vallora carries the momentum.", "en", st40), [])
    case("s", "'this goal shifts momentum slightly' is a change, not a level", V.check_momentum_wording("This goal shifts momentum slightly in their favor.", "en", st40), [])
    case("s", "'yet to translate pressure into control as the match remains unsettled' is no dominance claim", dom(
        "Vallora have yet to translate pressure into control as the match remains unsettled.", "en", g49), [])
    # t) recaps (facts as run_agents.recap_and_scouting builds them)
    import asyncio as _a, tempfile as _t
    import run_agents as _ra
    got = {}
    async def _fake(rt, agent, prompt, lang, meta, fallback=None, facts=None, store=None, max_repairs=1, previous=None):
        if facts is not None:
            got[(meta["persona"], lang)] = facts
        return "x"
    real, _ra.checked_document = _ra.checked_document, _fake
    try:
        _a.run(_ra.recap_and_scouting(None, STORE, [], CFG, _t.mkdtemp()))
        rfa = got[("fan", "en")]
    except ImportError:   # the recap builder imports the pipeline (agent-framework); the same facts from the store
        rfa = dict(recap_facts(), teams=[STORE.team_name(STORE.home), STORE.team_name(STORE.away)], match_team_ids=[STORE.home, STORE.away])
    finally:
        _ra.checked_document = real
    case("t", "recap: 'the previously top-ranked Northbridge United' (the team is Northbridge FC)", has(V.check_team_names("over the previously top-ranked Northbridge United", STORE), "Northbridge FC"), True)
    case("t", "recap: 'Northbridge FC' and 'Vallora United' are right", V.check_team_names("Vallora United beat Northbridge FC.", STORE), [])
    case("t", "recap HU: 'Andreou a 27. percben visszavette a vezetést' (Vallora had not led before)", has(V.check_recap_leads(
        "Iker Andreou aztán a 27. percben erős lövéssel visszavette a vezetést Vallorának.", "hu", rfa), "had not led"), True)
    case("t", "recap HU: 'a 49. percben ismét Vallora vezetett' is right (Vallora led 2-1 before)", V.check_recap_leads(
        "A 49. percben Andreou büntetőből betalált, ismét Vallora vezetett.", "hu", rfa), [])
    case("t", "recap HU: 'büntetőből szerzett góllal növelte előnyét' at 2-2 (the goal takes the lead)", has(V.check_recap_leads(
        "A második félidő elején Vallora büntetőből szerzett góllal növelte előnyét: Andreou duplázott.", "hu", rfa), "does not extend"), True)
    case("t", "recap HU: 'Vallora 2,35-szörös várható gólértékkel' (2,35 is the xG itself)", has(V.check_recap_wording(
        "Vallora 2,35-szörös várható gólértékkel volt veszélyesebb.", "hu", rfa), "not a ratio"), True)
    case("t", "recap: Andreou 'made eight touches in the box' (8 is his count at 41')", has(V.check_recap_counts(
        "Iker Andreou, who made eight touches in the box, kept up the pressure.", "en", rfa, STORE), "count at 41'"), True)
    case("t", "recap: 'Byrne ... from just over 10 meters' is no running count", V.check_recap_counts(
        "Mathis Byrne fired from just over 10 meters.", "en", rfa, STORE), [])
    case("t", "recap: 'territorial dominance' with a match field tilt of 55.3 %", has(V.check_recap_dominance(
        "Field tilt: Vallora 55.3%, Vallora's territorial dominance fostered more chances.", "en", rfa), "55.3"), True)
    case("t", "recap: 'Northbridge's attempts to dominate possession' is no claim", V.check_recap_dominance(
        "Despite Northbridge's vigorous pressing and attempts to dominate possession, Vallora held firm.", "en", rfa), [])
    case("t", "recap HU: 'Labdabirtoklás: Vallora 51,9%, enyhe fölény' is a possession share, not dominance", V.check_recap_dominance(
        "Labdabirtoklás: Vallora 51,9%, enyhe fölény a kritikus pillanatokban.", "hu", rfa), [])
    case("t", "a Hungarian ordinal does not end a sentence ('a 27. percben')", len(V.SENT_RE.split("Andreou a 27. percben betalált. Utána Winther egyenlített.")), 2)
    case("t", "18': 'mutual territorial control' is no team claim", dom("The match is balanced, showing mutual territorial control.", "en", item_at(18, kind="moment", mtype="goal")), [])
    case("t", "recap: 'Entering the match, Northbridge led the table by a point' is the gap before the match", [p for p in V.check_recap(
        "Entering the match, Northbridge led the table by a point, but Vallora won the title.", "en", rf, STORE) if "margin" in p], [])
    case("t", "recap: 'Vallora came out on top' (won) is no dominance claim", V.check_recap_dominance("Vallora came out on top in a tense final.", "en", rfa), [])
    # u) the targeted text fixes
    case("u", "recap: 'underpinning their control at key moments' with a match field tilt of 55.3 %", has(V.check_recap_dominance(
        "Vallora had 55.3% field tilt, underpinning their control at key moments.", "en", rfa), "their control"), True)
    case("u", "recap: 'some things were out of their control' is no claim", V.check_recap_dominance(
        "Some things were out of their control.", "en", rfa), [])
    edits = json.load(open("config/targeted_edits.json", encoding="utf-8"))["edits"]
    docs = {e["file"]: open(e["file"], encoding="utf-8").read() for e in edits if e["target"] == "doc"}
    case("u", "targeted edits: every recap edit is applied (the new phrase once, the old phrase gone)",
         [e["id"] for e in edits if e["target"] == "doc" and not (docs[e["file"]].count(e["new"]) == 1 and e["old"] not in docs[e["file"]])], [])
    import apply_targeted_edits as _ate
    back = {f: text for f, text in docs.items()}
    for e in edits:
        if e["target"] == "doc":
            back[e["file"]] = back[e["file"]].replace(e["new"], e["old"], 1)
    case("u", "targeted edits: a regenerated recap (the old phrases back) no longer counts as edited",
         [e["id"] for e in edits if e["target"] == "doc" and _ate.on_disk(back[e["file"]], e)], [])
    shown = [json.loads(l) for l in open("data/narration/results_debug.jsonl", encoding="utf-8") if l.strip()]
    rf_run = _ra.build_recap_facts(STORE, shown)          # the facts the Recap writer got in this run
    for f, text in docs.items():
        lang = "hu" if f.endswith("_hu.md") else "en"
        body = text.split("\n\n<sub>Source")[0]
        case("u", f"targeted edits: {os.path.basename(f)} passes the document and recap checks",
             V.check_document(body, lang, STORE) + V.check_recap(body, lang, rf_run, STORE), [])
    ov = [e for e in edits if e["target"] == "overlay"]
    case("u", "targeted edits: every overlay edit is applied and marked 'edited: targeted fix' in the trace",
         [e["id"] for e in ov if not any(r["item_id"] == e["item_id"] and (r.get("edited") or {}).get("kind") == "targeted fix" and e["id"] in r["edited"]["ids"]
                                         and e["new"] in (r["final"] or {}).get(e["field"], "") and e["old"] not in (r["final"] or {}).get(e["field"], "") for r in shown)], [])
    # q) the comparison uses exactly the pre-check's text checks
    try:
        import compare_agents
        sc = compare_agents.score_text(STORE, CFG, rules, item_at(80), dict(persona="fan", lang="hu", club_view="neutral", focus_player=None),
                                       dict(overlay="80': Vallora vezet", commentary="A nyitott bajnokin a Vallora vezet."), dict(state=STORE.state_at_ms(item_at(80)["t_ms"])))
        case("q", "compare_agents.score_text flags a garbled term the pre-check flags (wording)", sc["cats"].get("wording", 0) >= 1, True)
    except ImportError:
        case("q", "comparison scoring (skipped: agent-framework not installed)", True, True)
    pipeline_case()
    width = max(len(r["case"]) for r in RESULTS)
    for r in RESULTS:
        print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['fix']}  {r['case']:<{width}}  expected {r['expected']!r}, got {r['got']!r}")
    n = sum(r["passed"] for r in RESULTS)
    print(f"\n{n}/{len(RESULTS)} cases passed")
    with open("data/narration/checks_test.json", "w", encoding="utf-8") as f:
        json.dump(dict(note="tests/test_checks.py: free test cases for the checker fixes", passed=n, total=len(RESULTS),
                       rows=[dict(r, expected=str(r["expected"]), got=str(r["got"])) for r in RESULTS]), f, ensure_ascii=False, indent=1)
    return 0 if n == len(RESULTS) else 1


def pipeline_case():
    """a2) the real workflow with a fake model whose Verifier 'repairs' a focus text by swapping the player's name."""
    try:
        import agent_framework  # noqa: F401
    except ImportError:
        RESULTS.append(dict(fix="a", case="workflow: Verifier name swap is blocked (skipped: agent-framework not installed)", expected=True, got=True, passed=True))
        return
    import tempfile
    sys.path.insert(0, "tests")
    from test_failure_recovery import FakeBackend
    from agents.cache import ResponseCache
    from agents.llm import LLMRuntime
    from agents.pipeline import run_items
    import run_agents
    items = [it for it in run_agents.build_items(STORE, CFG) if it["mode"] == "focus" and it["focus_player"] == "T1P09"][:1]

    class SwapVerifier(FakeBackend):
        async def respond(self, agent, prompt, meta):
            out = await super().respond(agent, prompt, meta)
            if agent == "verifier":
                d = json.loads(out["text"])
                for k in ("overlay", "commentary", "detail"):
                    if d.get(k):
                        d[k] = d[k].replace("Ilyes Petrovic", "Ilyes Vermeulen").replace("Petrovic", "Vermeulen")
                d["verdict"] = "repaired"
                out["text"] = json.dumps(d, ensure_ascii=False)
            if agent == "narrator":
                d = json.loads(out["text"])
                d["overlay"] = "Ilyes Petrovic, still on the bench; low data so far" if meta["lang"] == "en" else "Ilyes Petrovic a kispadon; eddig kevés adat"
                d["commentary"] = d["overlay"] + "."
                out["text"] = json.dumps(d, ensure_ascii=False)
            return out
    tmp = tempfile.mkdtemp()
    rt = LLMRuntime(STORE, dict(CFG, llm_timeout_s=1, llm_backoff_scale=0.001), ResponseCache(os.path.join(tmp, "c")), os.path.join(tmp, "l.jsonl"),
                    backend=SwapVerifier(STORE, items))
    res, _ = asyncio.run(run_items(rt, STORE, V.load_rules(), items, CFG))
    finals = [r["final"]["overlay"] if r["final"] else "" for r in res]
    kept = all("Petrovic" in f and "Vermeulen" not in f for f in finals) and all(any(x.get("kind") == "name_change_blocked" for x in r["recovery"]) for r in res)
    RESULTS.append(dict(fix="a", case="workflow: Verifier name swap is blocked, the narrator text is kept", expected=True, got=kept, passed=kept))


if __name__ == "__main__":
    raise SystemExit(main())
