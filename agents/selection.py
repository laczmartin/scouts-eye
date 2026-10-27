"""Which moments get narrated in which mode (config/narration.json)."""

import json


def load_config(path="config/narration.json"):
    with open(path) as f:
        return json.load(f)


def select_items(store, cfg, mode, focus_player=None):
    """Return a chronological list of narration items: dict(kind='moment'|'state', ...)."""
    mc = cfg["modes"][mode]
    items = []
    for m in store.moments:
        if mode == "focus":
            if m.get("player_id") != focus_player and m["type"] != "goal":
                continue
            concrete = (m.get("player_id") == focus_player and m["type"] in ("goal", "big_chance", "card", "milestone")) or \
                       (m["type"] == "goal" and m["fact"].get("assist_by") == store.player_name(focus_player))
            live = store.player_live(focus_player, m["t_ms"])
            mins = live["minutes"] if live else 0.0
            if not concrete and mins < cfg["low_data_minutes_live"]:
                continue  # no focus overlay before 20 minutes played, unless a concrete event involves the player
        else:
            if mc["moment_types"] is not None and m["type"] not in mc["moment_types"] and not (m["type"] == "card"):
                continue
            if m["type"] == "card" and m["fact"].get("card") not in (
                    ["straight_red", "second_yellow"] if mc["card_outcomes"] == ["red"] else ["yellow", "straight_red", "second_yellow"]):
                continue
            if m["type"] != "card" and mc["moment_types"] is None and m["importance"] < mc["min_importance"]:
                continue
            if m["type"] == "card" and m["importance"] < mc["min_importance"] and m["fact"].get("card") == "yellow":
                continue
        items.append(dict(kind="moment", t_ms=m["t_ms"], minute=m["minute"], moment=m))
    # state cards
    every = mc["state_card_every_min"]
    seen = set()
    for s in store.states:
        if s["minute"] > 0 and s["minute"] % every == 0 and (s["minute"], s["period"]) not in seen and s["minute"] not in (45, 90):
            seen.add((s["minute"], s["period"]))
            items.append(dict(kind="state", t_ms=s["t_ms"], minute=s["minute"], state=s))
    # congestion control: at most one item per cooldown window (goals exempt). Items are admitted in
    # priority order (goals, then importance, state cards last) so the most important ones survive.
    cooldown = mc["cooldown_min"] * 60000
    def priority(it):
        if it["kind"] == "state":
            return 0.35
        return 2.0 if it["moment"]["type"] in cfg["cooldown_exempt_types"] else it["moment"]["importance"]
    accepted = []
    for it in sorted(items, key=lambda it: (-priority(it), it["t_ms"])):
        exempt = it["kind"] == "moment" and it["moment"]["type"] in cfg["cooldown_exempt_types"]
        if not exempt and any(abs(it["t_ms"] - a["t_ms"]) < cooldown for a in accepted
                              if not (a["kind"] == "moment" and a["moment"]["type"] in cfg["cooldown_exempt_types"])):
            continue
        accepted.append(it)
    accepted.sort(key=lambda it: it["t_ms"])
    return accepted
