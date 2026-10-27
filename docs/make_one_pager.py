#!/usr/bin/env python3
"""One-page PDF summary (English) with two screenshots -> docs/one_pager.pdf"""

import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

m = json.load(open("data/narration/run_metadata.json"))
live = json.load(open("data/narration/live_run_summary.json"))
DEMO, REPO = "https://calm-pond-0e514280f.3.azurestaticapps.net", "https://github.com/laczmartin/scouts-eye"
TEAL = colors.HexColor("#11998e")
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=TEAL)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=5, spaceAfter=2, textColor=colors.HexColor("#1b3a4b"))
P = ParagraphStyle("p", fontName="Helvetica", fontSize=8.6, leading=11)
B = ParagraphStyle("b", parent=P, leftIndent=8, bulletIndent=0)
doc = SimpleDocTemplate("docs/one_pager.pdf", pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=10 * mm,
                        title="Scout's Eye – Explainable U19 Match Intelligence", author="Laczkovics Martin")
S = []
S.append(Paragraph("Scout's Eye – Explainable U19 Match Intelligence", H1))
S.append(Paragraph("Multi-agent, verified live narration of a synthetic U19 title decider on Microsoft Foundry: every number traceable to an event, every sentence checked before it is shown.", P))
S.append(Paragraph("Laczkovics Martin · github.com/laczmartin/scouts-eye · MIT licence", ParagraphStyle("by", parent=P, textColor=colors.grey)))
S.append(Spacer(1, 4))
left = []
left.append(Paragraph("The problem", H2))
left.append(Paragraph("Broadcast and scouting content from youth football is either generic or unverifiable. Language models write fluent commentary but invent numbers, misread the clock and overstate claims; and youth data is small and noisy, so rankings need honest reliability labels.", P))
left.append(Paragraph("How it works", H2))
for t in ["<b>Synthetic events.</b> A possession-chain simulator generates a 4-team, 12-match U19 tournament (26 k events, lineups, GPS-like physical data), reproducible from a seed, checked by 19 consistency checks and five published benchmarks.",
          "<b>Explainable KPIs.</b> Common event-data definitions, possession-adjusted, shrunk per-90 values, percentiles against a 50-tournament reference pool, position profiles with reliability labels and a 180-minute ranking threshold.",
          "<b>Live engine.</b> Rolling 5/15-minute windows, control-vs-chaos index, momentum, a moments feed with evidence ids.",
          "<b>Five agents, one workflow.</b> Match Analyst → Narrator fan-out (fan/analyst, EN/HU, club view, player focus) → deterministic pre-check (numbers, names, claim rules, goal direction, clock, venue, language) → Verifier → one repair round; Scout and Recap agents reuse the verified cards.",
          "<b>Two-step live captioning.</b> A deterministic fact card appears in ~13 ms (median of 155 measurements); the verified agent text replaces it (0.1 s from cache, ~25 s fresh). A static web UI shows evidence and the full agent trace."]:
    left.append(Paragraph(t, B, bulletText="•"))
left.append(Paragraph("Microsoft technologies", H2))
left.append(Paragraph("<b>Microsoft Foundry</b> (gpt-4.1-mini deployment, Entra ID auth, no keys) · <b>Microsoft Agent Framework</b> (Agent + FoundryChatClient, function tools, WorkflowBuilder fan-out/fan-in) · <b>Azure Static Web Apps</b> (Free, hosts the demo) · <b>Azure AI Speech</b> (neural narration of the demo video) · Azure CLI.", P))
left.append(Paragraph("Results (committed run)", H2))
left.append(Paragraph(f"{m['items']} narration items → {m['text_variants']} text variants → {m['overlays']} verified overlays in two languages; Verifier: {m['verifier']['ok']} ok, {m['verifier']['repaired']} repaired, {m['verifier']['reject']} rejected; {m['verifier']['precheck_failed']} first drafts caught by the deterministic pre-check. "
                      f"Fresh run with an empty cache: {m['llm_calls']} LLM calls, {m['tokens']['total'] / 1e6:.2f} M tokens ≈ ${m['cost_usd']:.2f}, {m['elapsed_s']:.0f} s; "
                      f"targeted re-runs after the checker fixes: {len(m.get('reruns', []))} runs, ${sum(x['cost_usd'] for x in m.get('reruns', [])):.2f}. Live: fact card ~13 ms (median, n = 155), upgrade 0.1 s (cached) / ~{live['upgrade_latency_s']['max']:.0f} s (fresh). "
                      "Scouting validation against the hidden ground truth: 3 of the 4 planted talents ranked top-2 in their position by the model; the model never reads the hidden file.", P))
left.append(Paragraph("Data statement", H2))
left.append(Paragraph("All data is synthetic; no real match data, footage or provider data is included. During early development, the generator was tuned against private reference values (aggregate league averages), and earlier versions of the validator used realism bands derived from them. Two generator design ranges remain from that stage (goals per match 3.4–3.9, goals/xG 1.05–1.20). None of these values are part of this repository; the published realism validation uses public sources only (see benchmarks.py). Public sources: UEFA Youth League goals per match, a published U19 passing study, published U19 GPS studies.", P))
left.append(Paragraph("Links", H2))
left.append(Paragraph(f'Live demo: <a href="{DEMO}" color="#11998e">{DEMO}</a><br/>Repository (MIT, all data synthetic): <a href="{REPO}" color="#11998e">{REPO}</a>', P))
right = [Image("docs/screenshots/02_overlays_fan_vs_analyst_en.jpg", width=70 * mm, height=52.5 * mm), Spacer(1, 3),
         Paragraph("Fan and analyst overlays from the same verified facts", ParagraphStyle("c", parent=P, fontSize=7.5, textColor=colors.grey)), Spacer(1, 6),
         Image("docs/screenshots/04b_agent_trace_repair_verifier.jpg", width=70 * mm, height=52.5 * mm), Spacer(1, 3),
         Paragraph("Agent trace: pre-check failure, repair round, Verifier", ParagraphStyle("c2", parent=P, fontSize=7.5, textColor=colors.grey))]
tbl = Table([[left, right]], colWidths=[107 * mm, 74 * mm])
tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
S.append(tbl)
doc.build(S)
print("docs/one_pager.pdf written")
