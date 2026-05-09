#!/usr/bin/env python3
"""Debug script to test multi-pattern/multi-channel piano roll visibility.

Hypothesis: The issue is likely one of:
1. Pattern switching + piano roll retargeting leaves the viewport blank
2. The no-op optimization in h_ui_open_piano_roll prevents refresh when needed
3. Notes are added but piano roll viewport doesn't update until manual interaction
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client
from fl_studio_mcp.file_bridge import is_installed as pr_installed, stage_and_run, read_state


def banner(label: str) -> None:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")


def report_piano_roll_state() -> None:
    """Read and print current piano roll state."""
    state = read_state()
    if state:
        notes = state.get("notes", [])
        print(f"  Piano roll state: {len(notes)} note(s)")
        for n in notes[:5]:  # show first 5
            midi = n.get('midi', 'N/A')
            t = n.get('time')
            vel = n.get('velocity')
            time_str = f"{t:.2f}" if t is not None else "N/A"
            vel_str = f"{vel:.2f}" if vel is not None else "N/A"
            print(f"    - midi={midi}, time={time_str}, vel={vel_str}")
    else:
        print("  No piano roll state file found")


def main() -> int:
    c = get_client()

    banner("Pre-flight checks")
    print(f"ComposeWithLLM installed: {pr_installed()}")
    if not pr_installed():
        print("\n❌ pyscript not installed")
        return 1

    # Get patterns and channels
    patterns_list = c.call("patterns.list")["patterns"]
    channels_list = c.call("channels.all")["channels"]
    
    print(f"\nFound {len(patterns_list)} patterns:")
    for p in patterns_list:
        print(f"  [{p['index']}] {p['name']}")
    
    print(f"\nFound {len(channels_list)} channels:")
    for ch in channels_list:
        print(f"  [{ch['index']}] {ch['name']}")

    if len(patterns_list) < 2 or len(channels_list) < 1:
        print("\n❌ Need at least 2 patterns and 1 channel")
        return 1

    # Test scenario: iterate through first 3 patterns, add notes to channel 0
    test_patterns = patterns_list[:min(3, len(patterns_list))]
    test_channel = channels_list[0]["index"]
    
    banner(f"Test: Add notes to channel {test_channel} across multiple patterns")
    
    for i, pattern in enumerate(test_patterns):
        pattern_idx = pattern["index"]
        pattern_name = pattern["name"]
        
        print(f"\n--- Pattern {pattern_idx}: '{pattern_name}' ---")
        
        # Step 1: Switch to pattern
        print(f"  1. Switching to pattern {pattern_idx}...")
        c.call("patterns.select", index=pattern_idx)
        time.sleep(0.3)
        
        # Step 2: Select channel
        print(f"  2. Selecting channel {test_channel}...")
        c.call("channels.select", index=test_channel)
        time.sleep(0.3)
        
        # Step 3: Open piano roll (FORCE retarget)
        print(f"  3. Opening piano roll for channel={test_channel}, pattern={pattern_idx}...")
        result = c.call("ui.openPianoRoll", channel=test_channel, pattern=pattern_idx)
        print(f"     Result: ok={result.get('ok')}, retargeted={result.get('retargeted')}, no_op={result.get('no_op')}")
        time.sleep(0.5)
        
        # Step 4: Add a distinctive note (C4 + pattern offset)
        midi_note = 60 + (i * 2)  # C4, D4, E4
        print(f"  4. Adding note (MIDI {midi_note}) via Cmd+Opt+Y...")
        pr_result = stage_and_run([
            {"action": "clear"},
            {"action": "add_notes", "notes": [{
                "midi": midi_note,
                "time": 0.0,
                "duration": 4.0,
                "velocity": 0.85
            }]}
        ], wait_sec=3.0)
        
        print(f"     ok={pr_result.get('ok')}, hotkey_sent={pr_result.get('hotkey_sent')}")
        
        if pr_result.get("state"):
            notes = pr_result["state"].get("notes", [])
            print(f"     State returned: {len(notes)} note(s)")
        else:
            print("     ⚠️  No state returned!")
        
        # Step 5: Try reading state directly
        print(f"  5. Reading state file directly...")
        report_piano_roll_state()
        
        # Pause to see if FL shows the note
        print(f"  → Check FL Studio: Do you see the note (MIDI {midi_note}) in the piano roll?")
        time.sleep(2.0)

    banner("Experiment: Force re-open piano roll after edits")
    print("\nNow going back through patterns and re-opening piano roll...")
    
    for i, pattern in enumerate(test_patterns):
        pattern_idx = pattern["index"]
        pattern_name = pattern["name"]
        midi_note = 60 + (i * 2)
        
        print(f"\n  Pattern {pattern_idx} ('{pattern_name}'): should have MIDI {midi_note}")
        
        # Switch + select
        c.call("patterns.select", index=pattern_idx)
        c.call("channels.select", index=test_channel)
        time.sleep(0.2)
        
        # Try closing and re-opening piano roll
        print("    Closing piano roll...")
        c.call("ui.hideWindow", name="piano_roll")
        time.sleep(0.3)
        
        print("    Re-opening piano roll (new_window=1 should be used)...")
        result = c.call("ui.openPianoRoll", channel=test_channel, pattern=pattern_idx)
        print(f"    Result: retargeted={result.get('retargeted')}")
        
        time.sleep(1.5)
        print(f"    → Check FL: Do you NOW see MIDI {midi_note}?")

    banner("✅ Debug test complete")
    print("\nDid the notes appear consistently?")
    print("If not, the issue is likely:")
    print("  1. openEventEditor blanking viewport when reusing window")
    print("  2. Need to trigger a viewport refresh after retarget")
    print("  3. No-op optimization preventing necessary retargets")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
