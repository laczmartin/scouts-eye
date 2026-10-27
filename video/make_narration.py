#!/usr/bin/env python3
"""Synthesise the narration with Azure AI Speech (neural voice) using Entra ID token auth (az login).
No key is read, printed or stored. Writes one WAV per segment plus narration/timing.json.

    python video/make_narration.py          # only the segments whose text or slot changed (video/narration_script.json)
    python video/make_narration.py --all    # every segment again
"""

import argparse
import json
import os
import subprocess
import sys
import wave

RG, NAME, REGION = "rg-scouts-eye", "scouts-eye-speech", "eastus2"
VOICE = os.environ.get("VOICE", "en-US-AvaMultilingualNeural")
TIMING = "video/narration/timing.json"


def az(*args):
    return subprocess.run(["az", *args], capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="synthesise every segment again (default: only changed segments)")
    args = ap.parse_args()
    segs = json.load(open("video/narration_script.json"))
    old = {s["id"]: s for s in json.load(open(TIMING))["segments"]} if os.path.exists(TIMING) else {}
    same = lambda s: (s["id"] in old and old[s["id"]]["text"] == s["text"] and old[s["id"]]["start"] == s["start"]
                      and old[s["id"]]["end"] == s["end"] and os.path.exists(f"video/narration/seg{s['id']}.wav"))
    todo = {s["id"] for s in segs if args.all or not same(s)}
    synth_cfg = None
    if todo:
        import azure.cognitiveservices.speech as sdk
        resource_id = az("cognitiveservices", "account", "show", "-n", NAME, "-g", RG, "--query", "id", "-o", "tsv")
        token = az("account", "get-access-token", "--resource", "https://cognitiveservices.azure.com", "--query", "accessToken", "-o", "tsv")
        synth_cfg = sdk.SpeechConfig(auth_token=f"aad#{resource_id}#{token}", region=REGION)
        synth_cfg.speech_synthesis_voice_name = VOICE
        synth_cfg.set_speech_synthesis_output_format(sdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm)
    timing = []
    for s in segs:
        if s["id"] not in todo:
            timing.append(dict(old[s["id"]], start=s["start"], end=s["end"], slot=s["end"] - s["start"]))
            print(f"seg {s['id']}: unchanged, audio {old[s['id']]['audio_s']:.1f}s kept")
            continue
        out = f"video/narration/seg{s['id']}.wav"
        budget = s["end"] - s["start"] - 0.4
        rate = float(os.environ.get("RATE", "0"))
        for attempt in range(3):
            ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
                    f'<voice name="{VOICE}"><prosody rate="{rate:+.0f}%">{s["text"]}</prosody></voice></speak>')
            synth = sdk.SpeechSynthesizer(speech_config=synth_cfg, audio_config=sdk.audio.AudioOutputConfig(filename=out))
            r = synth.speak_ssml_async(ssml).get()
            if r.reason != sdk.ResultReason.SynthesizingAudioCompleted:
                d = r.cancellation_details
                print("synthesis failed:", d.reason, (d.error_details or "")[:200], file=sys.stderr)
                sys.exit(1)
            with wave.open(out) as w:
                dur = w.getnframes() / w.getframerate()
            if dur <= budget:
                break
            rate += 8  # speak a little faster if the segment does not fit its slot
        timing.append(dict(id=s["id"], start=s["start"], end=s["end"], slot=s["end"] - s["start"], audio_s=round(dur, 2), rate=rate, fits=dur <= budget, text=s["text"]))
        print(f"seg {s['id']}: slot {s['end'] - s['start']:.0f}s, audio {dur:.1f}s, rate {rate:+.0f}% {'OK' if dur <= budget else 'TOO LONG'}")
    json.dump(dict(voice=VOICE, segments=timing), open(TIMING, "w"), indent=2)


if __name__ == "__main__":
    main()
