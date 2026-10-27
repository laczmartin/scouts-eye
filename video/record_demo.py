#!/usr/bin/env python3
"""Record the 90-second demo script frame by frame on a virtual clock, and capture the About diagram.

    python video/record_demo.py http://localhost:8765/      # FPS=30 by default (env FPS)

Why frames and not a screencast: Playwright's screen recording timestamps frames as they arrive, so under load
the video drifted about 4 s behind the page (the recap tab of the 27 Oct night video was cut off). Here the page
runs on Playwright's virtual clock (Date, timers, requestAnimationFrame, performance.now): the recorder advances
it by exactly 1/FPS s, then takes a screenshot, so frame i shows the page at demo time i/FPS, however slow
the machine is. Smooth scrolling is made instant (it would run on the real clock).

The recorder never assumes that something is on the screen because a timer fired. After every 1/FPS step it
waits in real time, with the virtual clock stopped, until the page has nothing pending (network requests,
fonts, images), reads the DOM (tab, demo step, clock, stage overlays, evidence claims, profile card, recap)
and only then takes the frame. The nine screen events the narration talks about are taken from that state;
an event that does not appear inside its narration segment (start - 1 s ... end; video time = 8 s opener +
demo time) stops the script with exit code 1. Output: video/raw/frames/*.jpg, video/raw/frame_log.json (the
DOM state of every frame), video/raw/record_meta.json (fps, frames, events, capture time).
"""

import json
import os
import shutil
import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765/"
FPS = int(os.environ.get("FPS", "30"))
DEMO_S = float(os.environ.get("DEMO_S", "90"))      # length of the in-app demo script (6 steps, 90 s)
OPENER_S = 8.0                                     # the demo starts after the 8-second opener in the video
OUT, FRAMES = "video/raw", "video/raw/frames"
SETTLE_MAX_S = 10.0                                # longest real-time wait for pending loads before a frame

# instant scrolling: smooth scrolling is animated on the real clock, not on the virtual one
NO_SMOOTH = """(() => {
  const add = () => { const s = document.createElement('style'); s.textContent = 'html, body, * { scroll-behavior: auto !important; }';
                      (document.head || document.documentElement).appendChild(s); };
  if (document.documentElement) add(); else document.addEventListener('DOMContentLoaded', add);
  const fix = o => (o && typeof o === 'object') ? Object.assign({}, o, { behavior: 'auto' }) : o;
  const siv = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = function (o) { return siv.call(this, fix(o)); };
  for (const name of ['scrollTo', 'scroll', 'scrollBy']) {
    const f = window[name].bind(window);
    window[name] = function (a, b) { return (a && typeof a === 'object') ? f(fix(a)) : f(a, b); };
  }
})();"""

# what is on the screen: active tab, demo step, clock, stage overlays, evidence claims, profile card, recap heading
PROBE = """() => {
  const q = s => document.querySelector(s);
  const inView = el => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.bottom > 0 && r.top < innerHeight; };
  const stage = [...document.querySelectorAll('#overlayStage .ov')].filter(inView).map(e => ({
    clock: ((e.querySelector('.meta span') || {}).textContent || '').trim(),
    kind: e.classList.contains('fallback') ? 'fallback' : e.classList.contains('factcard') ? 'fact card' : 'verified',
    text: ((e.querySelector('.txt') || e).innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 140),
    focus: /focus:/.test((e.querySelector('.meta') || {}).innerText || '') }));
  const claims = [...document.querySelectorAll('#evidencePanel .tag.ok')].filter(t => t.textContent.trim() === 'supported' && inView(t))
    .map(t => (t.parentElement.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 120));
  const tab = (q('.tab.active') || {}).id || null;
  const card = q('#playerCard');
  const recapH = q('#recap h1, #recap h2');
  return { tab, step: ((q('#demoStep') || {}).textContent || '').slice(0, 3), demo: !(q('#demoOverlay') || {}).hidden,
           clock: ((q('#clock') || {}).textContent || '').trim(), scrollY: Math.round(scrollY), stage, claims,
           profile_before_m12: tab === 'tab-players' && !!card && /Before M12|M12 előtt/.test(card.innerText),
           recap_heading: tab === 'tab-recap' && recapH ? recapH.innerText.trim().slice(0, 120) : null };
}"""


# rendering that depends on the real clock: fonts still loading, images not decoded yet
PENDING = "() => (document.fonts && document.fonts.status !== 'loaded') || [...document.images].some(i => !i.complete)"


def load_segments():
    return {s["id"]: s for s in json.load(open("video/narration_script.json"))}


def events_spec(focus_surname):
    """(key, narration segment, description, predicate on the probed state) for the nine screen events."""
    fact = lambda st, clk: any(o["kind"] == "fact card" and o["clock"] == clk for o in st["stage"])
    verified = lambda st, clk: any(o["kind"] == "verified" and o["clock"] == clk for o in st["stage"])
    return [
        ("goal_fact_card", 2, "step 1: match tab, 2' goal fact card on stage", lambda st: st["step"] == "1/6" and st["tab"] == "tab-match" and fact(st, "2'")),
        ("side_by_side", 3, "step 2: verified fan + analyst texts side by side", lambda st: st["step"] == "2/6" and sum(o["kind"] == "verified" for o in st["stage"]) >= 2),
        ("evidence_claim", 4, "step 3: evidence panel with a supported claim rule", lambda st: st["step"] == "3/6" and len(st["claims"]) >= 1),
        ("agent_trace", 5, "step 4: agent trace tab (repair round)", lambda st: st["step"] == "4/6" and st["tab"] == "tab-agents"),
        ("focus_text", 6, f"step 5: player focus text ({focus_surname}) on stage", lambda st: st["step"] == "5/6" and st["tab"] == "tab-match"
         and any(o["kind"] == "verified" and focus_surname in o["text"] for o in st["stage"])),
        ("profile_tab", 6, "step 5: player profile tab", lambda st: st["step"] == "5/6" and st["tab"] == "tab-players" and st["profile_before_m12"]),
        ("winner_fact_card", 7, "step 6: match tab, 49' fact card", lambda st: st["step"] == "6/6" and st["tab"] == "tab-match" and fact(st, "49'")),
        ("winner_verified", 7, "step 6: 49' verified text", lambda st: st["step"] == "6/6" and st["tab"] == "tab-match" and verified(st, "49'")),
        ("recap_tab", 7, "step 6: recap tab", lambda st: st["tab"] == "tab-recap" and bool(st["recap_heading"])),
    ]


