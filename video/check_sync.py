#!/usr/bin/env python3
"""Audio / picture sync check measured from the FINISHED video (not from a recording log).

    python video/check_sync.py [--frames-out DIR] [--focus Petrovic] [--video FILE --report FILE]

Reads only video/scouts_eye_demo.mp4 (frames and audio through ffmpeg), video/narration/timing.json and
video/narration_script.json. Every 0.2 s of the demo part a frame is read with Apple's Vision text recognition
(video/ocr_frames.m, built with clang on first use, macOS only); the active tab is taken from the colour of its
button; the start and end of each narration segment are measured from the video's audio track. Each of the
nine screen events the narration talks about is detected from those frames and must become visible inside its
narration segment (start - 1 s ... end). Writes video/sync_check.md, and one frame per event (taken while the
event is visible and its narration is spoken) plus frames.md into DIR (default video/frames/sync).
Exit code 1 if an event is missing or outside its segment.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageStat

VIDEO = "video/scouts_eye_demo.mp4"
STEP = 0.2                      # seconds between checked frames (every 6th frame at 30 fps)
T_FROM, T_TO = 7.0, 98.0        # the demo part is 8-98 s; one second of lead
OCR_SRC, OCR_BIN = "video/ocr_frames.m", "video/raw/ocr_frames"
WORK = "video/raw/check"
TABS = {"Match": "match", "Agent trace": "agents", "Player profile": "players", "Scouting": "scouting", "Recap": "recap", "About": "about"}
RULES = ("dominance", "high_press", "chaos", "control_regime", "turnaround", "elite_player")
AUTHOR = "Laczkovics Martin"


def run(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, **kw)


def ocr(paths):
    """Vision text recognition of the given images (4 helper processes in parallel): {path: [line, ...]}."""
    if not os.path.exists(OCR_BIN) or os.path.getmtime(OCR_BIN) < os.path.getmtime(OCR_SRC):
        os.makedirs(os.path.dirname(OCR_BIN), exist_ok=True)
        run("clang", "-fobjc-arc", "-O2", "-framework", "Foundation", "-framework", "Vision", "-framework", "ImageIO",
            "-framework", "CoreGraphics", OCR_SRC, "-o", OCR_BIN)
    chunks = [paths[i::4] for i in range(4)]
    out = {}

    def one(chunk):
        if not chunk:
            return []
        res = run(OCR_BIN, *chunk, text=True)
        return [json.loads(l) for l in res.stdout.splitlines() if l.strip()]
    with ThreadPoolExecutor(4) as ex:
        for pages in ex.map(one, chunks):
            for p in pages:
                out[p["path"]] = p["lines"]
    return out


def active_tab(img, lines):
    """The tab whose button is teal: mean green minus red over the label's box (the header row only)."""
    best, score = None, 60.0
    for l in lines:
        tab = TABS.get(l["text"].strip())
        if not tab or l["y"] > 70:
            continue
        box = img.crop((max(0, l["x"] - 12), max(0, l["y"] - 7), l["x"] + l["w"] + 12, l["y"] + l["h"] + 7)).convert("RGB")
        r, g, _ = ImageStat.Stat(box).mean
        g_r = g - r
        if g_r > score:
            best, score = tab, g_r
    return best


def stage(lines):
    """Lines of the overlay stage (right column, between the player-focus row and the 'Overlay feed' heading)."""
    top = next((l["y"] for l in lines if "talent planted" in l["text"] or l["text"].startswith("Player focus")), None)
    bottom = next((l["y"] for l in lines if l["text"].startswith("Overlay feed")), None)
    if top is None or bottom is None:
        return []
    return [l for l in lines if l["x"] >= 1030 and top < l["y"] < bottom]


def find(lines, pat):
    return next((l["text"] for l in lines if re.search(pat, l["text"])), None)


def claim_line(f):
    """A supported claim rule in the evidence panel, below 'Claim rules applied': a rule id whose tag is the green
    'supported' tag (read from the tag's colour, the tag text is too small to read reliably) or reads 'supported'."""
    lines = f["lines"]
    head = next((l for l in lines if "Claim rules applied" in l["text"]), None)
    if not head:
        return None
    img, rows = None, []
    for l in sorted(lines, key=lambda x: (x["y"], x["x"])):
        if l["y"] <= head["y"] or not re.match(r"(%s)\b" % "|".join(RULES), l["text"]):
            continue
        tag = " ".join(x["text"] for x in lines if abs(x["y"] - l["y"]) <= 14 and l["x"] - 90 <= x["x"] < l["x"] - 2)
        row = " ".join(x["text"] for x in sorted(lines, key=lambda x: x["x"]) if abs(x["y"] - l["y"]) <= 14 and x["x"] >= l["x"] - 2)
        img = img or Image.open(f["path"])
        r, g, b = ImageStat.Stat(img.crop((max(0, l["x"] - 72), l["y"] - 1, max(1, l["x"] - 4), l["y"] + l["h"] + 1)).convert("RGB")).mean
        green = g - r > 20 and g > b
        said = re.search(r"(?<!not )(?<!un)\bsupported\b", tag) and "not supported" not in tag
        if green or said:
            rows.append("[supported] " + row)
    # the narration of this step talks about 'dominating': show that rule's row when it is there
    return next((r for r in rows if r.startswith("[supported] dominance")), rows[0] if rows else None)


