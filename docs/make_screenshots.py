#!/usr/bin/env python3
"""Re-capture docs/screenshots/*.jpg from the local site (python3 -m http.server --directory site). Playwright, no network."""

import sys
from playwright.sync_api import sync_playwright
from PIL import Image

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
OUT = "docs/screenshots/"

SETUP = """() => { const se = window.scoutsEye; se.dismissGuide(); window.__g = se;
  window.__goals = se.D.moments.filter(m => m.type === 'goal');
  window.__ov = (pred) => se.D.overlays.find(pred);
  window.__backed = o => !o.fallback && o.lang === 'en' && o.club_view === 'neutral' && !o.focus_player && se.D.trace[o.trace_key]
      && (se.D.trace[o.trace_key].claims_now || []).some(c => c.rule === 'dominance' && c.supported); }"""


def shot(page, name, js, size=(800, 600), scroll=None):
    page.evaluate(js)
    page.wait_for_timeout(700)
    if scroll:
        page.evaluate(scroll)
        page.wait_for_timeout(500)
    tmp = f"/tmp/_shot_{name}.png"
    page.screenshot(path=tmp)
    Image.open(tmp).convert("RGB").resize(size, Image.LANCZOS).save(OUT + name, quality=88)
    print("wrote", OUT + name)


def lang(code):
    return f"document.querySelector('.seg.lang-top button[data-v={code}]').click();"


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1000, "height": 750}, device_scale_factor=2, locale="en-US")
    page.goto(URL, wait_until="networkidle")
    page.wait_for_function("window.scoutsEye && window.scoutsEye.D && window.scoutsEye.D.overlays")
    page.evaluate(SETUP)
    d = "window.__g.S.upgradeDelayMs + 1500"
    shot(page, "01_match_player_fan_hu.jpg", lang("hu") + f"const g=window.__goals[1]; __g.showTab('match'); __g.setFocus(''); __g.setMode('fan','hu','neutral'); __g.S.speed=1; __g.seek(g.t_ms + {d}); window.scrollTo(0,0);", size=(800, 609))
    shot(page, "02_overlays_fan_vs_analyst_en.jpg", lang("en") + f"const g=window.__goals[0]; __g.setMode('compare','en','neutral'); __g.S.speed=1; __g.seek(g.t_ms + {d}); window.scrollTo(0,0);")
    shot(page, "03_evidence_panel.jpg", f"const o=__ov(__backed) ; __g.setMode(o.persona,'en','neutral'); __g.S.speed=1; __g.seek(o.t_ms + {d}); __g.selectOverlay(o.trace_key);",
         scroll="(() => { const h=[...document.querySelectorAll('#evidencePanel h4')].find(x=>/claim/i.test(x.textContent)); window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 300); })()")
    rep = "const o=__ov(o => !o.fallback && o.lang==='en' && o.club_view==='neutral' && !o.focus_player && __g.D.trace[o.trace_key] && __g.D.trace[o.trace_key].attempts.length>1); __g.selectOverlay(o.trace_key); __g.showTab('agents'); window.scrollTo(0,0);"
    shot(page, "04_agent_trace_with_repair.jpg", rep)
    shot(page, "04b_agent_trace_repair_verifier.jpg", rep, scroll="(() => { const s=document.querySelector('#traceFull .step.repair'); window.scrollTo(0, s.getBoundingClientRect().top + window.scrollY - 200); })()")
    shot(page, "05_player_profile.jpg", "__g.S.player='T1P09'; __g.showTab('players'); window.scrollTo(0,0);")
    shot(page, "06_scouting_view.jpg", "__g.showTab('scouting'); window.scrollTo(0,0);")
    shot(page, "07_recap_fan_hu.jpg", lang("hu") + "__g.showTab('recap'); document.querySelector('.seg[data-key=recapPersona] button[data-v=fan]').click(); document.querySelector('.seg[data-key=recapLang] button[data-v=hu]').click(); window.scrollTo(0,0);")
    shot(page, "08_about.jpg", lang("en") + "__g.showTab('about'); window.scrollTo(0,0);")
    shot(page, "09_player_focus_talent.jpg", f"const o=__g.D.overlays.filter(o=>!o.fallback && o.focus_player==='T1P09' && o.lang==='en' && /low (data|reliability)/i.test(o.text+' '+o.detail)).pop(); __g.showTab('match'); __g.setMode('analyst','en','neutral'); __g.setFocus('T1P09'); __g.S.speed=1; __g.seek(o.t_ms + {d}); window.scrollTo(0,0);")
    shot(page, "10_demo_49_winner.jpg", f"const g=window.__goals[window.__goals.length-1]; __g.setFocus(''); __g.setMode('fan','en','neutral'); __g.S.speed=1; __g.seek(g.t_ms + {d}); window.scrollTo(0,0);")
    m = b.new_page(viewport={"width": 375, "height": 812}, device_scale_factor=2, is_mobile=True, locale="en-US")
    m.goto(URL, wait_until="networkidle")
    m.wait_for_function("window.scoutsEye && window.scoutsEye.D && window.scoutsEye.D.overlays")
    m.evaluate(SETUP)
    shot(m, "11_mobile.jpg", f"const g=window.__goals[0]; __g.setMode('fan','en','neutral'); __g.S.speed=1; __g.seek(g.t_ms + {d}); window.scrollTo(0,0);", size=(750, 1624))
    b.close()
