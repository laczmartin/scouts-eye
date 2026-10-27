/* Scout's Eye – static UI over the offline outputs. No Azure calls. */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const D = {};                       // all data
const S = { t: 0, playing: false, speed: 10, lastTick: 0, persona: "fan", lang: "en", club: "neutral", focus: "", selected: null,
            recapPersona: "fan", recapLang: "en", player: null, upgradeDelayMs: 0 };

// ------------------------------------------------------------ i18n
const T = {
  hu: {
    tagline: "Megmagyarázható U19 meccsintelligencia · többügynökös narráció, minden szám visszakövethető",
    tab_match: "Meccs", tab_agents: "Ügynök-nyomkövetés", tab_players: "Játékosprofil", tab_scouting: "Scouting", tab_recap: "Összefoglaló", tab_about: "Névjegy",
    demo_btn: "▶ Demo", demo_stop: "Demo leállítása", fan: "Szurkolói", analyst: "Elemzői", compare: "Szurkolói + Elemzői", neutral: "Semleges", focus: "Játékosfókusz", none: "— nincs —",
    feed: "Felirat-folyam", evidence: "Bizonyíték", evidence_hint: "Kattints egy feliratra: forrás-események, adatmezők, állítás-szabályok és a Verifier eredménye.",
    trace_sel: "Ügynök-nyomkövetés (kiválasztott felirat)", trace_hint: "Ténykártya → Analyst → Narrator-változatok → előszűrő → Verifier → javítás → végső. A teljes nézet az Ügynök-nyomkövetés fülön.",
    trace_title: "A kiválasztott felirat ügynök-nyomkövetése", agg_title: "Összesítés: hogyan dolgoztak együtt az ügynökök", roles_title: "Szerepek és közös állapot",
    profile_title: "Játékosprofil", player: "Játékos", live_title: "Élőben ezen a meccsen (az aktuális óráig)",
    scouting_title: "Scouting nézet", scouting_hint: "A rangsorban csak a legalább 180 perccel rendelkező játékosok szerepelnek. A négy fiatal fókuszjátékos kiemelve. A kor csak információ.",
    notes_hu: "Scouting-jegyzet (HU)", notes_en: "Scouting-jegyzet (EN)", about_title: "Hogyan működik",
    legend_pitch: "labdaút = az utolsó labdás akciók · ● aktuális esemény",
    star_legend: "kísérletben elrejtett tehetség – a modell nem tudja, ki az", validation_legend: "Validation = a rejtett valós rang (csak ellenőrzésre)",
    no_overlay: "Nincs felirat a képernyőn ekkor: {clock} – nyomd meg a ▶ gombot vagy ugorj az idővonal jelölőivel.",
    shown_of: "{n} látható a mód {total} feliratából", verified: "igazolt", repaired: "igazolt · javítva", upgraded: "frissítve ténykártyáról", edited: "javítva: célzott csere", edited_title: "Ellenőrzés után célzott szövegcsere (nincs LLM-hívás): csak a hibás kifejezés változott, a teljes szabálykészlet és a kézi újraolvasás szerint hibátlan", recap_edited: "Javítva célzott szövegcserével ({n} kifejezés); a szöveg többi része változatlan:", fact_card: "ténykártya (determinisztikus)",
    before_match: "Az M12 előtt (ezt használták élőben az ügynökök): {m} perc · {n} meccs · {rel}{rank} · pozíciós pontszám {s}. A fenti profil a teljes tornáé, az M12-vel együtt.",
    not_ranked: " · kevés adat, nincs rangsorolva",
    low_data: "kevés adat", low_data_min: "kevés adat ({m} perc < 180)", rank: "{r}. / {n} a(z) {pos} poszton", reliability: "megbízhatóság", min_matches: "{m} perc · {n} meccs",
    validation: "Validation (valós rang): {r}. / {n}", young_focus: "fiatal fókuszjátékos", secondary: "másodlagos poszt profilja", not_on_pitch: "{name} nincs a pályán ekkor: {clock} (vagy még nincs élő KPI-ja).", pitch_bench: "{name} nincs a pályán ({clock}): a kispadon ül, eddig nem állt be. Ebben a meccsben {on} lép pályára (az ügynökök élőben ezt nem tudják előre).", pitch_bench_never: "{name} nincs a pályán ({clock}): ebben a meccsben nem lép pályára ({why}).", pitch_off: "{name} már nincs a pályán: {off} lecserélték.", pitch_other_team: "{name} nem játszik ezen a mérkőzésen (a csapata nem játszik).",
    live_reliab: "nagyon alacsony megbízhatóság (élő)", live_low: "kevés adat (< 20 perc)", minutes_played: "játszott perc", live_score: "élő pozíció-pontszám", clock: "óra",
    help_title: "Súgó – mit látsz itt?", guide_title: "Üdvözlünk! 3 lépés a kezdéshez", guide_demo: "▶ Demo indítása", guide_dismiss: "Értem, bezárom",
    guide_steps: ["Nyomd meg a sárga <b>Demo</b> gombot: 90 másodperc alatt végigvezet a lényegen.", "Kattints egy <b>feliratra</b>: megnyílik a bizonyíték és az ügynök-nyomkövetés.", "Nézd meg a <b>Scouting</b> fület: rangsorok, a 4 elrejtett tehetség és a jegyzetek."],
    select_overlay: "Válassz egy feliratot a Meccs fülön (vagy indítsd a demót).",
    focus_group_talents: "★ Elrejtett tehetségek – fókusz-narrációval", focus_group_others: "Többi játékos – csak profil",
    no_focus: "{name}: ehhez a játékoshoz nincs fókusz-narráció – a fókusz-feliratok csak a négy elrejtett tehetséghez készültek. Tornaprofil: {minutes} perc, megbízhatóság: {rel}{low}.",
    open_profile: "Profil megnyitása", low_data_note: " (kevés adat: 180 perc alatt nincs rangsor)",
    difficulty: "nehézség", line_breaking: "vonaltörő", tag: "címke (determinisztikus)", fastest_shot: "leggyorsabb lövés", hardest_pass: "legnehezebb sikeres passz",
    line_breaking_passes: "vonaltörő passz (sikeres)", tags_title: "Játékoscímkék", metrics_title: "Eseménymutatók",
    recovered: "helyreállt", fallback: "tartalék: ténykártya", fallback_title: "Nincs igazolt ügynök-szöveg ehhez a változathoz, ezért a ténykártya marad a képernyőn.",
    recovered_title: "Egy lépés hibázott (olvashatatlan válasz vagy újrapróbált hívás), de ellenőrzött szöveg készült.", recovery_title: "Hibakezelés",
  },
  en: {
    tagline: "Explainable U19 Match Intelligence · multi-agent narration, every number traceable",
    tab_match: "Match", tab_agents: "Agent trace", tab_players: "Player profile", tab_scouting: "Scouting", tab_recap: "Recap", tab_about: "About",
    demo_btn: "▶ Demo script", demo_stop: "Stop demo", fan: "Fan", analyst: "Analyst", compare: "Fan + Analyst", neutral: "Neutral", focus: "Player focus", none: "— none —",
    feed: "Overlay feed", evidence: "Evidence", evidence_hint: "Click an overlay to see its source events, data fields, claim rules and the Verifier result.",
    trace_sel: "Agent trace (selected overlay)", trace_hint: "Fact card → Analyst → Narrator fan-out → pre-check → Verifier → repair → final. Open the Agent trace tab for the full view.",
    trace_title: "Agent trace for the selected overlay", agg_title: "Aggregate: how the agents worked together", roles_title: "Roles and shared state",
    profile_title: "Player profile", player: "Player", live_title: "Live in this match (up to the current clock)",
    scouting_title: "Scouting view", scouting_hint: "Rankings use ranked players only (≥ 180 minutes in the position). The four young players in focus are highlighted. Age is shown as information only.",
    notes_hu: "Scouting notes (HU)", notes_en: "Scouting notes (EN)", about_title: "How it works",
    legend_pitch: "ball path = last on-ball actions · ● current event",
    star_legend: "talent planted for validation – the model does not know who it is", validation_legend: "Validation = hidden ground-truth rank (for checking only)",
    no_overlay: "No overlay on screen at {clock} – press ▶ or jump with the timeline markers.",
    shown_of: "{n} shown of {total} in this mode", verified: "verified", repaired: "verified · repaired", upgraded: "upgraded from fact card", edited: "edited: targeted fix", edited_title: "Targeted text fix after verification (no LLM call): only the wrong phrase changed; it passes the full rule set and was read again by hand", recap_edited: "Edited by targeted fix ({n} phrases); the rest of the text is unchanged:", fact_card: "fact card (deterministic)",
    before_match: "Before M12 (what the agents used live): {m} min · {n} matches · {rel}{rank} · position score {s}. The profile above is the whole tournament, M12 included.",
    not_ranked: " · low data, not ranked",
    low_data: "low data", low_data_min: "low data ({m} min < 180)", rank: "rank {r} / {n} among {pos}", reliability: "reliability", min_matches: "{m} min · {n} matches",
    validation: "Validation (hidden true rank): {r} / {n}", young_focus: "young player in focus", secondary: "secondary position profile", not_on_pitch: "{name} is not on the pitch at {clock} (or has no live KPIs yet).", pitch_bench: "{name} is not on the pitch at {clock}: on the bench, not brought on so far. In this match he comes on at {on} (the agents cannot know that live).", pitch_bench_never: "{name} is not on the pitch at {clock}: he does not play in this match ({why}).", pitch_off: "{name} is not on the pitch any more: substituted at {off}.", pitch_other_team: "{name} does not play in this match (his team is not playing).",
    live_reliab: "very low reliability (live)", live_low: "low data (< 20 min)", minutes_played: "minutes played", live_score: "live position score", clock: "clock",
    help_title: "Help – what am I looking at?", guide_title: "Welcome! Three steps to start", guide_demo: "▶ Start the demo", guide_dismiss: "Got it, close",
    guide_steps: ["Press the yellow <b>Demo</b> button: a 90-second tour of the essentials.", "Click an <b>overlay</b>: the evidence and the agent trace open.", "Open the <b>Scouting</b> tab: rankings, the 4 planted talents and the notes."],
    select_overlay: "Select an overlay on the Match tab (or press Demo).",
    focus_group_talents: "★ Planted talents – with focus narration", focus_group_others: "Other players – profile only",
    no_focus: "{name}: no player-focus narration – focus overlays were generated for the four planted talents only. Tournament profile: {minutes} min, reliability: {rel}{low}.",
    open_profile: "Open profile", low_data_note: " (low data: no ranking below 180 minutes)",
    difficulty: "difficulty", line_breaking: "line-breaking", tag: "tag (deterministic)", fastest_shot: "fastest shot", hardest_pass: "hardest completed pass",
    line_breaking_passes: "line-breaking passes (completed)", tags_title: "Player tags", metrics_title: "Event metrics",
    recovered: "recovered", fallback: "fallback: fact card", fallback_title: "No verified agent text for this variant, so the fact card stays on screen.",
    recovered_title: "A step failed (unreadable answer or retried call), but a checked text was still produced.", recovery_title: "Failure recovery",
  },
};
const t = (k, vars) => { let s = (T[S.lang] || T.en)[k] ?? T.en[k] ?? k; if (vars) for (const [a, b] of Object.entries(vars)) s = s.replace(`{${a}}`, b); return s; };
const HELP = {
  hu: `## Mi ez az oldal?
Egy **teljesen szintetikus** U19-es torna utolsó, címdöntő meccsének (M12) élő feliratozása. Minden szám az eseményekből számolt tényekből jön, a szövegeket öt együttműködő ügynök írja és ellenőrzi (Microsoft Foundry + Agent Framework). A csapatok és játékosok kitaláltak.
## Fülek és gombok
- **Meccs**: 2D pálya, meccsóra (45+3', 90+2'), lejátszás 1×/10×/60×, idővonal jelölőkkel. Jobbra a feliratok: *Szurkolói* (kevés szám, érzelem) vagy *Elemzői* (metrikák, percentilisek), klubnézet, játékosfókusz.
- **Ügynök-nyomkövetés**: egy kiválasztott felirat útja – ténykártya → Match Analyst → Narrator-változatok → determinisztikus előszűrő → javítókör → Verifier → végső; hívásonként késés és token.
- **Játékosprofil**: 11 kategória, pozíció-pontszám, rang, percek, megbízhatóság.
- **Scouting**: rangsor posztonként, a 4 elrejtett tehetség, jegyzetek. **Összefoglaló**, **Névjegy**.
## A demó 3 lépésben
1. Nyomd meg a sárga **Demo** gombot. 2. Kattints egy feliratra. 3. Nézd meg a Scouting fület.
## Jelölések
- **★** kísérletben elrejtett tehetség – a modell nem tudja, ki az; a *Validation* a rejtett valós rang.
- **kevés adat**: 180 tornaperc (élőben 20 perc) alatt nincs rangsor, csak jelzés.
- **megbízhatóság**: very low < 90 perc, low 90–179, medium 180–359, good ≥ 360.
## Bizonyíték és nyomkövetés
A bizonyíték-panel a forrás-eseményeket (azonosítóval), a felhasznált adatmezőket, az alkalmazott állítás-szabályt (pl. „uralja → field tilt ≥ 58 %”) és a Verifier előtte/utána szövegét mutatja. A nyomkövető azt, melyik ügynök mit olvasott és írt a közös állapotba, mennyi időbe és tokenbe került, és hol volt javítás vagy elutasítás.`,
  en: `## What is this?
Live captioning of the last, title-deciding match (M12) of a **fully synthetic** U19 tournament. Every number comes from facts computed from the events; the texts are written and verified by five cooperating agents (Microsoft Foundry + Agent Framework). Teams and players are fictional.
## Tabs and buttons
- **Match**: 2D pitch, match clock (45+3', 90+2'), playback 1×/10×/60×, timeline markers. On the right the overlays: *Fan* (few numbers, emotion) or *Analyst* (metrics, percentiles), club view, player focus.
- **Agent trace**: the path of one overlay – fact card → Match Analyst → Narrator variants → deterministic pre-check → repair → Verifier → final; latency and tokens per call.
- **Player profile**: 11 categories, position score, rank, minutes, reliability.
- **Scouting**: rankings per position, the 4 planted talents, notes. **Recap**, **About**.
## The demo in 3 steps
1. Press the yellow **Demo** button. 2. Click an overlay. 3. Open the Scouting tab.
## Markers
- **★** talent planted for validation – the model does not know who it is; *Validation* is the hidden true rank.
- **low data**: below 180 tournament minutes (20 live minutes) no ranking, only a flag.
- **reliability**: very low < 90 min, low 90–179, medium 180–359, good ≥ 360.
## Evidence and trace
The evidence panel shows the source events (with ids), the data fields used, the claim rule applied (e.g. "dominates → field tilt ≥ 58 %") and the Verifier's before/after text. The trace shows which agent read and wrote what in the shared state, how long and how many tokens it took, and where a repair or rejection happened.`,
};
const ABOUT = {
  hu: { data: `<h3>Adatnyilatkozat</h3><p>Minden adat szintetikus: a csapatokat, játékosokat, dátumokat, a helyszínt és minden eseményt a projekt kódja generálja. Valós meccsadat, felvétel vagy szolgáltatói adat nincs benne. A fejlesztés során a generátort úgy hangoltuk, hogy a statisztikák U19-es szinten életszerűek legyenek. A fejlesztés korai szakaszában a generátort privát referenciaértékekhez (összesített ligaátlagokhoz) hangoltuk, és a validátor korábbi változatai ezekből származtatott életszerűségi sávokat használtak. Ebből a szakaszból két tervezési sáv maradt meg a generátorban (gól meccsenként 3,4–3,9, gól/xG 1,05–1,20). Ezen értékek egyike sincs benne a repóban; a publikált életszerűségi ellenőrzés csak nyilvános forrásokat használ (lásd benchmarks.py): UEFA Youth League gólátlag, egy publikált U19 passzvizsgálat, publikált U19 GPS-vizsgálatok. A csapatok, játékosok és a helyszín kitaláltak; a játékosok kitalált kiskorúak, ezért az ügynökök kizárólag futballszakmai kommentárt írnak.</p><h3>Pipeline</h3><p>események → KPI-k (szokásos eseményadat-definíciók, birtoklás-korrekció) → posztspecifikus profilok megbízhatósággal → élő motor (pillanatok, kontroll vs. káosz, momentum) → öt ügynök a Microsoft Foundryn, Microsoft Agent Frameworkkel orkesztrálva → determinisztikus előszűrő és Verifier → időzített, igazolt feliratok.</p>`,
        why: `<h3>Mit ad hozzá az öt ügynök?</h3><p>A Match Analyst eldönti, mi számít, és strukturált insight-kártyát ír; a Narrator-változatok personánként, nyelvenként és klubnézetenként ágaznak szét; a determinisztikus előszűrő és a Verifier elkapja a hibás számot, az alaptalan állítást, a rossz félidő-órát és a hazai/vendég szöveget, és egyszer visszaküldi; a Recap és a Scout ügynök az igazolt kártyákat használja újra. Az eredmény visszakövethető lánc egy esemény-azonosítótól egy ellenőrzött mondatig, két nyelven. Az első félidőn mérve (Ügynök-nyomkövetés fül, „1 ügynök vs. több ügynök”, mindkét kar ugyanazokat a tényeket kapja): egyetlen ügynök kicsit gyakrabban sért szabályt, mint a Narrator első vázlatai (98 szövegből 45 vs. 39); a nyereséget az ellenőrzések, a javítókör és a ténykártya-tartalék adja, ezek minden, az ellenőrző által látható hibát kiszűrnek (a képernyőn 0 / 98), kb. kétszeres költséggel és idővel. Az ellenőrzőn kívüli hibák mindkét oldalon megmaradnak (kézzel olvasva 5 + 6, illetve 4 + 5).</p><h3>Dokumentáció</h3><ul><li><code>README.md</code> – architektúra, ügynökök, futtatás offline / batch / élő módban</li><li><code>SEGEDLET.md</code> – rövid magyar segédlet ehhez a felülethez</li><li><code>docs/kpi_definitions.md</code> – minden KPI képlete</li><li><code>config/claim_rules.json</code> – a Verifier állítás-szabályai</li><li><code>scouting_validation.md</code> – őszinte validáció a rejtett ground truth ellen</li></ul><p id="runMeta" class="muted"></p>` },
  en: { data: `<h3>Data statement</h3><p>All data is synthetic: teams, players, dates, the venue and every event are generated by the project's code. No real match data, footage or provider data is included. During development the generator was tuned so that the statistics look plausible for U19 football. During early development, the generator was tuned against private reference values (aggregate league averages), and earlier versions of the validator used realism bands derived from them. Two generator design ranges remain from that stage (goals per match 3.4–3.9, goals/xG 1.05–1.20). None of these values are part of this repository; the published realism validation uses public sources only (see benchmarks.py). The public sources: UEFA Youth League goals per match, a published U19 passing study, published U19 GPS studies. Teams, players and the venue are fictional; the players are fictional minors, so the agents produce football commentary only.</p><h3>Pipeline</h3><p>events → KPIs (common event-data definitions, possession-adjusted) → position-specific profiles with reliability → live engine (moments, control vs chaos, momentum) → five agents on Microsoft Foundry orchestrated with the Microsoft Agent Framework → deterministic pre-check and Verifier → timed, verified overlays.</p>`,
        why: `<h3>What the five agents add</h3><p>The Match Analyst decides what matters and writes structured insight cards; Narrator variants fan out per persona, language and club view; the deterministic pre-check and the Verifier catch wrong numbers, unsupported claims, wrong half-time clocks and home/away wording and send the text back once; the Recap and Scout agents reuse the verified cards. The result is a traceable chain from an event id to a checked sentence in two languages. Measured on the first half (Agent trace tab, "Single agent vs multi-agent", both arms get the same facts): one agent breaks the rules a little more often than the Narrator's first drafts (45 vs 39 of 98 texts); the gain comes from the checks, the repair round and the fact-card fallback, which remove every problem the checks can see (0 of 98 on screen), at about twice the cost and time. Errors outside the checks remain in both (read by hand: 5 + 6 vs 4 + 5).</p><h3>Docs</h3><ul><li><code>README.md</code> – architecture, agents, running offline / batch / live</li><li><code>SEGEDLET.md</code> – short guide to this UI (Hungarian)</li><li><code>docs/kpi_definitions.md</code> – every KPI formula</li><li><code>config/claim_rules.json</code> – the claim rules the Verifier applies</li><li><code>scouting_validation.md</code> – honest validation against the hidden ground truth</li></ul><p id="runMeta" class="muted"></p>` },
};

