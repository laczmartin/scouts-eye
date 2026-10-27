#!/usr/bin/env python3
"""Assemble the demo video: opener (8 s) + recorded demo (90 s) + closer (14 s), narration, burned subtitles, SRT, cover.

The demo part is built from the frames of video/record_demo.py (video/raw/frames, one frame per 1/fps s of the
page's virtual clock, see video/raw/record_meta.json), so picture and narration share one exact timeline."""

import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
BG, ACC, ACC2, TXT, MUT = (15, 20, 25), (25, 195, 165), (242, 177, 52), (232, 238, 243), (159, 176, 191)
DEMO_URL, REPO_URL = "https://calm-pond-0e514280f.3.azurestaticapps.net", "github.com/laczmartin/scouts-eye"
AUTHOR = "Laczkovics Martin"
FONT_CANDIDATES = ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"]


def font(size, bold=False):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size, index=1 if bold and p.endswith(".ttc") else 0)
            except Exception:
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def card(draw, x, y, w, h, fill=(29, 38, 49), outline=ACC):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=fill, outline=outline, width=2)


def opener():
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.ellipse([110, 400, 230, 520], fill=ACC); d.ellipse([145, 435, 195, 485], fill=(255, 255, 255))
    d.text((270, 380), "Scout's Eye", font=font(110, True), fill=TXT)
    d.text((272, 520), "Explainable U19 Match Intelligence", font=font(56), fill=TXT)
    d.text((272, 610), "Microsoft Foundry · Microsoft Agent Framework", font=font(44), fill=ACC)
    d.text((272, 720), "Every number traceable to an event · every sentence checked before it is shown", font=font(32), fill=MUT)
    d.text((272, 800), f"by {AUTHOR}", font=font(40, True), fill=TXT)
    im.save("video/opener.png")


def closer():
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.text((100, 60), "How it works", font=font(60, True), fill=TXT)
    arch = Image.open("video/about_architecture.png").convert("RGB")
    scale = min(1720 / arch.width, 300 / arch.height)
    arch = arch.resize((int(arch.width * scale), int(arch.height * scale)), Image.LANCZOS)
    im.paste(arch, (100, 150))
    y = 150 + arch.height + 40
    card(d, 100, y, 1720, 260)
    d.text((140, y + 28), "Live demo", font=font(38, True), fill=ACC)
    d.text((140, y + 78), DEMO_URL, font=font(46), fill=TXT)
    d.text((140, y + 150), "Repository", font=font(38, True), fill=ACC)
    d.text((140, y + 198), REPO_URL + "   ·   MIT licence   ·   all data synthetic", font=font(40), fill=TXT)
    d.text((100, y + 285), f"{AUTHOR} · GitHub: laczmartin", font=font(36, True), fill=TXT)
    d.text((100, y + 335), "Microsoft Foundry · Microsoft Agent Framework · Azure Static Web Apps · Azure AI Speech (narration)", font=font(26), fill=MUT)
    assert y + 335 + 34 < H - 220, "closer text would run into the subtitles"
    im.save("video/closer.png")


