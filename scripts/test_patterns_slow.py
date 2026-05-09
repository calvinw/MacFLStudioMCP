#!/usr/bin/env python3
"""Slowly iterate through patterns, editing the main channel for each.

Pattern assignments:
- Pattern 1 (Chords) → Channel 0 (Dark Resonance)
- Pattern 2 (Melody 1) → Channel 1 (Funky Electricity)
- Pattern 3 (Melody 2) → Channel 2 (Creeper Drone)
- Pattern 4 (Melody 3) → Channel 3 (Purity Cube)

We'll add notes WITHOUT clearing first, and keep the piano roll open throughout.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client
from fl_studio_mcp.file_bridge import stage_and_run


def main() -> int:
    c = get_client()
    
    print("\n" + "=" * 70)
    print("Slowly testing pattern/channel switching with piano roll edits")
    print("=" * 70)
    
    # Get patterns and channels
    patterns_list = c.call("patterns.list")["patterns"]
    channels_list = c.call("channels.all")["channels"]
    
    print("\nAvailable patterns:")
    for p in patterns_list:
        print(f"  [{p['index']}] {p['name']}")
    
    print("\nAvailable channels:")
    for ch in channels_list:
        print(f"  [{ch['index']}] {ch['name']}")
    
    # Define pattern → channel mapping
    pattern_channel_map = {
        1: 0,  # Chords → Dark Resonance
        2: 1,  # Melody 1 → Funky Electricity
        3: 2,  # Melody 2 → Creeper Drone
        4: 3,  # Melody 3 → Purity Cube
    }
    
    print("\n" + "=" * 70)
    print("Pattern → Channel Mapping:")
    for pattern_idx, channel_idx in pattern_channel_map.items():
        pattern_name = next((p['name'] for p in patterns_list if p['index'] == pattern_idx), '?')
        channel_name = next((ch['name'] for ch in channels_list if ch['index'] == channel_idx), '?')
        print(f"  Pattern {pattern_idx} ({pattern_name}) → Channel {channel_idx} ({channel_name})")
    print("=" * 70)
    
    # Process each pattern
    for pattern_idx in sorted(pattern_channel_map.keys()):
        channel_idx = pattern_channel_map[pattern_idx]
        
        pattern_name = next((p['name'] for p in patterns_list if p['index'] == pattern_idx), '?')
        channel_name = next((ch['name'] for ch in channels_list if ch['index'] == channel_idx), '?')
        
        print(f"\n{'─' * 70}")
        print(f"PATTERN {pattern_idx}: '{pattern_name}' → CHANNEL {channel_idx}: '{channel_name}'")
        print(f"{'─' * 70}")
        
        # Step 1: Switch to the pattern
        print(f"\n  Step 1: Switching to pattern {pattern_idx} ('{pattern_name}')...")
        c.call("patterns.select", index=pattern_idx)
        print(f"    ✓ Pattern {pattern_idx} is now selected")
        time.sleep(0.5)
        
        # Step 2: Select the channel
        print(f"\n  Step 2: Selecting channel {channel_idx} ('{channel_name}')...")
        c.call("channels.select", index=channel_idx)
        print(f"    ✓ Channel {channel_idx} is now selected")
        time.sleep(0.5)
        
        # Step 3: Open piano roll for this channel + pattern
        print(f"\n  Step 3: Opening piano roll for pattern={pattern_idx}, channel={channel_idx}...")
        result = c.call("ui.openPianoRoll", channel=channel_idx, pattern=pattern_idx)
        if result.get('retargeted'):
            print(f"    ✓ Piano roll retargeted to show pattern {pattern_idx}, channel {channel_idx}")
        else:
            print(f"    ✓ Piano roll already showing the correct content (no retarget needed)")
        time.sleep(0.5)
        
        # Step 4: Add a chord (C major with root at C4 + pattern offset)
        # Pattern 1: C4, E4, G4 (60, 64, 67)
        # Pattern 2: D4, F#4, A4 (62, 66, 69)
        # Pattern 3: E4, G#4, B4 (64, 68, 71)
        # Pattern 4: F4, A4, C5 (65, 69, 72)
        root_note = 60 + (pattern_idx - 1)
        chord_notes = [root_note, root_note + 4, root_note + 7]
        
        note_names = {60: 'C4', 62: 'D4', 64: 'E4', 65: 'F4'}
        chord_name = note_names.get(root_note, f'MIDI{root_note}')
        
        print(f"\n  Step 4: Adding {chord_name} major chord (MIDI {chord_notes}) via Cmd+Opt+Y...")
        print(f"    (NOT clearing first - adding to existing notes)")
        
        pr_result = stage_and_run([
            {"action": "add_notes", "notes": [
                {"midi": chord_notes[0], "time": 0.0, "duration": 4.0, "velocity": 0.85},
                {"midi": chord_notes[1], "time": 0.0, "duration": 4.0, "velocity": 0.85},
                {"midi": chord_notes[2], "time": 0.0, "duration": 4.0, "velocity": 0.85},
            ]}
        ], wait_sec=3.0)
        
        if pr_result.get("ok"):
            state = pr_result.get("state")
            if state:
                note_count = len(state.get("notes", []))
                print(f"    ✓ Notes added! Piano roll now has {note_count} note(s)")
            else:
                print(f"    ✓ Edit triggered (waiting for state update...)")
        else:
            print(f"    ⚠️  Edit failed: {pr_result.get('error', 'unknown error')}")
        
        print(f"\n  → Check FL Studio: Do you see the {chord_name} major chord in the piano roll?")
        print(f"     The piano roll should still be open and showing pattern {pattern_idx}, channel {channel_idx}")
        
        # Pause to let user observe
        time.sleep(3.0)
    
    print("\n" + "=" * 70)
    print("✅ Test complete!")
    print("\nDid the notes appear for each pattern?")
    print("Did the piano roll window stay open throughout?")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