function applyI18n() {
  document.documentElement.lang = S.lang;
  $$("[data-i18n]").forEach(el => { const k = el.dataset.i18n; if (T[S.lang][k] !== undefined) el.innerHTML = t(k); });
  $$(".seg[data-key=lang] button").forEach(b => b.classList.toggle("on", b.dataset.v === S.lang));
  $("#banner").textContent = D.match.stake[S.lang];
  $("#aboutData").innerHTML = ABOUT[S.lang].data; $("#aboutWhy").innerHTML = ABOUT[S.lang].why;
  const r = D.narration.run;
  $("#runMeta").textContent = (S.lang === "hu" ? `Commitolt narrációs futás: ${r.items} item, ${r.overlays} igazolt felirat, ${(r.tokens_full_run.total / 1e6).toFixed(2)} M token ≈ $${r.cost_usd_full_run} egy teljes futásra (gpt-4.1-mini).`
    : `Committed narration run: ${r.items} items, ${r.overlays} verified overlays, ${(r.tokens_full_run.total / 1e6).toFixed(2)} M tokens ≈ $${r.cost_usd_full_run} per full uncached run (gpt-4.1-mini).`);
  $("#helpTitle").textContent = t("help_title"); $("#helpBody").innerHTML = md(HELP[S.lang]);
  $("#guideTitle").textContent = t("guide_title"); $("#guideSteps").innerHTML = T[S.lang].guide_steps.map(s => `<li>${s}</li>`).join("");
  $("#guideDemo").textContent = t("guide_demo"); $("#guideDismiss").textContent = t("guide_dismiss");
  $$(".star-legend span[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
  if ($("#focusGroupTalents")) { $("#focusGroupTalents").label = t("focus_group_talents"); $("#focusGroupOthers").label = t("focus_group_others"); }
}

// ------------------------------------------------------------ loading
async function load() {
  const names = ["match", "events", "moments", "states", "overlays", "trace", "profiles", "players", "narration"];
  const res = await Promise.all(names.map(n => fetch(`data/${n}.json`, { cache: "no-store" }).then(r => { if (!r.ok) throw new Error(n + " " + r.status); return r.json(); })));
  names.forEach((n, i) => D[n] = res[i]);
  const cols = D.events.columns;
  D.ev = D.events.rows.map(r => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
  D.evById = Object.fromEntries(D.ev.map(e => [e.event_id, e]));
  D.playerById = Object.fromEntries(D.players.map(p => [p.player_id, p]));
  D.profById = {};
  D.profiles.forEach(p => { if (p.profile_type === "primary") D.profById[p.player_id] = p; });
  D.duration = D.match.duration_ms;
  D.home = D.match.teams[0]; D.away = D.match.teams[1];
  D.overlays.sort((a, b) => a.t_ms - b.t_ms);
  // measured live upgrade latency (fact card -> verified text), used to visualise the two-step captioning
  S.upgradeDelayMs = (D.narration.live && D.narration.live.upgrade_latency_s) ? Math.round(D.narration.live.upgrade_latency_s.median * 1000) : 0;
  init();
}

// ------------------------------------------------------------ helpers
function teamShort(x) { return D.match.team_short[x] || x; }
function pname(pid) { return (D.playerById[pid] || {}).name || pid || "–"; }
function clockStr(m, p) { return (p === 1 && m > 45) ? `45+${m - 45}'` : (p === 2 && m > 90) ? `90+${m - 90}'` : `${m}'`; }
function clockAt(tm) {
  let e = null;
  for (let i = D.ev.length - 1; i >= 0; i--) if (D.ev[i].timestamp_ms <= tm) { e = D.ev[i]; break; }
  if (!e) return { minute: 0, period: 1, clock: "0'", score: [0, 0], e: null };
  return { minute: e.minute, period: e.period, clock: clockStr(e.minute, e.period), score: [e.score_home, e.score_away], e };
}
function stateAt(tm) { let s = D.states[0]; for (const x of D.states) { if (x.t_ms <= tm) s = x; else break; } return s; }
function isTalent(pid) { return D.narration.focus_players.includes(pid); }
function star(pid) { return isTalent(pid) ? `<span class="star" title="${esc(t("star_legend"))}" aria-label="${esc(t("star_legend"))}">★</span> ` : ""; }

// ------------------------------------------------------------ init
function init() {
  $("#legendHome").textContent = teamShort(D.home); $("#legendAway").textContent = teamShort(D.away);
  $("#seek").max = D.duration;
  $$(".tabs button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#playBtn").addEventListener("click", togglePlay);
  $$(".speed button").forEach(b => b.addEventListener("click", () => setSpeed(+b.dataset.speed)));
  $("#seek").addEventListener("input", e => seek(+e.target.value));
  document.addEventListener("keydown", e => {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "Escape") { $("#helpModal").hidden = true; $("#guideModal").hidden = true; }
    if (e.code === "Space") { e.preventDefault(); togglePlay(); }
    if (e.key === "ArrowRight") seek(S.t + 60000); if (e.key === "ArrowLeft") seek(S.t - 60000);
  });
  $$(".seg").forEach(seg => seg.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    $$("button", seg).forEach(x => x.classList.toggle("on", x === b));
    S[seg.dataset.key] = b.dataset.v;
    if (seg.dataset.key === "lang") { applyI18n(); renderTimeline(); renderPlayer(); renderEvidence(); renderTraceMini(); renderTraceFull(); renderAgg(); }
    renderOverlays(true); renderRecap(); renderScouting();
  }));
  const sel = $("#focusSel");
  const talents = D.narration.focus_players;
  const g1 = document.createElement("optgroup"); g1.id = "focusGroupTalents"; sel.appendChild(g1);
  const g2 = document.createElement("optgroup"); g2.id = "focusGroupOthers"; sel.appendChild(g2);
  const addOpt = (grp, p, label) => { const o = document.createElement("option"); o.value = p; o.textContent = label; grp.appendChild(o); };
  talents.forEach(p => addOpt(g1, p, `★ ${pname(p)} (${teamShort(D.playerById[p].team_id)}, ${D.playerById[p].age})`));
  D.players.filter(p => !talents.includes(p.player_id) && D.match.lineups.some(l => l.player_id === p.player_id && l.on_ms !== "")).sort((a, b) => a.name.localeCompare(b.name))
    .forEach(p => addOpt(g2, p.player_id, `${p.name} (${teamShort(p.team_id)}, ${p.position})`));
  sel.addEventListener("change", () => { S.focus = sel.value; renderOverlays(true); });
  const ps = $("#playerSel");
  D.profiles.filter(p => p.profile_type === "primary").sort((a, b) => a.name.localeCompare(b.name)).forEach(p => { const o = document.createElement("option"); o.value = p.player_id; o.textContent = `${isTalent(p.player_id) ? "★ " : ""}${p.name} (${teamShort(p.team_id)}, ${p.position})`; ps.appendChild(o); });
  ps.addEventListener("change", () => { S.player = ps.value; renderPlayer(); });
  S.player = talents[0]; ps.value = S.player;
  $("#demoBtn").addEventListener("click", runDemo); $("#demoStop").addEventListener("click", stopDemo);
  $("#helpBtn").addEventListener("click", () => { $("#helpModal").hidden = false; $("#helpClose").focus(); });
  $("#helpClose").addEventListener("click", () => $("#helpModal").hidden = true);
  $("#guideClose").addEventListener("click", dismissGuide); $("#guideDismiss").addEventListener("click", dismissGuide);
  $("#guideDemo").addEventListener("click", () => { dismissGuide(); runDemo(); });
  $$(".modal").forEach(m => m.addEventListener("click", e => { if (e.target === m) m.hidden = true; }));
  applyI18n();
  drawPitchBase(); renderTimeline(); renderAgg(); renderRoleDiagram(); renderArch(); renderPlayer(); renderScouting(); renderRecap();
  seek(0); requestAnimationFrame(tick);
  let seen = false; try { seen = localStorage.getItem("scoutseye_guide_seen") === "1"; } catch (e) { /* storage blocked */ }
  if (!seen) $("#guideModal").hidden = false;
}
function dismissGuide() { $("#guideModal").hidden = true; try { localStorage.setItem("scoutseye_guide_seen", "1"); } catch (e) { /* ignore */ } }

