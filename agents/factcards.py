"""Deterministic, LLM-free fact cards (the first layer of the two-step live captioning).

A fact card is rendered from templates (HU / EN) straight from the moment and
the state snapshot, passes the same clock / score / venue checks as the agent
texts, and appears within milliseconds. When the agents' verified text is
ready it replaces the card (same item id, flagged "upgraded").
"""

from . import verify as V

TEMPLATES = {
    "goal": {"hu": "GÓL – {scorer}{pen}, {clock} – {score}", "en": "GOAL – {scorer}{pen}, {clock} – {score}"},
    "big_chance": {"hu": "NAGY HELYZET – {shooter}, {clock} (xG {xg})", "en": "BIG CHANCE – {shooter}, {clock} (xG {xg})"},
    "card": {"hu": "{cardname} – {player}, {clock}", "en": "{cardname} – {player}, {clock}"},
    "momentum_shift": {"hu": "LENDÜLETVÁLTÁS – {team} felé, {clock}", "en": "MOMENTUM SHIFT – towards {team}, {clock}"},
    "pressing_surge": {"hu": "PRESSING-HULLÁM – {team}, {n} letámadás 5 perc alatt, {clock}", "en": "PRESSING SURGE – {team}, {n} pressures in 5 minutes, {clock}"},
    "control_chaos_switch": {"hu": "JÁTÉKKÉP – {regime_hu}, {clock}", "en": "GAME STATE – {regime_en}, {clock}"},
    "milestone": {"hu": "MÉRFÖLDKŐ – {player}: {milestone_hu}, {clock}", "en": "MILESTONE – {player}: {milestone}, {clock}"},
    "player_threshold": {"hu": "{player}: {count}. {kpi_hu}, {clock}", "en": "{player}: {kpi} #{count}, {clock}"},
    "substitution": {"hu": "CSERE – {on} be, {off} le, {clock}", "en": "SUBSTITUTION – {on} on, {off} off, {clock}"},
    "injury": {"hu": "SÉRÜLÉS – {player}, {clock}", "en": "INJURY – {player}, {clock}"},
    "state": {"hu": "{clock} – {score} · {team} birtoklás {poss}% · területi fölény {tilt}%", "en": "{clock} – {score} · {team} possession {poss}% · field tilt {tilt}%"},
}
CARD_NAMES = {"yellow": {"hu": "SÁRGA LAP", "en": "YELLOW CARD"}, "second_yellow": {"hu": "PIROS LAP (2. sárga)", "en": "RED CARD (second yellow)"},
              "straight_red": {"hu": "PIROS LAP", "en": "RED CARD"}}
KPI_HU = {"progressive_passes": "progresszív passz", "pressures": "letámadás", "defensive_duels_won": "megnyert védőpárharc", "key_passes": "kulcspassz",
          "touches_in_box": "érintés a 16-oson belül", "dribbles_completed": "sikeres csel", "aerial_duels_won": "megnyert fejpárharc"}
MILESTONE_HU = {"first tournament goal": "első gól a tornán", "youngest scorer of the tournament": "a torna legfiatalabb gólszerzője", "brace": "duplázott", "hat-trick": "mesterhármas"}
REGIME = {"chaos": ("káosz – nyílt játék", "chaos – open game"), "control": ("kontroll – nyugodt játék", "control – settled game"), "balanced": ("kiegyensúlyozott", "balanced")}


def _score_str(store, sh, sa):
    return f"{store.team_name(store.home).replace(' U19', '')} {sh}–{sa} {store.team_name(store.away).replace(' U19', '')}"


def fact_card(store, item, lang):
    """Return dict(text, data, evidence_event_ids) or None if no template applies."""
    if item["kind"] == "state":
        s = item["state"] if "state" in item else store.state_at_ms(item["t_ms"])
        h = s["teams"][store.home]["15min"]
        clock = store.clock_string(item["minute"], s["period"])
        # the shares are the first-named team's (15-minute window): name it, "possession 57%" alone is ambiguous
        text = TEMPLATES["state"][lang].format(clock=clock, score=_score_str(store, s["score"][store.home], s["score"][store.away]),
                                                team=store.teams[store.home]["city"], poss=round(h["possession_pct"]), tilt=round(h["field_tilt_pct"]))
        return dict(text=text, data=dict(score=s["score"], possession_pct=h["possession_pct"], field_tilt_pct=h["field_tilt_pct"]), evidence_event_ids=[])
    m = item["moment"]; f = m["fact"]; t = m["type"]
    clock = m.get("clock") or store.clock_string(m["minute"], m.get("period", 1))
    team = store.team_name(m["team_id"]).replace(" U19", "") if m.get("team_id") else ""
    fields = dict(clock=clock, team=team, player=f.get("player") or store.player_name(m.get("player_id")))
    data = dict(clock=clock)
    if t == "goal":
        sh, sa = (int(x) for x in f["score"].split("-"))
        fields.update(scorer=f["scorer"], pen=(" (büntető)" if lang == "hu" else " (penalty)") if f.get("penalty") else "", score=_score_str(store, sh, sa))
        data.update(score=f["score"], xg=f["xg"], penalty=f.get("penalty", False))
    elif t == "big_chance":
        fields.update(shooter=f["shooter"], xg=f["xg"]); data.update(xg=f["xg"])
    elif t == "card":
        fields.update(cardname=CARD_NAMES.get(f["card"], {}).get(lang, f["card"]), player=f["player"]); data.update(card=f["card"])
    elif t == "momentum_shift":
        fields.update(team=store.team_name(f["now_with"]).replace(" U19", "")); data.update(momentum_home=f["momentum_home"])
    elif t == "pressing_surge":
        fields.update(n=f["pressures_last_5min"]); data.update(pressures_last_5min=f["pressures_last_5min"], ppda_last_5min=f.get("ppda_last_5min"))
    elif t == "control_chaos_switch":
        r = REGIME.get(f["to_regime"], (f["to_regime"], f["to_regime"])); fields.update(regime_hu=r[0], regime_en=r[1]); data.update(control_index=f["control_index"])
    elif t == "milestone":
        fields.update(player=f["scorer"], milestone=f["milestone"], milestone_hu=MILESTONE_HU.get(f["milestone"], f["milestone"]))
    elif t == "player_threshold":
        fields.update(count=f["count"], kpi=f["kpi"].replace("_", " "), kpi_hu=KPI_HU.get(f["kpi"], f["kpi"])); data.update(count=f["count"], kpi=f["kpi"])
    elif t == "substitution":
        fields.update(on=f["on"], off=f["off"])
    elif t == "injury":
        pass
    else:
        return None
    text = TEMPLATES[t][lang].format(**fields)
    return dict(text=text, data=data, evidence_event_ids=list(m.get("evidence_event_ids", [])))


def checked_fact_card(store, item, lang, cfg):
    """Fact card with the deterministic clock / score / venue checks applied; problems are returned, not hidden."""
    card = fact_card(store, item, lang)
    if card is None:
        return None
    card["problems"] = V.check_semantics(card["text"], lang, item, store, cfg)
    card["layer"] = "deterministic"
    return card