def cover():
    im = Image.new("RGB", (1280, 720), BG); d = ImageDraw.Draw(im)
    shot = Image.open("docs/screenshots/02_overlays_fan_vs_analyst_en.jpg").convert("RGB")
    shot = shot.resize((760, int(760 * shot.height / shot.width)), Image.LANCZOS)
    im.paste(shot, (500, 100))
    d.rectangle([0, 0, 520, 720], fill=(15, 20, 25))
    d.ellipse([60, 80, 140, 160], fill=ACC); d.ellipse([84, 104, 116, 136], fill=(255, 255, 255))
    d.text((60, 200), "Scout's Eye", font=font(78, True), fill=TXT)
    d.text((60, 300), "Explainable U19", font=font(46), fill=TXT); d.text((60, 356), "Match Intelligence", font=font(46), fill=TXT)
    d.text((60, 450), "5 agents · every number checked", font=font(28), fill=ACC2)
    d.text((60, 500), "Microsoft Foundry", font=font(32), fill=ACC); d.text((60, 544), "Agent Framework", font=font(32), fill=ACC)
    d.text((60, 600), f"by {AUTHOR}", font=font(28, True), fill=TXT)
    d.text((60, 650), "Best Multi-Agent System entry · synthetic data", font=font(24), fill=MUT)
    im.save("video/youtube_cover_1280x720.png")


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap(text, n=92):
    """Split the cue into the fewest lines of at most ~n characters, balanced in length."""
    words = text.split()
    k = max(1, -(-len(text) // n))
    while True:
        target = len(text) / k
        lines, cur = [], ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > target and len(lines) < k - 1:
                lines.append(cur); cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        if max(len(l) for l in lines) <= n + 8 or k >= 3:
            return "\n".join(lines)
        k += 1


def main():
    opener(); closer(); cover()
    rec = json.load(open("video/raw/record_meta.json"))
    if not all(e["ok"] for e in rec["events"]):
        raise SystemExit("video/raw/record_meta.json: the recording has screen events outside their narration segment; record again")
    timing = json.load(open("video/narration/timing.json"))
    segs = timing["segments"]
    # subtitles: one cue per narration segment, timed to the narration audio
    with open("video/scouts_eye_demo.srt", "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"{s['id']}\n{srt_time(s['start'] + 0.2)} --> {srt_time(min(s['end'] - 0.2, s['start'] + s['audio_s'] + 0.6))}\n{wrap(s['text'])}\n\n")
    run = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
    # segments (silent video), 30 fps, 1080p
    run("-loop", "1", "-t", "8", "-i", "video/opener.png", "-vf", "format=yuv420p,fps=30", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "video/raw/part_opener.mp4")
    # the demo: frame i of the recording is demo time i/fps (virtual clock), so the part is exactly frames/fps seconds
    run("-framerate", str(rec["fps"]), "-i", "video/raw/frames/%05d.jpg", "-frames:v", str(rec["frames"]), "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "video/raw/part_demo.mp4")
    run("-loop", "1", "-t", "14", "-i", "video/closer.png", "-vf", "format=yuv420p,fps=30", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "video/raw/part_closer.mp4")
    with open("video/raw/concat.txt", "w") as f:
        for p in ("part_opener", "part_demo", "part_closer"):
            f.write(f"file '{os.path.abspath('video/raw/' + p + '.mp4')}'\n")
    run("-f", "concat", "-safe", "0", "-i", "video/raw/concat.txt", "-c", "copy", "video/raw/video_silent.mp4")
    # narration track: each segment placed at its start time
    inputs, filt = [], []
    for i, s in enumerate(segs):
        inputs += ["-i", f"video/narration/seg{s['id']}.wav"]
        filt.append(f"[{i}:a]adelay={int(s['start'] * 1000)}|{int(s['start'] * 1000)}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(segs))) + f"amix=inputs={len(segs)}:normalize=0,aresample=48000[aout]"
    run(*inputs, "-filter_complex", ";".join(filt) + ";" + mix, "-map", "[aout]", "-t", "112", "-c:a", "aac", "-b:a", "160k", "video/raw/narration.m4a")
    # burn subtitles: this ffmpeg build has no libass, so each cue is rendered with PIL and overlaid for its time window
    os.makedirs("video/raw/subs", exist_ok=True)
    cues = []
    for s in segs:
        a, b = s["start"] + 0.2, min(s["end"] - 0.2, s["start"] + s["audio_s"] + 0.6)
        lines = wrap(s["text"]).split("\n")
        f = font(36)
        im = Image.new("RGBA", (W, 200), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        widths = [d.textlength(l, font=f) for l in lines]
        bw = int(max(widths)) + 60; bh = 50 * len(lines) + 26
        x0 = (W - bw) // 2; y0 = 200 - bh - 10
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=12, fill=(16, 20, 24, 200))
        for i, l in enumerate(lines):
            d.text(((W - widths[i]) / 2, y0 + 12 + 50 * i), l, font=f, fill=(255, 255, 255, 255))
        p = f"video/raw/subs/cue{s['id']}.png"; im.save(p); cues.append((p, a, b))
    inputs = ["-i", "video/raw/video_silent.mp4", "-i", "video/raw/narration.m4a"]
    chain, last = [], "[0:v]"
    for i, (p, a, b) in enumerate(cues):
        inputs += ["-i", p]
        out = f"[v{i}]"
        chain.append(f"{last}[{i + 2}:v]overlay=0:{H - 200 - 20}:enable='between(t,{a:.2f},{b:.2f})'{out}")
        last = out
    run(*inputs, "-filter_complex", ";".join(chain), "-map", last, "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy", "-shortest", "-movflags", "+faststart", "video/scouts_eye_demo.mp4")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_name", "-of", "csv=p=0", "video/scouts_eye_demo.mp4"], capture_output=True, text=True).stdout
    print(out.strip())


if __name__ == "__main__":
    main()
