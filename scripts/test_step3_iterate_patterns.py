#!/usr/bin/env python3
"""Step 3 — iterate through all patterns, opening each in the piano editor.

This is the workflow that was painful in the dev branch's event-tracking
approach: just list patterns, switch to each, show its piano roll. No state
mirror, no event subscriptions — every call is a fresh query into FL Studio.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client


def main() -> int:
    c = get_client()

    print("=" * 60)
    print("Iterate patterns and open each in the piano roll")
    print("=" * 60)

    plist = c.call("patterns.list")["patterns"]
    print(f"\nFound {len(plist)} patterns: "
          f"{', '.join(p['name'] for p in plist)}")

    # use channel 0 as the focus channel (you'll see its notes for each pattern)
    chans = c.call("channels.all")["channels"]
    if not chans:
        print("No channels in project — nothing to show in piano roll.")
        return 1
    focus_channel = chans[0]
    print(f"Focus channel: [{focus_channel['index']}] {focus_channel['name']}")
    print()

    for p in plist:
        print(f"→ Pattern {p['index']}: '{p['name']}'  ({p.get('color', '')})")

        # 1. switch to the pattern (watch FL's pattern selector change)
        c.call("patterns.select", index=p["index"])

        # 2. select our focus channel (the piano roll is per-channel-per-pattern)
        c.call("channels.select", index=focus_channel["index"])

        # 3. show the piano roll window for this pattern + channel
        c.call("ui.openPianoRoll", channel=focus_channel["index"], pattern=p["index"])

        # pause so you can visually verify FL flipped to the right pattern's piano roll
        time.sleep(1.5)

    # leave the user back on the first pattern at the end
    c.call("patterns.select", index=plist[0]["index"])

    print("\n✅ Done — FL Studio should have walked through every pattern's piano roll.")
    print("   No state-tracking, no event subscriptions — just on-demand queries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