function showTab(id) { $$(".tabs button").forEach(b => b.setAttribute("aria-selected", b.dataset.tab === id)); $$(".tab").forEach(x => x.classList.toggle("active", x.id === "tab-" + id)); if (id === "players") renderPlayer(); if (id === "agents") renderTraceFull(); }
function setSpeed(v) { S.speed = v; $$(".speed button").forEach(x => x.classList.toggle("on", +x.dataset.speed === v)); }
function setPlaying(v) { S.playing = v; $("#playBtn").textContent = v ? "❚❚" : "▶"; S.lastTick = performance.now(); }
function togglePlay() { setPlaying(!S.playing); }
function seek(tm) { S.t = Math.max(0, Math.min(D.duration, tm)); render(); }
function tick(now) {
  if (S.playing) { S.t += (now - S.lastTick) * S.speed; if (S.t >= D.duration) { S.t = D.duration; setPlaying(false); } render(); }
  S.lastTick = now; requestAnimationFrame(tick);
}

// ------------------------------------------------------------ render loop
let lastClock = "";
function render() {
  const c = clockAt(S.t);
  $("#clock").textContent = c.clock; $("#seek").value = S.t;
  $("#scoreboard").innerHTML = `<div class="t"><span class="sw home"></span>${esc(teamShort(D.home))}</div><div class="score">${c.score[0]} – ${c.score[1]}</div><div class="t">${esc(teamShort(D.away))}<span class="sw away"></span></div>`;
  drawPitchState(c);
  const cur = $(".timeline .cur"); if (cur) cur.style.left = (100 * S.t / D.duration) + "%";
  renderOverlays(false);
  if (c.e) $("#eventLine").textContent = `${c.clock} ${teamShort(c.e.team_id || "")} · ${c.e.type}${c.e.outcome ? " (" + c.e.outcome + ")" : ""} · ${pname(c.e.player_id)}${c.e.xg ? " · xG " + c.e.xg : ""}${evMetrics(c.e) ? " · " + evMetrics(c.e) : ""}`;
  if ($("#tab-players").classList.contains("active") && c.clock !== lastClock) renderPlayerLive();
  lastClock = c.clock;
}

// ------------------------------------------------------------ pitch
function drawPitchBase() {
  const svg = $("#pitch");
  const L = (x1, y1, x2, y2) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
  svg.innerHTML = `<g stroke="#d8f0e0" stroke-width=".35" fill="none" opacity=".9">
    <rect x="0.5" y="0.5" width="104" height="67"/>${L(52.5, 0.5, 52.5, 67.5)}<circle cx="52.5" cy="34" r="9.15"/>
    <rect x="0.5" y="13.84" width="16.5" height="40.32"/><rect x="88" y="13.84" width="16.5" height="40.32"/>
    <rect x="0.5" y="24.84" width="5.5" height="18.32"/><rect x="99" y="24.84" width="5.5" height="18.32"/>
    <circle cx="11" cy="34" r=".5" fill="#d8f0e0"/><circle cx="94" cy="34" r=".5" fill="#d8f0e0"/></g>
    <g id="path"></g><g id="cur"></g><g font-size="2.6" fill="#fff" opacity=".8"><text x="2" y="3.5">${esc(teamShort(D.home))} ⟶</text><text x="103" y="3.5" text-anchor="end">⟵ ${esc(teamShort(D.away))}</text></g>`;
}
function toPitch(e, team) {
  const flip = team === D.away;
  const f = (x, y) => flip ? [105 - x * 1.05, 68 - y * 0.68] : [x * 1.05, y * 0.68];
  return { s: f(e.x, e.y), t: (e.end_x !== null && e.end_x !== undefined) ? f(e.end_x, e.end_y) : null };
}
function drawPitchState(c) {
  const path = $("#path"), cur = $("#cur");
  if (!c.e) { path.innerHTML = ""; cur.innerHTML = ""; return; }
  const idx = D.ev.indexOf(c.e);
  const recent = [];
  for (let i = idx; i >= 0 && recent.length < 8; i--) { const e = D.ev[i]; if (["pass", "carry", "dribble", "shot", "corner", "free_kick", "throw_in", "clearance"].includes(e.type) && e.x !== null) recent.unshift(e); }
  path.innerHTML = recent.map((e, i) => { const p = toPitch(e, e.team_id); const col = e.team_id === D.home ? "#4aa3ff" : "#ff6b6b"; const o = 0.25 + 0.75 * (i + 1) / recent.length;
    return p.t ? `<line x1="${p.s[0]}" y1="${p.s[1]}" x2="${p.t[0]}" y2="${p.t[1]}" stroke="${col}" stroke-width="${e.type === "shot" ? 1 : 0.6}" opacity="${o}" ${e.type === "carry" ? 'stroke-dasharray="1 .8"' : ""}/>` : `<circle cx="${p.s[0]}" cy="${p.s[1]}" r=".8" fill="${col}" opacity="${o}"/>`; }).join("");
  const e = c.e; const p = e.x !== null ? toPitch(e, e.team_id) : null;
  const col = e.team_id === D.home ? "#4aa3ff" : (e.team_id === D.away ? "#ff6b6b" : "#fff");
  cur.innerHTML = p ? `<circle cx="${p.s[0]}" cy="${p.s[1]}" r="1.6" fill="#fff" stroke="${col}" stroke-width=".8"/><text x="${Math.min(p.s[0] + 2, 80)}" y="${Math.max(p.s[1] - 2, 4)}" font-size="2.6" fill="#fff">${esc(pname(e.player_id).split(" ").slice(-1)[0])} · ${esc(e.type)}${e.outcome === "goal" ? " ⚽" : ""}</text>` : "";
}

// ------------------------------------------------------------ timeline
function renderTimeline() {
  const tl = $("#timeline");
  tl.innerHTML = D.moments.filter(m => ["goal", "big_chance", "card", "momentum_shift", "milestone", "pressing_surge", "control_chaos_switch"].includes(m.type) && !(m.type === "card" && m.fact.card === "yellow"))
    .map(m => `<button class="mk ${m.type}" style="left:${100 * m.t_ms / D.duration}%" title="${esc(m.clock)} ${esc(m.type)}: ${esc(JSON.stringify(m.fact).slice(0, 80))}" data-t="${m.t_ms}" aria-label="${esc(m.clock)} ${esc(m.type)}"></button>`).join("") + `<div class="cur"></div>`;
  $$(".mk", tl).forEach(b => b.addEventListener("click", () => seek(+b.dataset.t - 500)));
}

