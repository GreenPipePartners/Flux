#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import statistics
from pathlib import Path


EVENT_RE = re.compile(r"^\s*(click|show)\s*:\s*(\d+):(\d+)\s*$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze click-to-show timings from a perspective_test.md file.")
    parser.add_argument("path", nargs="?", default="perspective_test.md", help="Input markdown file")
    parser.add_argument("--fps", type=float, default=25.0, help="Frames per second for timestamps like seconds:frames")
    parser.add_argument("--wrap-seconds", type=float, default=60.0, help="Timestamp wrap interval in seconds")
    return parser.parse_args()


def timestamp_seconds(value: str, *, fps: float) -> float:
    seconds, frames = value.split(":", 1)
    return int(seconds) + int(frames) / fps


def percentile(values: list[float], percent: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = int((percent / 100) * (len(ordered) - 1))
    return ordered[index]


def parse_events(path: Path, *, fps: float) -> list[tuple[str, float, int, str]]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = EVENT_RE.match(line)
        if not match:
            continue
        kind = match.group(1).lower()
        raw = f"{match.group(2)}:{match.group(3)}"
        events.append((kind, timestamp_seconds(raw, fps=fps), line_number, raw))
    return events


def click_show_durations(events: list[tuple[str, float, int, str]], *, wrap_seconds: float) -> list[float]:
    durations = []
    pending_click: tuple[float, int, str] | None = None
    for kind, timestamp, line_number, raw in events:
        if kind == "click":
            pending_click = (timestamp, line_number, raw)
            continue
        if pending_click is None:
            continue
        click_time, _click_line, _click_raw = pending_click
        duration = timestamp - click_time
        if duration < 0:
            duration += wrap_seconds
        durations.append(duration)
        pending_click = None
    return durations


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    events = parse_events(path, fps=args.fps)
    durations = click_show_durations(events, wrap_seconds=args.wrap_seconds)
    if not durations:
        print("No click/show pairs found.")
        return 1

    print(f"file={path}")
    print(f"pairs={len(durations)} fps={args.fps:g} wrap_seconds={args.wrap_seconds:g}")
    print(f"min={min(durations):.3f}s")
    print(f"avg={statistics.mean(durations):.3f}s")
    print(f"median={statistics.median(durations):.3f}s")
    print(f"p90={percentile(durations, 90):.3f}s")
    print(f"p95={percentile(durations, 95):.3f}s")
    print(f"p99={percentile(durations, 99):.3f}s")
    print(f"max={max(durations):.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
