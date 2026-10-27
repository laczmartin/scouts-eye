# Scout's Eye – short guide to the web UI

**What is this?** *Scout's Eye* is explainable live captioning of the last, title-deciding match (M12) of a **fully synthetic** U19 tournament. Every number comes from facts computed from the events; the texts are written and checked by five cooperating agents (Microsoft Foundry + Microsoft Agent Framework). Teams and players are fictional and the venue is neutral.

## Tabs and buttons

| element | what it does |
|---|---|
| **Match** | 2D pitch drawn from the events, match clock in football notation (45+3', 90+2'), scoreboard, ▶ play, speed 1×/10×/60×, timeline with clickable goal and moment markers. On the right: the overlays, synchronised to the match clock. |
| Fan / Analyst / both | tone of the overlays: *fan* = few numbers, emotion; *analyst* = metrics, percentiles, PPDA, field tilt; *both* = side by side from the same facts |
| HU / EN | language of the interface and the overlays |
| Neutral / Northbridge / Vallora | club view: fan overlays framed from that club's point of view |
| Player focus | follows one player for the whole match; focus narration exists for the four ★ planted talents, other players open their profile |
| **Agent trace** | the path of the selected overlay step by step: fact card → Match Analyst → Narrator variants → deterministic pre-check → repair round → Verifier → final; latency, tokens and quota waits per call. On the right: the aggregate and the roles diagram. |
| **Player profile** | 11 categories as bars, position score, rank in the position, minutes, reliability, live KPIs up to the current clock |
| **Scouting** | rankings per position (≥ 180 minutes only), a separate "low data" list, the four ★ talents, scouting notes in HU/EN |
| **Recap** | post-match recap in fan or analyst tone, HU/EN |
| **About** | architecture, data statement, documentation |
| **▶ Demo** | a curated 90-second tour in six steps |
| **?** | this guide in short, HU/EN |

Keys: space = play/pause, ← → = ±1 minute, Esc = close a window.

## The demo in three steps

1. Press the yellow **▶ Demo** button (top right).
2. Click any **overlay**: the evidence and agent-trace panels open below.
3. Open the **Scouting** tab: rankings, the four planted talents (model rank and *Validation* rank), notes.

## Markers

- **★** – *talent planted for validation: the model does not know who it is.* Four young (15–16) players were hidden in the synthetic data to test whether the system finds them. **Validation** shows their hidden true rank, for checking only; the model never sees it.
- **low data** – below 180 tournament minutes (20 minutes live) a player gets no ranking, only a flag.
- **reliability** – by minutes: *very low* < 90, *low* 90–179, *medium* 180–359, *good* ≥ 360.
- **fact card (dashed border)** – appears instantly in live mode, from a template without an LLM (e.g. "GOAL – Andreou (penalty), 49' – Vallora 3–2"); when the agents' text is ready and the Verifier approves it, it replaces the card ("upgraded from fact card").
- **fallback: fact card** – no verified agent text exists for this variant (the text was rejected, or an agent call failed after its retries), so the fact card stays on screen.
- **tag (deterministic)** – a short caption with a player's name when a threshold is crossed: a very difficult completed pass, a shot of at least 100 km/h, or the fastest run of the match so far. Computed from the data, no AI. The event line under the pitch, the evidence panel and the live player card show pass distance, pass difficulty, line-breaking passes and ball / shot speed.
- **↺ recovered** – a step failed (an unreadable answer or a retried call) but a checked text was still produced. The Agent trace tab lists what happened in a "Failure recovery" step and box.
- **Single agent vs multi-agent** (Agent trace tab, right column) – the same first half written by one agent and by the five agents, scored by the same checks, with the hand review and the limits.
- **verified · repaired** – the Verifier repaired the text (number, name, claim, clock or language).

## Evidence and trace panels

- **Evidence:** the overlay's source events (event id, minute, type, player), the data fields used, the **claim rule** applied (e.g. "dominates the match → field tilt ≥ 58 % or possession ≥ 58 % or momentum ≥ 0.25") and the Verifier's verdict, with the **before/after** text for repairs.
- **Trace:** which agent read what from the shared state and wrote what into it, how many seconds and tokens it used, where the pre-check failed (wrong number, unsupported claim, wrong half-time clock, home/away wording, language), and where a repair or rejection happened. Click a variant (fan/analyst, HU/EN, club view) to follow the other overlays of the same moment.
