#!/usr/bin/env python3
"""Test that ui.openPianoRoll actually retargets the piano roll window
to a specific channel × pattern, without needing the user to double-click first.

We cycle through several channel/pattern combos with pauses so you can watch
FL Studio's piano roll re-target each time.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client


def main() -> int:
    c = get_client()

    chans = c.call("channels.all")["channels"]
    pats = c.call("patterns.list")["patterns"]
    print(f"Channels: {[(ch['index'], ch['name']) for ch in chans]}")
    print(f"Patterns: {[(p['index'], p['name']) for p in pats]}")

    # Capture starting state so we can restore it at the end
    start_pattern = c.call("patterns.current")
    start_channel = c.call("ui.selectedChannel")
    print(f"\nStart state: pattern={start_pattern}  channel={start_channel}")

    # Walk a few combos. After each, the piano roll should be showing
    # THAT channel's notes for THAT pattern.
    combos = [
        (0, 1),   # Dark Resonance × Chords  (should show your existing chords)
        (1, 2),   # Funky Electricity × Melody 1 (should show your 1 note)
        (2, 3),   # Creeper Drone × Melody 2
        (0, 2),   # Dark Resonance × Melody 1 (empty)
    ]

    for ch_idx, pat_idx in combos:
        ch_name = chans[ch_idx]["name"] if ch_idx < len(chans) else "?"
        pat_name = next((p["name"] for p in pats if p["index"] == pat_idx), "?")
        print(f"\n→ Targeting channel {ch_idx} ({ch_name}) × pattern {pat_idx} ({pat_name})")
        result = c.call("ui.openPianoRoll", channel=ch_idx, pattern=pat_idx)
        print(f"  result: {result}")
        time.sleep(2.0)   # pause so you can verify in FL Studio

    # Restore starting state — extract just the indices
    restore_pattern = start_pattern.get("index")
    ch_dict = start_channel.get("channel") if isinstance(start_channel, dict) else None
    restore_channel = ch_dict.get("index") if isinstance(ch_dict, dict) else None

    if restore_pattern is not None and restore_channel is not None:
        ch_name = ch_dict.get("name", "?")
        pat_name = next((p["name"] for p in pats if p["index"] == restore_pattern), "?")
        print(f"\n↩ Restoring start state: channel {restore_channel} ({ch_name}) × pattern {restore_pattern} ({pat_name})")
        c.call("ui.openPianoRoll", channel=restore_channel, pattern=restore_pattern)
    else:
        print(f"\n(could not determine start state: pattern={start_pattern}, channel={start_channel})")

    print("\n✅ Done. You should have seen the piano roll re-target each time,")
    print("   and the final state should match where you started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