// ------------------------------------------------------------ overlays (two-step: fact card, then verified text)
function overlayFilter(persona) {
  if (S.focus) return D.overlays.filter(o => o.lang === S.lang && o.focus_player === S.focus);
  return D.overlays.filter(o => o.lang === S.lang && o.persona === persona && o.club_view === S.club && !o.focus_player);
}
function phaseOf(o) { // "fact" while the agents are still working (measured upgrade latency), "verified" afterwards
  if (o.fallback) return "fallback";   // no verified text: the fact card stays
  const age = S.t - o.t_ms;
  const delay = S.upgradeDelayMs * Math.max(1, S.speed);
  return (o.fact_card && age < delay) ? "fact" : "verified";
}
function renderNoFocus(stage, feed) {
  const p = D.profById[S.focus];
  const key = "nofocus#" + S.focus + "#" + S.lang;
  if (stage.dataset.key === key) return;
  stage.dataset.key = key; feed.dataset.key = key;
  const msg = t("no_focus", { name: pname(S.focus), minutes: p ? p.minutes.toFixed(0) : "0", rel: p ? p.reliability : "–", low: (!p || p.ranking_status !== "ranked") ? t("low_data_note") : "" });
  stage.classList.remove("compare");
  stage.innerHTML = `<div class="card"><div>${esc(msg)}</div>${p ? `<button id="openFocusProfile" style="margin-top:8px">${esc(t("open_profile"))}</button>` : ""}</div>`;
  feed.innerHTML = "";
  $("#feedCount").textContent = t("shown_of", { n: 0, total: 0 });
  const b = $("#openFocusProfile"); if (b) b.onclick = () => { S.player = S.focus; showTab("players"); };
}
function renderOverlays(force) {
  const stage = $("#overlayStage"), feed = $("#feed");
  if (S.focus && !isTalent(S.focus)) { if (force) stage.dataset.key = ""; renderNoFocus(stage, feed); return; }
  const personas = S.persona === "compare" ? ["fan", "analyst"] : [S.persona];
  stage.classList.toggle("compare", S.persona === "compare");
  const visibleMs = 6000 * Math.max(1, S.speed) + S.upgradeDelayMs * Math.max(1, S.speed);
  let shown = [], all = [], total = 0;
  personas.forEach(p => {
    const list = overlayFilter(p); total += list.length;
    all = all.concat(list.filter(o => o.t_ms <= S.t));
    let vis = list.filter(o => o.t_ms <= S.t && S.t - o.t_ms <= visibleMs);
    const verifiedAt = new Set(vis.filter(o => !o.fallback).map(o => o.t_ms));
    vis = vis.filter(o => !o.fallback || !verifiedAt.has(o.t_ms));   // a fact-card fallback never hides a verified text of the same moment
    const latest = {}; vis.forEach(o => latest[o.layout] = o);
    shown = shown.concat(Object.values(latest).sort((a, b) => b.t_ms - a.t_ms).slice(0, 2));
  });
  const stageKey = shown.map(o => o.trace_key + ":" + phaseOf(o)).join("|") + "#" + S.selected + "#" + S.lang;
  if (force || stage.dataset.key !== stageKey) {
    stage.dataset.key = stageKey;
    stage.innerHTML = shown.length ? shown.map(o => ovHtml(o, true)).join("") : `<div class="muted">${esc(t("no_overlay", { clock: clockAt(S.t).clock }))}</div>`;
  } else if (!shown.length) {
    const m = stage.querySelector(".muted"); if (m) m.textContent = t("no_overlay", { clock: clockAt(S.t).clock });
  }
  all.sort((a, b) => b.t_ms - a.t_ms);
  const tg = tagsUntil(S.t);
  const feedKey = all.length + "#" + tg.length + "#" + (all[0] ? all[0].trace_key : "") + "#" + S.selected + "#" + S.lang;
  if (force || feed.dataset.key !== feedKey) {
    feed.dataset.key = feedKey;
    const items = all.map(o => ({ t: o.t_ms, h: ovHtml(o, false) })).concat(tg.map(x => ({ t: x.t_ms, h: tagHtml(x) })));
    items.sort((a, b) => b.t - a.t);
    feed.innerHTML = items.map(x => x.h).join("");
  }
  $("#feedCount").textContent = t("shown_of", { n: all.length, total });
  $$(".ov", stage).concat($$(".ov", feed)).forEach(el => { el.onclick = () => selectOverlay(el.dataset.key); el.onkeydown = e => { if (e.key === "Enter") selectOverlay(el.dataset.key); }; });
}
function ovHtml(o, big) {
  const sel = S.selected === o.trace_key ? " sel" : "";
  const fb = !!o.fallback;
  const fact = fb || (big && phaseOf(o) === "fact");
  const rec = o.status === "recovered" ? `<span class="tag rec" title="${esc(t("recovered_title"))}">↺ ${t("recovered")}</span>` : "";
  const badge = fb ? `<span class="tag fb" title="${esc(t("fallback_title"))}">${t("fallback")}</span>`
    : fact ? `<span class="tag fact">${t("fact_card")}</span>` : `<span class="tag ${o.verdict === "repaired" ? "warn" : "ok"}">${o.verdict === "repaired" ? t("repaired") : t("verified")}</span>${o.upgraded && o.fact_card ? `<span class="tag up">${t("upgraded")}</span>` : ""}${o.edited ? `<span class="tag ed" title="${esc(t("edited_title"))}">${t("edited")}</span>` : ""}${rec}`;
  const text = fb ? o.text : fact ? o.fact_card : o.text;
  return `<div class="ov ${esc(o.layout)}${sel}${fact ? " factcard" : ""}${fb ? " fallback" : ""}" data-key="${esc(o.trace_key)}" tabindex="0" role="button">
    <div class="meta"><span>${esc(o.clock)}</span><span>${esc(o.persona)}/${esc(o.lang)}</span><span>${esc(o.layout.replace("_", " "))}</span>${o.club_view !== "neutral" ? `<span>view: ${esc(teamShort(o.club_view))}</span>` : ""}${o.focus_player ? `<span>focus: ${star(o.focus_player)}${esc(pname(o.focus_player))}</span>` : ""}${badge}</div>
    <div class="txt">${esc(text)}</div>${big && !fact && o.detail ? `<div class="det">${esc(o.detail)}</div>` : ""}</div>`;
}
function evMetrics(e) {   // kpi/event_metrics.py, computed in build_site.py
  if (!e) return "";
  if (e.type === "pass" && e.pass_difficulty != null) return `${e.pass_length_m} m · ${t("difficulty")} ${e.pass_difficulty.toFixed(2)}${e.line_breaking ? " · " + t("line_breaking") : ""}${e.under_pressure ? " · under pressure" : ""} · ${e.ball_speed_kmh} km/h`;
  if (e.type === "shot" && e.ball_speed_kmh) return `${e.ball_speed_kmh} km/h${e.body_part ? " · " + e.body_part.replace("_", " ") : ""}`;
  if (e.ball_speed_kmh) return `${e.ball_speed_kmh} km/h`;
  return "";
}
function tagsUntil(tms) {
  const tags = (D.narration.tags || []).filter(x => x.t_ms <= tms);
  return S.focus ? tags.filter(x => x.player_id === S.focus) : tags;
}
function tagHtml(x) {
  return `<div class="ov tag-ov"><div class="meta"><span>${esc(x.clock)}</span><span class="tag tagd">${t("tag")}</span></div><div class="txt">${esc(S.lang === "hu" ? x.text_hu : x.text_en)}</div></div>`;
}
function selectOverlay(key) { S.selected = key; renderOverlays(true); renderEvidence(); renderTraceMini(); renderTraceFull(); }