def fact_card(st, clock):
    """A fact card of the given minute on the stage: its 'fact card' tag and the card text (GOAL / MILESTONE ... in capitals)."""
    if not any("fact card" in l["text"] for l in st) or not any(l["text"].startswith(clock) for l in st):
        return None
    return next((l["text"] for l in st if re.match(r"[A-ZÁÉÍÓÖŐÚÜŰ-]{4,}\b", l["text"])), None)


def events(focus):
    """(key, narration segment, what the frame shows, detector returning the matching text or None)."""
    def verified(st):
        return sum(bool(re.search(r"\bverified\b", l["text"])) for l in st)
    return [
        ("goal_fact_card", 2, "match tab: the 2' goal as a fact card on the stage",
         lambda f: f["tab"] == "match" and fact_card(f["stage"], "2'")),
        ("side_by_side", 3, "match tab, Fan + Analyst: two verified texts side by side",
         lambda f: f["tab"] == "match" and verified(f["stage"]) >= 2 and find(f["stage"], r"\bfan/en\b") and find(f["stage"], r"\banalyst/en\b")),
        ("evidence_claim", 4, "evidence panel: a supported claim rule", lambda f: claim_line(f)),
        ("agent_trace", 5, "agent trace tab: the selected overlay's agents, pre-check and repair",
         lambda f: f["tab"] == "agents" and find(f["lines"], r"Agent trace for the selected overlay")),
        ("focus_text", 6, f"match tab: the player-focus text about {focus} on the stage",
         lambda f: f["tab"] == "match" and verified(f["stage"]) >= 1 and find(f["stage"], re.escape(focus))),
        ("profile_tab", 6, f"player profile tab: {focus}'s profile with the line 'Before M12'",
         lambda f: f["tab"] == "players" and find(f["lines"], r"Before M12")),
        ("winner_fact_card", 7, "match tab: the 49' penalty goal as a fact card",
         lambda f: f["tab"] == "match" and fact_card(f["stage"], "49'")),
        ("winner_verified", 7, "match tab: the verified 49' texts",
         lambda f: f["tab"] == "match" and verified(f["stage"]) >= 1 and find(f["stage"], r"\b49'")
         and next((l["text"] for l in f["stage"] if "Andreou" in l["text"] and "GOAL" not in l["text"]), None)),
        ("recap_tab", 7, "recap tab: the fan recap in English", lambda f: f["tab"] == "recap" and find(f["lines"], r"Top 3 [Mm]oments|Final [Ss]tandings")),
    ]


# a sentence of the narration that names the event: the frame for the audit is taken while it is spoken
SAYS = {"goal_fact_card": r"fact card", "side_by_side": r"two audiences|Fans get", "evidence_claim": r"rule behind|dominating",
        "agent_trace": r"pre-check|Five agents", "focus_text": r"[Pp]layer focus", "profile_tab": r"minutes|ranking",
        "winner_fact_card": r"fact card comes first", "winner_verified": r"verified text", "recap_tab": r"recap"}


