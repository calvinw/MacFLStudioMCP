#!/usr/bin/env python3
"""Step 2 of the manual test plan — exercise individual bridge calls so you can
watch FL Studio respond live.

Pauses between steps so you can switch focus to FL Studio and confirm visually.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client


def step(label: str) -> None:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")


def pause(seconds: float = 1.5) -> None:
    time.sleep(seconds)


def main() -> int:
    c = get_client()

    # ---- 2a — Transport control --------------------------------------------
    step("2a — Transport control")
    print("Calling transport.start (watch FL — playhead should move)...")
    print(f"  result: {c.call('transport.start')}")
    pause(2.0)

    print("Reading transport.status while playing...")
    print(f"  result: {c.call('transport.status')}")
    pause(1.0)

    print("Calling transport.stop...")
    print(f"  result: {c.call('transport.stop')}")
    pause(0.5)

    # ---- 2b — Switch patterns ----------------------------------------------
    step("2b — Pattern switching")
    initial = c.call("patterns.current")
    print(f"Initial pattern: {initial}")

    for idx in (2, 3, 1):
        print(f"\nSwitching to pattern index={idx} (watch FL pattern selector)...")
        c.call("patterns.select", index=idx)
        pause(0.8)
        cur = c.call("patterns.current")
        print(f"  current is now: {cur}")

    # ---- 2c — Tempo --------------------------------------------------------
    step("2c — Tempo")
    status = c.call("transport.status")
    original_bpm = status.get("bpm", 130.0)
    print(f"Original BPM: {original_bpm}")

    for bpm in (140.0, 100.0, original_bpm):
        print(f"\nSetting BPM to {bpm} (watch FL's BPM display)...")
        c.call("transport.setTempo", bpm=bpm)
        pause(0.8)
        status = c.call("transport.status")
        print(f"  FL now reports: {status.get('bpm')} BPM")

    # ---- 2d — Channel info -------------------------------------------------
    step("2d — Channel rack")
    count = c.call("channels.count")
    print(f"Channel count: {count}")

    chans = c.call("channels.all")
    n_show = min(5, len(chans.get("channels", [])))
    print(f"\nFirst {n_show} channels:")
    for ch in chans.get("channels", [])[:n_show]:
        print(f"  [{ch.get('index')}] {ch.get('name')}")

    # ---- summary -----------------------------------------------------------
    step("✅ Step 2 complete")
    print("If you saw FL Studio play/stop, switch patterns, change BPM,")
    print("and the channel list above looks right, the main bridge is solid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