// ------------------------------------------------------------ evidence
function renderEvidence() {
  const tr = D.trace[S.selected]; const el = $("#evidencePanel");
  if (!tr) { el.innerHTML = `<h3>${t("evidence")}</h3><div class='muted'>${t("select_overlay")}</div>`; return; }
  const evs = (tr.card.evidence || []).map(id => D.evById[id]).filter(Boolean);
  const rows = evs.map(e => `<tr><td>${esc(clockStr(e.minute, e.period))}</td><td><code>${esc(e.event_id)}</code></td><td>${esc(e.type)}${e.outcome ? " · " + esc(e.outcome) : ""}</td><td>${esc(pname(e.player_id))} (${esc(teamShort(e.team_id))})</td><td>${e.xg ? "xG " + e.xg : ""}</td><td>${esc(evMetrics(e))}</td></tr>`).join("");
  const data = Object.entries(tr.card.data || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "number" ? +v.toFixed(3) : JSON.stringify(v))}</dd>`).join("");
  const claims = tr.claims_now || tr.attempts.flatMap(a => a.claims);
  const ruleDesc = Object.fromEntries(D.narration.claim_rules.map(r => [r.id, r.description]));
  const claimsHtml = claims.length ? claims.map(c => `<div><span class="tag ${c.supported ? "ok" : "bad"}">${c.supported ? "supported" : "not supported"}</span><b>${esc(c.rule)}</b> – “${esc(c.matched)}” → ${esc(ruleDesc[c.rule] || "")}<div class="muted">evidence: ${esc(JSON.stringify(c.evidence)).slice(0, 220)}</div></div>`).join("") : "<div class='muted'>No claim rule matched this text.</div>";
  const a0 = tr.attempts[0]; const before = a0 ? a0.text : null, after = tr.final;
  const fbText = !after && tr.fact_card ? tr.fact_card.text : "";
  el.innerHTML = `<h3>${t("evidence")}: “${esc(after ? after.overlay : fbText)}”</h3>
    ${tr.status && tr.status !== "verified" ? `<div>${statusTag(tr)} <span class="muted">${esc(recoveryText(tr))}</span></div>` : ""}
    ${tr.fact_card ? `<div class="muted">${t("fact_card")}: <i>${esc(tr.fact_card.text)}</i></div>` : ""}
    <h4>Source events</h4><table><tr><th>clock</th><th>event</th><th>type</th><th>player</th><th></th><th>${t("metrics_title")}</th></tr>${rows || "<tr><td colspan=6 class='muted'>state card – derived from the state snapshot at " + esc(tr.clock) + "</td></tr>"}</table>
    <h4>Data fields used</h4><dl class="kv">${data || "<dd class='muted'>–</dd>"}</dl><div class="muted">source fields: ${esc((tr.card.source_fields || []).join(", "))}</div>
    <h4>Claim rules applied</h4>${claimsHtml}
    <h4>Verifier result</h4><div><span class="tag ${tr.verdict === "ok" ? "ok" : tr.verdict === "repaired" ? "warn" : "bad"}">${esc(tr.verdict)}</span> ${esc((tr.reasons || []).join("; "))}</div>
    ${!a0 ? `<div class='muted'>${S.lang === "hu" ? "Nem készült ellenőrizhető narrátor-szöveg; a ténykártya maradt." : "No narrator text reached the pre-check; the fact card stayed."}</div>` : (!a0.passed || tr.verdict === "repaired") ? `<div class="kv" style="margin-top:6px"><dt>before</dt><dd>${esc(before.overlay)} <span class="muted">/ ${esc(before.commentary)}</span></dd><dt>after</dt><dd>${esc(after ? after.overlay : "(dropped)")} <span class="muted">/ ${esc(after ? after.commentary : "")}</span></dd></div>` : "<div class='muted'>First draft passed the pre-check and the Verifier unchanged.</div>"}`;
}

// ------------------------------------------------------------ agent trace
function callMeta(c) {
  if (!c) return "";
  const rk = (c.retry_kinds || []).filter(k => k !== "rate_limit");
  const retry = rk.length ? `<span class="tag rec" title="retried after: ${esc(rk.join(", "))}">↺ retry ${rk.length}× (${esc([...new Set(rk)].join(", "))})</span>` : "";
  if (c.status === "failed") return `<span class="tag bad" title="${esc((c.failure && c.failure.detail) || "")}">failed: ${esc(c.failure ? c.failure.kind : "error")} after ${(c.retry_kinds || []).length} attempts</span>`;
  const bad = c.status === "invalid_json" ? `<span class="tag bad" title="the answer was not valid JSON">unreadable answer</span>` : "";
  if (c.cached) return `<span class="tag">cache hit</span><span class="tag">${c.tokens.total} tok</span>${bad}${retry}`;
  const w = (c.wait_429_s || 0) > 0 ? ((c.retries_429 || 0) > 0 ? `<span class="tag bad" title="HTTP 429 token-per-minute quota: ${c.retries_429} retry, ${c.wait_429_s}s waiting">429 wait ${c.wait_429_s}s · ${c.retries_429}×</span>` : `<span class="tag rec" title="time spent on failed attempts and back-off before the successful call">waited ${c.wait_429_s}s before retry</span>`) : "";
  const q = (c.queue_wait_s || 0) > 0.5 ? `<span class="tag" title="waiting for a concurrency slot">queue ${c.queue_wait_s}s</span>` : "";
  return `<span class="tag ok">LLM call ${c.call_latency_s ?? c.latency_s}s</span>${w}${q}${retry}${bad}<span class="tag">${c.tokens.total} tok</span>`;
}
function statusTag(tr) {
  if (tr.status === "fallback") return `<span class="tag fb" title="${esc(t("fallback_title"))}">${t("fallback")}</span>`;
  if (tr.status === "recovered") return `<span class="tag rec" title="${esc(t("recovered_title"))}">↺ ${t("recovered")}</span>`;
  return `<span class="tag ok">${t("verified")}</span>`;
}
function recoveryText(tr) { return (tr.recovery || []).map(x => `${x.agent}: ${x.kind}${x.action ? " → " + x.action : ""}`).join(" · "); }
function traceSteps(tr) {
  const calls = tr.calls || [];
  const byAgent = a => calls.filter(c => c.agent === a);
  const siblings = Object.entries(D.trace).filter(([k, x]) => x.item_id === tr.item_id);
  const steps = [];
  const live = D.narration.live;
  if (tr.fact_card) steps.push({ cls: "fact", agent: (S.lang === "hu" ? "Determinisztikus ténykártya (LLM nélkül)" : "Deterministic fact card (no LLM)"), io: `in: moment / state → template (${tr.fact_card.layer})` + (live && live.fact_card_benchmark ? ` · measured latency ≈ ${live.fact_card_benchmark.median_ms} ms (median of ${live.fact_card_benchmark.n})` : (live && live.fact_card_latency_s ? ` · measured live latency ${live.fact_card_latency_s.mean}s` : "")), out: esc(tr.fact_card.text) + (tr.fact_card.problems && tr.fact_card.problems.length ? " ⚠ " + esc(tr.fact_card.problems.join("; ")) : ""), call: null });
  steps.push({ cls: "", agent: "Match Analyst", io: `in: ${tr.kind === "moment" ? "moment + state window + tournament context" : "state snapshot at " + esc(tr.clock)} · reads shared state: ${esc(tr.facts_read.join(", "))}`, out: `insight card (${esc(tr.card.type)}): ${(tr.card.headline_facts || []).slice(0, 3).map(esc).join(" · ")}`, call: byAgent("analyst")[0] });
  const sc = byAgent("scout")[0];
  if (sc) steps.push({ cls: "", agent: "Scout", io: "in: baseline profile + live KPIs of the focus player", out: sc.status === "invalid_json" ? "unreadable answer – the Narrator wrote the focus text without the scout note" : "player-focus note with reliability label and low-data warning", call: sc });
  const nar = byAgent("narrator").filter(c => !c.repair);
  steps.push({ cls: "", agent: `Narrator – fan-out to ${siblings.length} variants`, io: "in: insight card (+ scout note), persona, language, club view / focus", out: "overlay ≤ 90 characters + commentary per variant (click a variant to follow its trace)", call: nar[0], fanout: siblings });
  const a0 = tr.attempts[0] || { bad_numbers: [], bad_names: [], claims: [], semantic: [], too_long: false, passed: false, missing: true };
  const prob = [...a0.bad_numbers.map(x => "number " + x), ...a0.bad_names.map(x => "name " + x), ...a0.claims.filter(c => !c.supported).map(c => "claim “" + c.matched + "”"), ...(a0.semantic || []), ...(a0.too_long ? ["overlay too long"] : [])];
  steps.push({ cls: a0.passed ? "" : "fail", agent: "Deterministic pre-check (no LLM)", io: "numbers · names · claim rules · goal direction · clock · venue · language", out: a0.missing ? "not reached (no narrator text)" : a0.passed ? "passed" : "FAILED: " + esc(prob.join(", ")), call: null });
  if (tr.attempts.length > 1) { const a1 = tr.attempts[1]; steps.push({ cls: "repair", agent: "Narrator – repair round (sent back once)", io: "in: previous text + the pre-check findings", out: (a1.passed ? "rewritten, pre-check passed: " : "rewritten, still failing: ") + esc(a1.text.overlay), call: byAgent("narrator").find(c => c.repair) }); }
  const ver = byAgent("verifier")[0];
  if (ver || tr.verdict === "reject") steps.push({ cls: tr.verdict === "reject" ? "fail" : "", agent: "Verifier (LLM)", io: "in: text + facts + pre-check findings", out: `${esc(tr.verdict)}${tr.reasons && tr.reasons.length ? ": " + esc(tr.reasons.join("; ")) : ""}`, call: ver });
  if (tr.recovery && tr.recovery.length) steps.push({ cls: tr.status === "fallback" ? "fail" : "repair", agent: `${t("recovery_title")} – ${tr.status === "fallback" ? "fallback" : "recovered"}`, io: "time limit, retries and back-off per call; a failing step is isolated, the run goes on", out: tr.recovery.map(x => `${statusTagSmall(x)} <b>${esc(x.agent)}</b>: ${esc(x.kind)}${x.action ? " → " + esc(x.action) : ""}`).join("<br>"), call: null });
  if (tr.edited) steps.push({ cls: "repair", agent: `${t("edited")} (no LLM, after verification)`, io: "replaced phrase checked by the full rule set (0 findings, none new) and read again by hand; the Verifier LLM saw the original text",
    out: tr.edited.replacements.map(x => `“${esc(x.old)}” → “${esc(x.new)}” (${esc(x.reason)})`).join("<br>"), call: null });
  steps.push({ cls: "final", agent: tr.final ? (tr.fact_card ? "Final overlay – replaces the fact card (same item id, flagged upgraded)" : "Final overlay (written to the feed)") : "Fallback – no verified text, the fact card stays on screen", io: "writes shared state: overlay text, evidence ids, data, verdict, trace id" + (live && live.upgrade_latency_s ? ` · measured live upgrade latency: median ${live.upgrade_latency_s.median}s` : ""), out: tr.final ? esc(tr.final.overlay) : (tr.fact_card ? esc(tr.fact_card.text) : "–"), call: null });
  steps.forEach((s, i) => s.n = i + 1);
  return steps;
}
function statusTagSmall(x) { return x.kind === "rejected" || x.action === "fact card stays" ? `<span class="tag fb">fallback</span>` : `<span class="tag rec">↺ recovered</span>`; }
function stepHtml(s) {
  const fan = s.fanout ? `<div class="fanout">${s.fanout.map(([k, x]) => `<span class="v${k === S.selected ? " sel" : ""}" data-key="${esc(k)}" tabindex="0">${x.status === "fallback" || x.verdict === "reject" ? "✗ " : x.status === "recovered" ? "↺ " : ""}${esc(k.split("|").slice(1).join("/").replace("/null", "").replace("/neutral", ""))}</span>`).join("")}</div>` : "";
  return `<div class="step ${s.cls}"><div class="dot">${s.n}</div><div class="box"><div class="h">${esc(s.agent)} ${callMeta(s.call)}</div><div class="muted">${s.io}</div><div>${s.out}</div>${fan}</div></div>`;
}
function renderTraceMini() {
  const tr = D.trace[S.selected]; const el = $("#tracePanelMini");
  if (!tr) return;
  el.innerHTML = `<h3>${t("trace_sel")} <span class="tag">${esc(tr.trace_id)}</span> ${statusTag(tr)}</h3><div class="trace">${traceSteps(tr).map(stepHtml).join("")}</div>`;
  $$(".fanout .v", el).forEach(v => v.addEventListener("click", () => selectOverlay(v.dataset.key)));
}
function renderTraceFull() {
  const tr = D.trace[S.selected]; const el = $("#traceFull");
  if (!tr) { el.innerHTML = `<div class='muted'>${t("select_overlay")}</div>`; return; }
  const calls = (tr.calls || []).map(c => `<tr><td>${esc(c.agent)}${c.repair ? " (repair)" : ""}</td><td>${c.persona ? esc(c.persona + "/" + c.lang) : ""}</td><td>${c.cached ? "cache" : "LLM"}</td><td>${c.cached ? "–" : (c.call_latency_s ?? c.latency_s) + "s"}</td><td>${c.cached ? "–" : ((c.wait_429_s || 0) > 0 ? `${c.wait_429_s}s (${(c.retry_kinds || []).join(", ") || c.retries_429 + "×"})` : "0")}</td><td>${c.tokens.input}/${c.tokens.output}</td></tr>`).join("");
  el.innerHTML = `<div class="muted">trace ${esc(tr.trace_id)} · item ${esc(tr.item_id)} · ${esc(tr.mode)} · ${esc(tr.clock)}</div><div>${statusTag(tr)} <span class="muted">${esc(recoveryText(tr))}</span></div><div class="trace">${traceSteps(tr).map(stepHtml).join("")}</div>
    <h3>LLM calls in this trace</h3><table><tr><th>agent</th><th>variant</th><th>source</th><th>latency</th><th>retry wait</th><th>tokens in/out</th></tr>${calls || "<tr><td colspan=6 class='muted'>no calls logged</td></tr>"}</table>
    <h3>Narrator drafts</h3>${tr.attempts.map(a => `<div class="box"><b>${esc(a.stage)}</b> <span class="tag ${a.passed ? "ok" : "bad"}">${a.passed ? "pre-check passed" : "pre-check failed"}</span><pre>${esc(a.text.overlay)}\n${esc(a.text.commentary)}</pre></div>`).join("")}`;
  $$(".fanout .v", el).forEach(v => v.addEventListener("click", () => selectOverlay(v.dataset.key)));
}
function renderAgg() {
  const v = D.narration.verifier, r = D.narration.run, st = D.narration.agent_stats || {}, live = D.narration.live;
  const rules = Object.keys(v.claims).map(k => `<tr><td>${esc(k)}</td><td>${v.claims[k] - (v.claims_unsupported[k] || 0)}</td><td>${v.claims_unsupported[k] || 0}</td></tr>`).join("");
  const agents = Object.entries(st).map(([a, s]) => `<tr><td>${esc(a)}</td><td>${s.calls}</td><td>${s.mean_call_latency_s}s</td><td>${s.mean_latency_s}s</td><td>${s.retries} / ${s.wait_429.toFixed(0)}s</td><td>${s.mean_tokens}</td></tr>`).join("");
  $("#traceAgg").innerHTML = `<div class="card"><dl class="kv"><dt>narration items</dt><dd>${r.items} (fan ${r.items_by_mode.fan}, analyst ${r.items_by_mode.analyst}, focus ${r.items_by_mode.focus})</dd>
    <dt>text variants</dt><dd>${v.items}</dd><dt>verified ok</dt><dd>${v.ok}</dd><dt>repaired by Verifier</dt><dd>${v.repaired}</dd><dt>rejected (fact card stays)</dt><dd>${v.rejected}</dd>
    <dt>first drafts failing pre-check</dt><dd>${v.precheck_failed} (semantic: ${v.semantic_failures})</dd><dt>LLM calls / cached (this run)</dt><dd>${r.llm_calls} / ${r.cached_calls}</dd>
    <dt>retries (this run)</dt><dd>${r.retries_429 ?? 0}</dd><dt>tokens / cost (this run)</dt><dd>${(r.tokens.total / 1e6).toFixed(2)} M ≈ $${r.cost_usd} · ${r.elapsed_s}s wall time <span class="muted">(one full uncached run with the shared calls: ${(r.tokens_full_run.total / 1e6).toFixed(2)} M ≈ $${r.cost_usd_full_run})</span></dd>
    ${live ? `<dt>live: fact card latency</dt><dd>${live.fact_card_benchmark ? `mean ${live.fact_card_benchmark.mean_ms} ms · median ${live.fact_card_benchmark.median_ms} ms · p95 ${live.fact_card_benchmark.p95_ms} ms (n=${live.fact_card_benchmark.n}, ${live.fact_card_benchmark.runs} replays)` : (live.fact_card_latency_s ? `mean ${live.fact_card_latency_s.mean}s (n=${live.fact_card_latency_s.n})` : "–")}</dd><dt>live: upgrade latency</dt><dd>${live.upgrade_latency_s ? `median ${live.upgrade_latency_s.median}s · mean ${live.upgrade_latency_s.mean}s · max ${live.upgrade_latency_s.max}s (n=${live.upgrade_latency_s.n})` : "–"}</dd>` : ""}</dl>
    <h3>Per agent (uncached calls of the committed run)</h3><table><tr><th>agent</th><th>calls</th><th>mean call latency</th><th>mean incl. retry waits</th><th>retries / wait</th><th>mean tokens</th></tr>${agents || "<tr><td colspan=6 class='muted'>no uncached calls in the committed run</td></tr>"}</table>
    <h3>Claim rules</h3><table><tr><th>rule</th><th>supported</th><th>unsupported</th></tr>${rules}</table></div>${comparisonHtml()}${recoveryHtml()}`;
}
function comparisonHtml() {
  const C = D.narration.comparison; if (!C) return "";
  const hu = S.lang === "hu";
  const name = { "single agent (1 call per text, no checks)": hu ? "1 ügynök (szövegenként 1 hívás, ellenőrzés nélkül)" : "single agent (1 call per text, no checks)",
    "five agents: Narrator first drafts (before the pre-check)": hu ? "5 ügynök: a Narrator első vázlatai (előszűrő előtt)" : "five agents: Narrator first drafts (before the pre-check)",
    "five agents: final on screen (verified text or fact card)": hu ? "5 ügynök: a képernyőn (igazolt szöveg vagy ténykártya)" : "five agents: final on screen (verified text or fact card)" };
  const cell = (n, tot) => `<td>${n}${tot ? ` <span class="muted">(${Math.round(100 * n / tot)}%)</span>` : ""}</td>`;
  const rows = C.rows.map(r => `<tr><td>${esc(name[r.arm] || r.arm)}</td>${cell(r.numbers, r.texts)}${cell(r.names, r.texts)}${cell(r.claims, r.texts)}${cell(r.goal + r.clock + r.venue, r.texts)}${cell(r.player || 0, r.texts)}${cell(r.wording || 0, r.texts)}${cell(r.any_error, r.texts)}<td>${r.calls ?? "–"}</td><td>${r.cost_usd != null ? "$" + r.cost_usd : "–"}</td><td>${r.llm_s_per_text != null ? r.llm_s_per_text + " s" : "–"}</td></tr>`).join("");
  const lim = hu ? ["mindhárom sort ugyanaz a determinisztikus ellenőrző pontozza, és az 5 ügynökös rendszer ezt belül is használja", "egy félidő, egy futás; az LLM kimenete futásonként változik", "minden sor azokhoz a tényekhez mérve, amelyeket kapott", "az ellenőrző csak azt látja, amire szabálya van (szám, név, állítás-szabály, gólirány, óra, helyszín, nyelv, ki van a pályán, szakszavak); a többit kézzel néztük át"] : C.limits;
  return `<div class="card" id="comparisonBox" style="margin-top:12px"><h3>${hu ? "1 ügynök vs. több ügynök" : "Single agent vs multi-agent"} – ${esc(C.segment)}, ${C.texts} ${hu ? "szöveg" : "texts"}</h3>
    <table><tr><th></th><th>${hu ? "igazolatlan szám" : "unverified numbers"}</th><th>${hu ? "rossz név" : "unknown names"}</th><th>${hu ? "alaptalan szakmai állítás" : "unsupported claims"}</th><th>${hu ? "gólirány / óra / hazai-vendég" : "goal direction / clock / home-away"}</th><th>${hu ? "poszt / nem játszik / pályán van-e" : "position / not in match / on the pitch"}</th><th>${hu ? "megfogalmazás (szakszó, mértékegység, arány, mutató)" : "wording (terms, units, shares, metrics)"}</th><th>${hu ? "bármilyen jelölés" : "any problem"}</th><th>${hu ? "hívás" : "calls"}</th><th>${hu ? "költség" : "cost"}</th><th>${hu ? "LLM-idő / szöveg" : "LLM time / text"}</th></tr>${rows}</table>
    ${manualHtml(C, hu)}
    <div class="muted">${hu ? "Korlátok" : "Limits"}: ${lim.map(esc).join(" · ")}. compare_agents.py</div></div>`;
}
function manualHtml(C, hu) {
  const M = C.manual_review; if (!M) return "";
  const a = C.rows.map(r => r.arm), fb = M.flagged_breakdown, ns = M.not_seen_by_the_checks;
  const f = (arm) => fb[arm] ? (hu ? `${fb[arm].flagged} jelölt: ${fb[arm].rule_violations} valódi szabálysértés, ${fb[arm].correct_but_untraceable_numbers} helyes, de nem visszakövethető szám, ${fb[arm].checker_false_positives} téves riasztás` : `${fb[arm].flagged} flagged: ${fb[arm].rule_violations} real rule violations, ${fb[arm].correct_but_untraceable_numbers} correct but untraceable numbers, ${fb[arm].checker_false_positives} checker false positives`) : "";
  const n = (arm) => ns[arm] ? (hu ? `${ns[arm].factual_errors} ténybeli hiba és ${ns[arm].garbled_sentences} értelmetlen mondat, amit az ellenőrző nem lát` : `${ns[arm].factual_errors} factual errors and ${ns[arm].garbled_sentences} garbled sentences the checks cannot see`) : "";
  return `<h3>${hu ? "Kézi átnézés (mind a 98 szöveg karonként)" : "Read by hand (all 98 texts of each arm)"}</h3><ul class="muted">
    <li><b>${hu ? "1 ügynök" : "single agent"}</b>: ${esc(f(a[0]))}; ${esc(n(a[0]))}.</li>
    <li><b>${hu ? "5 ügynök, első vázlatok" : "five agents, first drafts"}</b>: ${esc(f(a[1]))}.</li>
    <li><b>${hu ? "5 ügynök, képernyőn" : "five agents, on screen"}</b>: ${esc(n(a[2]))}${(() => { const x = ns[a[2]] || {}; const ex = (hu ? x.examples_hu : x.examples) || x.examples || []; return ex.length ? " – " + esc(ex.slice(0, 3).join("; ")) : ""; })()}.</li>
    <li>${hu ? "Eredmény: az 5 ügynök minden, az ellenőrző által látható hibát kiszűr (ez része a folyamatnak), kb. kétszeres költséggel és idővel; az ellenőrzőn kívüli hibák mindkét oldalon maradnak, és a kézi átnézés találta meg az új szabályokat." : "Result: the five agents remove every problem the checks can see (the checks are part of the pipeline) at about twice the cost and time; errors outside the checks remain in both arms, and the hand review is what found the new rules."}</li></ul>`;
}
function recoveryHtml() {
  const R = D.narration.recovery; if (!R) return "";
  const hu = S.lang === "hu";
  const st = (R.run && R.run.status) || {};
  const kinds = Object.entries((R.run && R.run.recovery) || {}).map(([k, n]) => `<tr><td>${esc(k.split(":")[0])}</td><td>${esc(k.split(":")[1])}</td><td>${n}</td></tr>`).join("");
  const T = R.test;
  const rows = T ? T.rows.map((r, i) => `<tr><td>${i + 1}</td><td>${esc(r.scenario)}</td><td>${esc(r.fault)}</td><td>${esc(r.expected)}</td><td>${Object.entries(r.affected).map(([k, n]) => `${esc(k)} ${n}`).join(", ") || "–"}</td><td><span class="tag ${r.passed ? "ok" : "bad"}">${r.passed ? "PASS" : "FAIL"}</span></td></tr>`).join("") : "";
  return `<div class="card" id="recoveryBox" style="margin-top:12px"><h3>${t("recovery_title")}</h3>
    <div class="muted">${hu ? `Minden ügynökhívásnak ${R.timeout_s} mp időkorlátja van; időtúllépésnél, 429-nél és szolgáltatáshibánál visszalépéssel újrapróbál. Ami ezután is hibás, az csak a saját lépését érinti: az Analyst helyett determinisztikus elemzőkártya, a Narrator / Verifier helyett a ténykártya marad. A futás megy tovább.` : `Every agent call has a ${R.timeout_s} s time limit and retries with back-off on timeout, HTTP 429 and service errors. Whatever still fails is isolated to its own step: a deterministic insight card replaces the Analyst, the fact card stays in place of the Narrator / Verifier text. The run goes on.`}</div>
    <dl class="kv" style="margin-top:6px"><dt>${hu ? "commitolt futás" : "committed run"}</dt><dd><span class="tag ok">verified ${st.verified || 0}</span><span class="tag rec">↺ recovered ${st.recovered || 0}</span><span class="tag fb">fallback ${st.fallback || 0}</span></dd>
    <dt>${hu ? "ténykártya a helyén" : "fact cards kept on screen"}</dt><dd>${R.fallbacks_shown}</dd></dl>
    ${kinds ? `<table><tr><th>agent / step</th><th>${hu ? "mi történt" : "what happened"}</th><th>n</th></tr>${kinds}</table>` : ""}
    ${T ? `<h3>${hu ? `Hibainjektálásos teszt (ál-modell, Azure és költség nélkül): ${T.passed}/${T.total} PASS` : `Fault-injection test (fake model, no Azure, no cost): ${T.passed}/${T.total} PASS`}</h3>
    <table><tr><th>#</th><th>scenario</th><th>${hu ? "beinjektált hiba" : "injected fault"}</th><th>${hu ? "mit tett a rendszer" : "what the system did"}</th><th>${hu ? "érintett" : "affected"}</th><th></th></tr>${rows}</table>
    <div class="muted">tests/test_failure_recovery.py · ${hu ? `tesztben ${T.timeout_s} mp időkorlát, a várakozások ×${T.backoff_scale}` : `time limit in the test ${T.timeout_s} s, back-off ×${T.backoff_scale}`}</div>` : ""}</div>`;
}
function renderRoleDiagram() {
  const boxes = [["Fact card (no LLM)", 10, "#2a2410", "#f2b134"], ["Match Analyst", 160, "#163a33", "#19c3a5"], ["Scout", 310, "#163a33", "#19c3a5"], ["Narrator ×N", 460, "#163a33", "#19c3a5"], ["Verifier", 610, "#163a33", "#19c3a5"]].map(([n, x, f, s]) => `<rect x="${x}" y="130" width="130" height="44" rx="8" fill="${f}" stroke="${s}"/><text x="${x + 65}" y="157" text-anchor="middle" font-weight="700">${n}</text>`).join("");
  $("#roleDiagram").innerHTML = `<svg viewBox="0 0 760 300" role="img" aria-label="Agent roles and shared state">
  <defs><marker id="ar" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#9fb0bf"/></marker></defs>
  <g font-size="12" fill="#e8eef3" font-family="system-ui">
  <rect x="10" y="20" width="740" height="60" rx="8" fill="#1d2631" stroke="#19c3a5"/><text x="20" y="40" font-weight="700">Shared state (facts)</text><text x="20" y="60" fill="#9fb0bf">moments · state by minute · profiles · team KPIs · tournament table · fact cards · insight cards · verdicts · overlays</text>
  ${boxes}
  <rect x="385" y="230" width="150" height="44" rx="8" fill="#2a2410" stroke="#f2b134"/><text x="460" y="257" text-anchor="middle" font-weight="700">Recap</text>
  <g stroke="#9fb0bf" stroke-width="1.5" fill="none" marker-end="url(#ar)"><path d="M75,130 V80"/><path d="M225,130 V80"/><path d="M375,130 V80"/><path d="M525,130 V80"/><path d="M675,130 V80"/><path d="M140,152 H160"/><path d="M290,152 H310"/><path d="M440,152 H460"/><path d="M590,152 H610"/><path d="M640,174 C620,215 560,215 535,250"/><path d="M610,160 C570,200 520,200 480,230" stroke-dasharray="4 3"/></g>
  <text x="540" y="215" fill="#f2b134" font-size="11">repair ↩ (once)</text><text x="20" y="290" fill="#9fb0bf" font-size="11">two-step live captioning: the fact card appears first (ms), the verified agent text replaces it (same id, "upgraded"); failures recover through one repair round, otherwise the fact card stays</text>
  </g></svg>`;
}
function renderArch() {
  const boxes = [["Synthetic events", "generate.py · seed", 10], ["KPIs & profiles", "run_kpis.py · PAdj · percentiles", 160], ["Live engine", "moments · windows · momentum", 310], ["Agents on Foundry", "Agent Framework workflow", 460], ["Verified overlays", "fact card → pre-check · Verifier", 610], ["This site", "static · offline · no Azure", 760]]
    .map(([a, s, x]) => `<rect x="${x}" y="40" width="130" height="70" rx="8" fill="#1d2631" stroke="#19c3a5"/><text x="${x + 65}" y="68" text-anchor="middle" font-weight="700">${a}</text><text x="${x + 65}" y="90" text-anchor="middle" fill="#9fb0bf" font-size="10">${s}</text>`).join("");
  $("#arch").innerHTML = `<svg viewBox="0 0 900 170" role="img" aria-label="Architecture"><g font-size="12" fill="#e8eef3" font-family="system-ui">${boxes}
  <g stroke="#9fb0bf" stroke-width="1.5" fill="none">${[140, 290, 440, 590, 740].map(x => `<path d="M${x},75 H${x + 20}"/>`).join("")}</g>
  <text x="10" y="150" fill="#9fb0bf" font-size="11">Microsoft Foundry hosts gpt-4.1-mini; the Microsoft Agent Framework orchestrates the five agents; authentication is az login (no keys); the site only reads exported files.</text></g></svg>`;
}

// ------------------------------------------------------------ players
const CAT_LABEL = { hu: { finishing: "Befejezés", goal_contribution: "Gólhozzájárulás", chance_creation: "Helyzetkialakítás", passing: "Passzolás", progression: "Progresszió", offensive_duels: "Támadó párharc", defensive_duels: "Védőpárharc", aerial_play: "Fejjáték", defensive_activity: "Védekező aktivitás", pressing: "Pressing", physical: "Fizikai" },
                    en: { finishing: "Finishing", goal_contribution: "Goal contribution", chance_creation: "Chance creation", passing: "Passing", progression: "Progression", offensive_duels: "Offensive duels", defensive_duels: "Defensive duels", aerial_play: "Aerial play", defensive_activity: "Defensive activity", pressing: "Pressing", physical: "Physical" } };
function profileCard(p, title) {
  const bars = Object.entries(p.cats).map(([k, v]) => `<div class="bar ${v >= 75 ? "high" : v <= 30 ? "low" : ""}"><span>${esc(CAT_LABEL[S.lang][k] || k)}</span><div class="track"><div class="fill" style="width:${v}%"></div></div><span>${v.toFixed(0)}</span></div>`).join("");
  const low = p.ranking_status !== "ranked";
  const val = p.gt_rank ? `<span class="tag val" title="${esc(t("validation_legend"))}">${t("validation", { r: p.gt_rank, n: p.rank_of || "–" })}</span>` : "";
  return `<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px"><div>${star(p.player_id)}<b>${esc(p.name)}</b> <span class="muted">${esc(teamShort(p.team_id))} · ${esc(p.position)} · ${S.lang === "hu" ? "kor" : "age"} ${p.age}</span></div><div class="big">${p.score.toFixed(1)}</div></div>
    <div>${low ? `<span class="tag low">${t("low_data_min", { m: p.minutes.toFixed(0) })}</span>` : `<span class="tag ok">${t("rank", { r: p.rank, n: p.rank_of, pos: p.position })}</span>`} ${val} <span class="tag">${t("min_matches", { m: p.minutes.toFixed(0), n: p.matches })}</span> <span class="tag">${t("reliability")}: ${esc(p.reliability)}</span> ${title ? `<span class="tag warn">${esc(title)}</span>` : ""}</div>
    ${p.before && p.before.minutes !== p.minutes ? `<div class="muted" style="margin-top:6px">${esc(t("before_match", { m: S.lang === "hu" ? p.before.minutes.toFixed(1).replace(".", ",") : p.before.minutes.toFixed(1), n: p.before.matches, rel: (S.lang === "hu" ? "megbízhatóság: " : "reliability: ") + p.before.reliability, rank: p.before.ranking_status !== "ranked" ? t("not_ranked") : "", s: S.lang === "hu" ? p.before.score.toFixed(1).replace(".", ",") : p.before.score.toFixed(1) }))}</div>` : ""}
    <div class="bars" style="margin-top:8px">${bars}</div>
    <div class="muted" style="margin-top:6px">+ ${esc(p.strengths.replace(/;/g, ", "))} · − ${esc(p.weaknesses.replace(/;/g, ", "))} · ${p.fouls} fouls, ${p.yellow} yellow, ${p.red} red</div></div>`;
}
function renderPlayer() {
  const pid = S.player; $("#playerSel").value = pid;
  const prim = D.profById[pid]; const sec = D.profiles.find(p => p.player_id === pid && p.profile_type === "secondary");
  $("#playerCard").innerHTML = prim ? profileCard(prim, isTalent(pid) ? t("young_focus") : "") + (sec ? profileCard(sec, t("secondary")) : "") : "<div class='muted'>No outfield profile.</div>";
  renderPlayerLive();
}
// why a player has no live KPIs at this moment: line-ups and substitutions (the replay knows the whole match, the agents only the past)
function pitchStatus(pid, tms, clock) {
  const name = pname(pid), l = D.match.lineups.find(x => x.player_id === pid);
  const p = D.playerById[pid] || {};
  if (!l && !D.match.teams.includes(p.team_id)) return t("pitch_other_team", { name });
  const at = ms => { const e = D.ev.find(x => x.type === "substitution" && x.timestamp_ms === ms); return e ? clockStr(e.minute, e.period) : ""; };
  if (!l || l.on_ms === "") return t("pitch_bench_never", { name, clock, why: l ? l.status : "–" });
  if (tms < +l.on_ms) return t("pitch_bench", { name, clock, on: at(+l.on_ms) });
  if (l.off_ms !== "" && tms >= +l.off_ms && +l.off_ms < D.duration - 1000) return t("pitch_off", { name, off: at(+l.off_ms) });
  return t("not_on_pitch", { name, clock });
}
function renderPlayerLive() {
  const s = stateAt(S.t); const pl = s.players.find(p => p.player_id === S.player);
  const el = $("#playerLive");
  if (!pl) { el.innerHTML = `<div class="muted">${esc(pitchStatus(S.player, S.t, s.clock))}</div>`; return; }
  const tot = Object.entries(pl.totals || {}).map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${v}</dd>`).join("");
  // deterministic event metrics of this player up to the clock (kpi/event_metrics.py)
  const mine = D.ev.filter(e => e.player_id === S.player && e.timestamp_ms <= S.t);
  const shots = mine.filter(e => e.type === "shot" && e.ball_speed_kmh);
  const fast = shots.length ? shots.reduce((a, b) => (b.ball_speed_kmh > a.ball_speed_kmh ? b : a)) : null;
  const done = mine.filter(e => e.type === "pass" && e.outcome === "success" && e.pass_difficulty != null);
  const hard = done.length ? done.reduce((a, b) => (b.pass_difficulty > a.pass_difficulty ? b : a)) : null;
  const lb = done.filter(e => e.line_breaking).length;
  const tg = (D.narration.tags || []).filter(x => x.player_id === S.player && x.t_ms <= S.t);
  const met = `<dt>${t("fastest_shot")}</dt><dd>${fast ? `${fast.ball_speed_kmh} km/h (${esc(clockStr(fast.minute, fast.period))})` : "–"}</dd>
    <dt>${t("hardest_pass")}</dt><dd>${hard ? `${hard.pass_difficulty.toFixed(2)} · ${hard.pass_length_m} m (${esc(clockStr(hard.minute, hard.period))})` : "–"}</dd>
    <dt>${t("line_breaking_passes")}</dt><dd>${lb}</dd>${tg.length ? `<dt>${t("tags_title")}</dt><dd>${tg.map(x => esc(S.lang === "hu" ? x.text_hu : x.text_en)).join("<br>")}</dd>` : ""}`;
  el.innerHTML = `<dl class="kv"><dt>${t("clock")}</dt><dd>${esc(s.clock)}</dd><dt>${t("minutes_played")}</dt><dd>${pl.minutes}</dd><dt>${t("live_score")}</dt><dd>${pl.score ?? "–"} <span class="tag ${pl.ranking_status === "ranked" ? "warn" : "low"}">${pl.ranking_status === "ranked" ? t("live_reliab") : t("live_low")}</span></dd>${met}${tot}</dl>`;
}