def main():
    segs = load_segments()
    shutil.rmtree(FRAMES, ignore_errors=True)
    os.makedirs(FRAMES, exist_ok=True)
    n_frames = int(round(DEMO_S * FPS))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1, locale="en-US")
        ctx.add_init_script(NO_SMOOTH)
        page = ctx.new_page()
        in_flight = set()
        page.on("request", lambda r: in_flight.add(r))
        page.on("requestfinished", lambda r: in_flight.discard(r))
        page.on("requestfailed", lambda r: in_flight.discard(r))
        page.clock.install()                   # virtual clock; it runs normally until it is paused below
        page.goto(URL, wait_until="networkidle")
        page.wait_for_function("window.scoutsEye && window.scoutsEye.D && window.scoutsEye.D.overlays")
        page.evaluate("window.scoutsEye.dismissGuide()")
        # About diagram for the closing card (separate screenshot, not part of the demo timeline)
        page.evaluate("window.scoutsEye.showTab('about')")
        page.wait_for_timeout(500)
        page.locator("#arch").screenshot(path="video/about_architecture.png")
        page.evaluate("window.scoutsEye.showTab('match'); window.scrollTo(0, 0)")
        page.wait_for_timeout(1500)
        focus = page.evaluate("(() => { const D = window.scoutsEye.D; const pid = D.narration.focus_players[0]; return (D.playerById[pid] || {}).name || pid; })()")
        surname = focus.split()[-1]
        spec = events_spec(surname)
        # stop the clock, then start the demo: from now on time moves only when the recorder advances it
        page.clock.pause_at(page.evaluate("Date.now()") + 1000)
        page.evaluate("window.scoutsEye.runDemo()")
        log, found, waited = [], {}, 0.0
        t_start, prev_ms = time.time(), 0
        for i in range(n_frames):
            target_ms = round(i * 1000 / FPS)
            if target_ms > prev_ms:
                page.clock.run_for(target_ms - prev_ms)
                prev_ms = target_ms
            video_t = OPENER_S + i / FPS
            # wait for the real screen state: nothing pending that runs on the real clock (the virtual one is stopped)
            t_w = time.time()
            while (in_flight or page.evaluate(PENDING)) and time.time() - t_w < SETTLE_MAX_S:
                time.sleep(0.02)
            waited += time.time() - t_w
            st = page.evaluate(PROBE)
            for key, sid, _, pred in spec:
                if key not in found and pred(st):
                    found[key] = dict(frame=i, demo_t=round(i / FPS, 3), video_t=round(video_t, 3))
            page.screenshot(path=os.path.join(FRAMES, f"{i:05d}.jpg"), type="jpeg", quality=90, animations="disabled", caret="hide")
            log.append(dict(i=i, demo_t=round(i / FPS, 3), video_t=round(video_t, 3), **st))
            if i % (10 * FPS) == 0:
                print(f"  frame {i}/{n_frames} (demo {i / FPS:.0f}s), {time.time() - t_start:.0f}s real", flush=True)
        capture_s = time.time() - t_start
        ctx.close()
        browser.close()
    json.dump(log, open(os.path.join(OUT, "frame_log.json"), "w"), indent=0)
    rows, bad = [], []
    for key, sid, desc, _ in spec:
        s = segs[sid]
        f = found.get(key)
        ok = bool(f) and s["start"] - 1.0 <= f["video_t"] <= s["end"]
        rows.append(dict(event=key, description=desc, segment=sid, segment_start=s["start"], segment_end=s["end"],
                         video_t=f["video_t"] if f else None, frame=f["frame"] if f else None, ok=ok))
        if not ok:
            bad.append(f"{desc}: " + (f"first seen at {f['video_t']:.2f} s, outside segment {sid} ({s['start']:.0f}-{s['end']:.0f} s)" if f
                                      else f"never on the screen (segment {sid}, {s['start']:.0f}-{s['end']:.0f} s)"))
    meta = dict(url=URL, fps=FPS, frames=n_frames, demo_s=DEMO_S, opener_s=OPENER_S, focus_player=focus, capture_s=round(capture_s, 1),
                real_wait_s=round(waited, 2), events=rows, note="frame i shows the page at virtual demo time i/fps (Playwright clock)")
    json.dump(meta, open(os.path.join(OUT, "record_meta.json"), "w"), indent=1)
    for r in rows:
        print(f"{'OK    ' if r['ok'] else 'NOT OK'} {r['description']}: " + (f"{r['video_t']:.2f} s" if r["video_t"] is not None else "not seen")
              + f" (segment {r['segment']}: {r['segment_start']:.0f}-{r['segment_end']:.0f} s)")
    print(f"recorded {n_frames} frames at {FPS} fps in {capture_s:.0f} s; about diagram -> video/about_architecture.png")
    if bad:
        print("RECORDING FAILED – screen events outside their narration segment:\n  " + "\n  ".join(bad), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
