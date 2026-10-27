#!/usr/bin/env python3
"""Replay a match's events in timestamp order, simulating a live feed.

Usage:
    python replay.py --match M12 --speed 60            # 1 match minute per second, to stdout
    python replay.py --match M12 --speed 60 --limit 20 # first 20 events only
    python replay.py --match M12 --speed 600 --url http://localhost:8080/events

Output: one JSON object per line on stdout (default) or an HTTP POST per event
to --url. Later phases subscribe to this stream; the transport can be swapped
for Azure Event Hubs / Functions without touching the generator.
"""

import argparse
import json
import os
import sys
import time
import urllib.request


def iter_events(path):
    with open(path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    events.sort(key=lambda e: (e["timestamp_ms"], e["event_id"]))
    return events


def post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()


def main():
    ap = argparse.ArgumentParser(description="Live replay of a synthetic match")
    ap.add_argument("--data", default="data/synthetic", help="dataset directory")
    ap.add_argument("--match", default="M12", help="match id (default M12, the live match)")
    ap.add_argument("--speed", type=float, default=1.0, help="speed factor: 1 = real time, 60 = one match minute per second")
    ap.add_argument("--url", default=None, help="POST each event to this URL instead of printing it")
    ap.add_argument("--limit", type=int, default=None, help="stop after N events (for testing)")
    ap.add_argument("--quiet", action="store_true", help="print only a progress line per minute, not every event")
    args = ap.parse_args()

    path = os.path.join(args.data, "events", f"{args.match}.jsonl")
    events = iter_events(path)
    if args.limit:
        events = events[: args.limit]
    start_wall = time.monotonic()
    last_minute = -1
    sent = 0
    for e in events:
        target_wall = start_wall + e["timestamp_ms"] / 1000.0 / args.speed
        delay = target_wall - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if args.url:
            post(args.url, e)
        if not args.quiet:
            sys.stdout.write(json.dumps(e) + "\n")
            sys.stdout.flush()
        elif e["minute"] != last_minute:
            last_minute = e["minute"]
            sys.stdout.write(f"[{e['minute']:02d}'] {e['score_home']}-{e['score_away']}  events sent: {sent + 1}\n")
            sys.stdout.flush()
        sent += 1
    sys.stderr.write(f"Replay finished: {sent} events from {args.match} in {time.monotonic() - start_wall:.1f}s (speed x{args.speed})\n")


if __name__ == "__main__":
    main()