// ------------------------------------------------------------ scouting
function renderScouting() {
  const talents = D.narration.focus_players;
  $("#talents").innerHTML = talents.map(pid => { const p = D.profById[pid]; if (!p) return ""; return `<div class="talent" data-pid="${pid}" tabindex="0" role="button"><b>${star(pid)}${esc(p.name)}</b> <span class="muted">${esc(teamShort(p.team_id))} · ${esc(p.position)} · ${S.lang === "hu" ? "kor" : "age"} ${p.age}</span><div class="big">${p.score.toFixed(1)}</div><div>${p.ranking_status === "ranked" ? `${S.lang === "hu" ? "modell-rang" : "model rank"} ${p.rank}/${p.rank_of}` : `<span class="tag low">${t("low_data")}</span>`}${p.gt_rank ? ` · <span class="tag val" title="${esc(t("validation_legend"))}">Validation: ${p.gt_rank}/${p.rank_of || "–"}</span>` : ""}</div><div class="muted">${p.minutes.toFixed(0)} min · ${esc(p.reliability)} · ${esc(p.strengths.replace(/;/g, ", "))}</div></div>`; }).join("");
  $$(".talent").forEach(x => x.addEventListener("click", () => { S.player = x.dataset.pid; showTab("players"); }));
  const pos = ["CB", "FB", "DM", "CM", "AM", "W", "ST"];
  $("#rankings").innerHTML = pos.map(g => { const ranked = D.profiles.filter(p => p.profile_type === "primary" && p.position === g && p.ranking_status === "ranked").sort((a, b) => a.rank - b.rank);
    const low = D.profiles.filter(p => p.profile_type === "primary" && p.position === g && p.ranking_status !== "ranked");
    return `<div class="card"><b>${g}</b><ol>${ranked.map(p => `<li class="${talents.includes(p.player_id) ? "hl" : ""}">${star(p.player_id)}${esc(p.name)} <span class="muted">${p.score.toFixed(1)} · ${p.minutes.toFixed(0)}′</span></li>`).join("")}</ol>${low.length ? `<div class="muted">${t("low_data")}: ${low.map(p => esc(p.name) + " (" + p.minutes.toFixed(0) + "′)").join(", ")}</div>` : ""}</div>`; }).join("");
  $("#notesHu").innerHTML = md(D.narration.texts.scouting_notes_hu || ""); $("#notesEn").innerHTML = md(D.narration.texts.scouting_notes_en || "");
}
function renderRecap() {
  const k = `M12_recap_${S.recapPersona}_${S.recapLang}`;
  const text = D.narration.texts[k] || "";
  const ed = ((D.narration.run || {}).targeted_edits || []).filter(e => e.file.endsWith(`${k}.md`) && text.includes(e.new) && !text.includes(e.old));
  const note = ed.length ? `<div class="muted" style="margin-bottom:8px"><span class="tag ed">${t("edited")}</span> ${esc(t("recap_edited", { n: ed.length }))}<ul>${ed.map(e => `<li>“${esc(e.old)}” → “${esc(e.new)}”</li>`).join("")}</ul></div>` : "";
  $("#recap").innerHTML = note + md(text || "(missing)");
}