def speech_spans(segs):
    """Start and end of the speech of every narration segment, measured from the video's audio (RMS per 50 ms)."""
    raw = run("ffmpeg", "-v", "error", "-i", VIDEO, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-").stdout
    import array
    a = array.array("h", raw)
    win = 800
    rms = [(sum(x * x for x in a[i:i + win]) / win) ** 0.5 for i in range(0, len(a) - win, win)]
    thr = max(rms) * 0.04
    t = lambda k: k * win / 16000
    out = {}
    for s in segs:
        ks = [k for k in range(len(rms)) if s["start"] - 0.5 <= t(k) <= s["end"] and rms[k] > thr]
        out[s["id"]] = (round(t(ks[0]), 2), round(t(ks[-1]) + win / 16000, 2)) if ks else (None, None)
    return out


def sentence_at(seg, span, t):
    """The narration sentence spoken at video time t (spread over the measured speech by length: approximate)."""
    a, b = span
    if a is None or t < a:
        return "(before this segment's narration starts)"
    if t > b:
        return "(after this segment's narration has ended)"
    sents = [x for x in re.split(r"(?<=[.!?])\s+", seg["text"]) if x]
    total = sum(len(x) for x in sents)
    pos, acc = (t - a) / (b - a) * total, 0
    for x in sents:
        acc += len(x)
        if pos <= acc:
            return x
    return sents[-1]


def sentence_window(seg, span, pat):
    """(from, to) video time of the first sentence matching pat (approximate), or None."""
    a, b = span
    if a is None:
        return None
    sents = [x for x in re.split(r"(?<=[.!?])\s+", seg["text"]) if x]
    total, acc = sum(len(x) for x in sents), 0
    for x in sents:
        s0 = a + acc / total * (b - a)
        acc += len(x)
        if re.search(pat, x):
            return s0, a + acc / total * (b - a)
    return None


def main():
    global VIDEO
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-out", default="video/frames/sync", help="folder for the one-frame-per-event images and frames.md")
    ap.add_argument("--focus", default="Petrovic", help="surname of the focus player shown in demo step 5")
    ap.add_argument("--video", default=VIDEO, help="the video to check (default: the assembled demo video)")
    ap.add_argument("--report", default="video/sync_check.md", help="where to write the Markdown report")
    args = ap.parse_args()
    VIDEO = args.video
    timing = json.load(open("video/narration/timing.json"))["segments"]
    script = {s["id"]: s for s in json.load(open("video/narration_script.json"))}
    segs = {s["id"]: dict(s, end=script[s["id"]]["end"]) for s in timing}
    duration = float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", VIDEO, text=True).stdout)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    run("ffmpeg", "-v", "error", "-ss", f"{T_FROM}", "-to", f"{T_TO}", "-i", VIDEO, "-vf", f"fps={1 / STEP:g}", "-q:v", "2", f"{WORK}/%05d.jpg")
    paths = sorted(os.path.join(WORK, f) for f in os.listdir(WORK) if f.endswith(".jpg"))
    texts = ocr(paths)
    frames = []
    for k, p in enumerate(paths):
        lines = texts.get(p, [])
        img = Image.open(p)
        frames.append(dict(t=round(T_FROM + k * STEP, 2), path=p, lines=lines, tab=active_tab(img, lines), stage=stage(lines)))
    spans = speech_spans(timing)
    spec = events(args.focus)
    rows = []
    for key, sid, what, det in spec:
        seen = [(f["t"], det(f)) for f in frames]
        vis = [t for t, hit in seen if hit]
        s = segs[sid]
        first = vis[0] if vis else None
        ok = first is not None and s["start"] - 1.0 <= first <= s["end"]
        rows.append(dict(key=key, sid=sid, what=what, first=first, last=vis[-1] if vis else None, vis=vis, ok=ok,
                         evidence=next((hit for t, hit in seen if hit), None)))
    # one frame per event for the audit: visible, inside the segment, preferably while the sentence about it is spoken
    os.makedirs(args.frames_out, exist_ok=True)
    for f in os.listdir(args.frames_out):
        if re.match(r"\d\d_seg\d_.*\.jpg$", f):
            os.remove(os.path.join(args.frames_out, f))
    for n, r in enumerate(rows, 1):
        s, span = segs[r["sid"]], spans[r["sid"]]
        cands = [t for t in r["vis"] if s["start"] - 1.0 <= t <= s["end"]]
        if not cands:
            r["frame"] = None
            continue
        win = sentence_window(s, span, SAYS[r["key"]])
        inside = [t for t in cands if win and win[0] <= t <= win[1]]
        in_speech = [t for t in cands if span[0] is not None and span[0] <= t <= span[1]]
        pick = inside or in_speech or cands
        t = pick[len(pick) // 2]
        name = f"{n:02d}_seg{r['sid']}_{r['key']}_{t:.1f}s.jpg"
        run("ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", VIDEO, "-frames:v", "1", "-q:v", "2", os.path.join(args.frames_out, name))
        r.update(frame=name, frame_t=t, says=sentence_at(s, span, t))
    # the author's name on the opener, the closer and the cover
    run("ffmpeg", "-v", "error", "-y", "-ss", "4", "-i", VIDEO, "-frames:v", "1", "-q:v", "2", f"{WORK}/opener.jpg")
    run("ffmpeg", "-v", "error", "-y", "-ss", f"{duration - 3:.2f}", "-i", VIDEO, "-frames:v", "1", "-q:v", "2", f"{WORK}/closer.jpg")
    names = ocr([f"{WORK}/opener.jpg", f"{WORK}/closer.jpg", "video/youtube_cover_1280x720.png"])
    author = {k: any(AUTHOR in l["text"] for l in names.get(p, [])) for k, p in
              (("opener", f"{WORK}/opener.jpg"), ("closer", f"{WORK}/closer.jpg"), ("cover", "video/youtube_cover_1280x720.png"))}
    n_ok = sum(r["ok"] for r in rows)
    fmt = lambda x: f"{x:.1f}" if x is not None else "–"
    md = [f"# Audio / picture sync check ({os.path.relpath(VIDEO) if os.path.abspath(VIDEO).startswith(os.getcwd() + os.sep) else os.path.basename(VIDEO)})", "",
          f"Measured from the finished video ({duration:.1f} s), not from a recording log (`python video/check_sync.py`): every "
          f"{STEP:g} s of the demo part ({T_FROM:g}–{T_TO:g} s) a frame is read with Apple's Vision text recognition, the active tab is "
          "taken from the colour of its button, and the start and end of every narration segment are measured from the video's "
          "audio track. An event is OK when it first becomes visible inside its narration segment (or up to 1 s before it).", "",
          "| screen event | first visible (s) | visible until (s) | narration segment | segment (s) | speech measured (s) | result |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        s, sp = segs[r["sid"]], spans[r["sid"]]
        md.append(f"| {r['what']} | {fmt(r['first'])} | {fmt(r['last'])} | {r['sid']} | {s['start']:.0f}–{s['end']:.0f} | "
                  f"{fmt(sp[0])}–{fmt(sp[1])} | {'OK' if r['ok'] else 'NOT OK'} |")
    md += ["", f"Result: **{n_ok} / {len(rows)}** screen events visible inside their narration segment.", "",
           "| segment | slot (s) | narration audio (s) | speech measured in the video (s) | fits in its slot |", "|---|---|---|---|---|"]
    for s in timing:
        sp = spans[s["id"]]
        md.append(f"| {s['id']} | {s['start']:.0f}–{segs[s['id']]['end']:.0f} | {s['audio_s']} | {fmt(sp[0])}–{fmt(sp[1])} | "
                  f"{'yes' if sp[1] is not None and sp[1] <= segs[s['id']]['end'] + 0.05 else 'no'} |")
    out_abs = os.path.abspath(args.frames_out)
    where = os.path.relpath(out_abs) if out_abs.startswith(os.getcwd() + os.sep) else f"{os.path.basename(out_abs)}/ (outside the repository)"
    md += ["", f"Author name ({AUTHOR}) on the opener / closer / cover: " + " / ".join("yes" if author[k] else "NO" for k in ("opener", "closer", "cover")) + ".",
           "", f"One frame per event (taken while the event is visible and its narration is spoken): `{where}`, listed in `frames.md` there."]
    open(args.report, "w", encoding="utf-8").write("\n".join(md) + "\n")
    fm = ["# One frame per screen event (from the finished video)", "",
          f"Video: `{os.path.basename(VIDEO)}`, {duration:.1f} s. Each frame is taken from the finished video while the event is "
          "visible and inside its narration segment; the sentence is the one spoken at that moment (estimated from the measured "
          "speech of the segment, spread by sentence length, so ± about 1 s).", "",
          "| # | file | video time (s) | what the frame shows | what the voice says at that moment |", "|---|---|---|---|---|"]
    for n, r in enumerate(rows, 1):
        shown = r["what"] + (f" (read on the frame: “{r['evidence'][:90]}”)" if isinstance(r["evidence"], str) else "")
        fm.append(f"| {n} | {r.get('frame') or '– (not visible inside its segment)'} | {fmt(r.get('frame_t'))} | {shown} | “{r.get('says', '–')}” |")
    open(os.path.join(args.frames_out, "frames.md"), "w", encoding="utf-8").write("\n".join(fm) + "\n")
    for r in rows:
        print(f"{'OK    ' if r['ok'] else 'NOT OK'} {r['what']}: first {fmt(r['first'])} s (segment {r['sid']}: "
              f"{segs[r['sid']]['start']:.0f}-{segs[r['sid']]['end']:.0f} s)  frame {r.get('frame')}")
    print(f"{n_ok}/{len(rows)} screen events inside their narration segment; video {duration:.1f} s; author on opener/closer/cover: {author}")
    if n_ok < len(rows) or not all(author.values()):
        sys.exit(1)          # the checked frames stay in video/raw/check for a look
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