// ------------------------------------------------------------ tiny markdown
function md(src) {
  const lines = src.split("\n"); const out = []; let inTable = false, inList = false, inOl = false;
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/&lt;sub&gt;(.*?)&lt;\/sub&gt;/g, "<sub>$1</sub>");
  for (const raw of lines) {
    const l = raw.trimEnd();
    if (/^\|/.test(l)) { if (/^\|\s*-+/.test(l)) continue; const cells = l.split("|").slice(1, -1); if (!inTable) { out.push("<table>"); inTable = true; out.push("<tr>" + cells.map(c => `<th>${inline(c.trim())}</th>`).join("") + "</tr>"); } else out.push("<tr>" + cells.map(c => `<td>${inline(c.trim())}</td>`).join("") + "</tr>"); continue; }
    if (inTable) { out.push("</table>"); inTable = false; }
    if (/^\s*[-*] /.test(l)) { if (!inList) { out.push("<ul>"); inList = true; } out.push(`<li>${inline(l.replace(/^\s*[-*] /, ""))}</li>`); continue; }
    if (inList) { out.push("</ul>"); inList = false; }
    if (/^\s*\d+\. /.test(l)) { if (!inOl) { out.push("<ol>"); inOl = true; } out.push(`<li>${inline(l.replace(/^\s*\d+\. /, ""))}</li>`); continue; }
    if (inOl) { out.push("</ol>"); inOl = false; }
    const h = l.match(/^(#{1,4}) (.*)/); if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (l === "---") { out.push("<hr>"); continue; }
    if (l.trim()) out.push(`<p>${inline(l)}</p>`);
  }
  if (inTable) out.push("</table>"); if (inList) out.push("</ul>"); if (inOl) out.push("</ol>");
  return out.join("\n");
}

// ------------------------------------------------------------ demo script (≈ 90 s)
let demoTimer = null, demoInner = null;
function setMode(persona, lang2, club) { S.persona = persona; S.club = club; $$(".seg[data-key=persona] button").forEach(b => b.classList.toggle("on", b.dataset.v === persona)); $$(".seg[data-key=club] button").forEach(b => b.classList.toggle("on", b.dataset.v === club)); if (lang2 !== S.lang) { S.lang = lang2; applyI18n(); renderScouting(); } }
function setFocus(pid) { S.focus = pid; $("#focusSel").value = pid; }
function runDemo() {
  const goals = D.moments.filter(m => m.type === "goal"); const goal2 = goals[0], winner = goals[goals.length - 1];
  // step 4: a text the pre-check sent back because of an unsupported claim (the narration says so), else any repair round
  const repairedBy = claim => D.overlays.find(o => !o.fallback && o.lang === "en" && o.club_view === "neutral" && !o.focus_player && D.trace[o.trace_key]
      && D.trace[o.trace_key].attempts.length > 1 && (!claim || D.trace[o.trace_key].attempts[0].claims.some(c => !c.supported)));
  const repaired = repairedBy(true) || repairedBy(false) || D.overlays.find(o => o.verdict === "repaired") || D.overlays[0];
  const talent = D.narration.focus_players[0];
  const lowData = o => /low data|low-data|low reliability/i.test(o.text + " " + o.detail) && !/\btop\b|\bbest\b|elite|outstanding|standout/i.test(o.text + " " + o.detail);
  const talentOverlays = D.overlays.filter(o => !o.fallback && o.focus_player === talent && o.lang === "en" && lowData(o) && o.t_ms < winner.t_ms);
  const backed = o => !o.fallback && o.lang === "en" && o.club_view === "neutral" && !o.focus_player && D.trace[o.trace_key]
      && (D.trace[o.trace_key].claims_now || []).some(c => c.rule === "dominance" && c.supported);
  const claimOv = D.overlays.find(o => backed(o) && o.kind === "state") || D.overlays.find(backed)
    || D.overlays.find(x => !x.fallback && x.t_ms === goal2.t_ms && x.lang === "en" && x.persona === "analyst" && x.club_view === "neutral" && !x.focus_player);
  const talentT = talentOverlays.length ? talentOverlays[talentOverlays.length - 1].t_ms + 1000 : winner.t_ms - 5000;
  const msgs = {
    hu: ["1/6 · Korai gól: a címdöntő 2' gólja – ténykártya azonnal, majd a szurkolói felirat", "2/6 · Elemzői és szurkolói egymás mellett (angolul): ugyanazok az igazolt tények, két persona", "3/6 · Bizonyíték: egy felirat → forrás-események, adatmezők, az állítás-szabály (pl. „uralja” → field tilt ≥ 58 %), Verifier-eredmény", "4/6 · Ügynök-nyomkövetés Verifier-javítással: Analyst → Narrator-változatok → előszűrő elbukik → javítás → Verifier → végső", "5/6 · Játékosfókusz egy ★ fiatal tehetségen: még a kispadon ül, és a szöveg ezt mondja; kevés adat, profil megbízhatósággal", "6/6 · A 49' győztes gól és a cím: eredményjelző-felirat, majd az összefoglaló megnevezi a tornagyőztest"],
    en: ["1/6 · Early goal: the title decider opens with a 2' goal – fact card instantly, then the fan overlay", "2/6 · Analyst vs Fan side by side (English): the same verified facts, two personas", "3/6 · Evidence: an overlay → source events, data fields, the claim rule behind it (e.g. \"controls\" → field tilt ≥ 58 %), Verifier result", "4/6 · Agent trace with a Verifier repair: Analyst → Narrator fan-out → pre-check fails → repair → Verifier → final", "5/6 · Player focus on a ★ young talent: still on the bench, and the text says so; low data, profile with reliability", "6/6 · The 49' winner and the title: scorebug note, then the recap names the tournament winner"],
  };
  const steps = [
    { d: 12, do: () => { showTab("match"); setFocus(""); setMode("fan", "en", "neutral"); setSpeed(10); seek(goal2.t_ms - 20000); setPlaying(true);
        // the fact card appears with the goal; then jump past the measured upgrade delay so that the verified text replaces it in this step
        demoInner = setTimeout(() => { seek(goal2.t_ms + S.upgradeDelayMs * 10 + 1500); }, 6000); } },
    { d: 14, do: () => { setPlaying(false); setMode("compare", "en", "neutral"); seek(goal2.t_ms + 2000 + S.upgradeDelayMs * 10); } },
    { d: 16, do: () => { const o = claimOv; if (o) { setMode(o.persona, "en", "neutral"); setSpeed(1); seek(o.t_ms + S.upgradeDelayMs + 1500); selectOverlay(o.trace_key); }
        const h = [...$$("#evidencePanel h4")].find(x => /claim/i.test(x.textContent)); (h || $("#evidencePanel")).scrollIntoView({ behavior: "smooth", block: "center" }); $("#evidencePanel").classList.add("hl-pulse"); } },
    { d: 18, do: () => { selectOverlay(repaired.trace_key); showTab("agents"); window.scrollTo({ top: 0, behavior: "smooth" }); } },
    { d: 14, do: () => { showTab("match"); setMode("analyst", "en", "neutral"); setFocus(talent); S.player = talent; setSpeed(10); seek(talentT + S.upgradeDelayMs * 10); window.scrollTo({ top: 0, behavior: "smooth" });
        demoInner = setTimeout(() => { showTab("players"); renderPlayer(); window.scrollTo({ top: 0, behavior: "smooth" }); }, 7000); } },
    { d: 16, do: () => { showTab("match"); window.scrollTo({ top: 0, behavior: "smooth" }); setFocus(""); setMode("fan", "en", "neutral"); setSpeed(1); seek(winner.t_ms - 3000); setPlaying(true);
        // the fact card appears with the goal; then jump past the measured upgrade delay so the verified text is on screen
        demoInner = setTimeout(() => { seek(winner.t_ms + S.upgradeDelayMs + 800); demoInner = setTimeout(() => { setPlaying(false); showTab("recap"); S.recapPersona = "fan"; S.recapLang = "en"; $$(".seg[data-key=recapPersona] button").forEach(b => b.classList.toggle("on", b.dataset.v === "fan")); $$(".seg[data-key=recapLang] button").forEach(b => b.classList.toggle("on", b.dataset.v === "en")); renderRecap(); }, 5000); }, 6000); } },
  ];
  stopDemo(); $("#demoOverlay").hidden = false; $("#guideModal").hidden = true;
  let i = 0;
  const run = () => { if (i >= steps.length) { $("#demoStep").textContent = S.lang === "hu" ? "A demó véget ért (≈ 90 mp)" : "Demo finished (≈ 90 s)"; demoTimer = setTimeout(stopDemo, 4000); return; } const s = steps[i]; const lang0 = S.lang; s.do(); $("#demoStep").textContent = msgs[S.lang === "hu" ? "hu" : "en"][i]; i++; demoTimer = setTimeout(run, s.d * 1000); };
  run();
}
function stopDemo() { if (demoTimer) clearTimeout(demoTimer); if (demoInner) clearTimeout(demoInner); demoTimer = demoInner = null; $("#demoOverlay").hidden = true; }
window.scoutsEye = { S, D, seek, showTab, selectOverlay, runDemo, setMode, setFocus, setPlaying, dismissGuide };

load().catch(e => { document.body.insertAdjacentHTML("afterbegin", `<div class="banner">Failed to load data: ${esc(e.message)}. Serve the site folder over HTTP (e.g. python -m http.server) – browsers block fetch() on file://.</div>`); console.error(e); });
})();
