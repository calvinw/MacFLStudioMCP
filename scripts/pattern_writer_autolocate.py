#!/usr/bin/env python3
"""Write notes back to all pattern/channel combos using autolocate-style switching.

This is the **inverse of autolocate**: instead of reading all notes,
it writes them back using the same efficient pattern-switching approach.

Workflow:
  1. Run piano_roll_read_patterns_autolocate() to get all notes
  2. Modify the notes however you want (transpose, humanize, etc.)
  3. Pass the modified notes to this script
  4. It writes them back using pattern-only switching (no unnecessary retargeting)

Usage:
    from fl_studio_mcp.bridge_client import get_client
    from fl_studio_mcp.file_bridge import stage_and_run
    
    # Get all notes
    result = c.call("piano_roll_read_patterns_autolocate", patterns_to_read=None)
    
    # Modify them...
    modified_results = transform_notes(result["results"])
    
    # Write them back
    autolocate_write_patterns(c, modified_results, start_pattern=result["start_pattern"]["index"])
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client
from fl_studio_mcp.file_bridge import is_installed, stage_and_run


def banner(msg: str) -> None:
    print(f"\n{'─' * 70}\n{msg}\n{'─' * 70}")


def autolocate_write_patterns(
    c,
    results: list[dict],
    start_pattern: Optional[int] = None,
    restore_start: bool = True,
) -> dict:
    """Write notes back to all patterns using autolocate-style pattern switching.
    
    Args:
        c: BridgeClient
        results: List of dicts from piano_roll_read_patterns_autolocate results,
                 but with modified "notes" in each entry
        start_pattern: Starting pattern index (to restore at end if restore_start=True)
        restore_start: Whether to restore the starting pattern
    
    Returns:
        Summary dict with counts and results
    """
    banner("Writing patterns using autolocate-style switching")
    
    if not results:
        print("❌ No results to write")
        return {"ok": False, "updated": 0, "failed": 0}
    
    updated_count = 0
    failed_count = 0
    
    print(f"Writing {len(results)} pattern/channel combos...\n")
    
    # Process each combo
    for combo_idx, result in enumerate(results):
        pattern_info = result.get("pattern", {})
        channel_info = result.get("channel", {})
        notes = result.get("notes", [])
        
        pattern_idx = pattern_info.get("index")
        channel_idx = channel_info.get("index")
        pattern_name = pattern_info.get("name", "Unknown")
        channel_name = channel_info.get("name", "Unknown")
        
        if pattern_idx is None or channel_idx is None:
            print(f"  [{combo_idx + 1:2d}] ❌ Missing pattern or channel info, skipping")
            failed_count += 1
            continue
        
        # For autolocate-style: first combo may already be open, rest use pattern_only
        already_open = combo_idx == 0
        pattern_only = combo_idx > 0
        
        # Switch to pattern/channel
        if pattern_only:
            # For subsequent combos: select pattern, then make sure channel is right
            c.call("patterns.select", index=pattern_idx)
            c.call("channels.select", index=channel_idx)
            time.sleep(0.25)
        elif not already_open:
            c.call("ui.openPianoRoll", channel=channel_idx, pattern=pattern_idx)
            time.sleep(0.5)
        
        # Convert notes: pyscript add_notes expects "time" and "duration"
        # in QUARTER NOTES, but autolocate returns "time_bars" / "duration_bars".
        # 1 bar = 4 quarter notes.
        converted_notes = []
        for n in notes:
            cn = dict(n)
            if "time" not in cn:
                cn["time"] = cn.get("time_bars", cn.get("time_quarters", 0)) * 4 \
                    if "time_bars" in cn else cn.get("time_quarters", 0)
            if "duration" not in cn:
                cn["duration"] = cn.get("duration_bars", cn.get("duration_quarters", 1.0)) * 4 \
                    if "duration_bars" in cn else cn.get("duration_quarters", 1.0)
            converted_notes.append(cn)

        # Build update actions: clear then add notes
        actions = [
            {"action": "clear"},
            {"action": "add_notes", "notes": converted_notes},
        ]
        
        # Write via piano-roll bridge
        state_result = stage_and_run(actions, wait_sec=5.0)
        ok = state_result.get("ok", False)
        
        status = "✓" if ok else "✗"
        note_summary = f"{len(notes)} notes" if notes else "empty"
        
        print(f"  [{combo_idx + 1:2d}] {status} ch[{channel_idx}] {channel_name:<20} × "
              f"pat[{pattern_idx}] {pattern_name:<15} → {note_summary}")
        
        if ok:
            updated_count += 1
        else:
            failed_count += 1
            if state_result.get("note"):
                print(f"        hint: {state_result['note']}")
    
    # Restore starting pattern if requested
    if restore_start and start_pattern is not None:
        banner("Restoring starting pattern")
        c.call("patterns.select", index=start_pattern)
        time.sleep(0.5)
        state_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
        print(f"✅ Restored pattern {start_pattern}\n")
    
    # Summary
    banner("Write complete")
    print(f"Updated:  {updated_count}")
    print(f"Failed:   {failed_count}")
    print(f"Total:    {len(results)}\n")
    
    return {
        "ok": failed_count == 0,
        "updated": updated_count,
        "failed": failed_count,
        "total": len(results),
    }


def read_all_patterns_autolocate(c) -> tuple[list[dict], int | None]:
    """Read all patterns using autolocate-style switching (same as piano_roll_read_patterns_autolocate)."""
    from fl_studio_mcp.file_bridge import stage_and_run
    
    start_pattern = c.call("patterns.current")
    start_channel = c.call("channels.selected")
    start_pattern_index = start_pattern.get("index")
    start_channel_index = (start_channel.get("channel") or {}).get("index")
    channels = c.call("channels.all")["channels"]
    patterns = c.call("patterns.list")["patterns"]
    
    results = []
    
    # Build ordered combos
    combos = [(ch, pat) for pat in patterns for ch in channels]
    if start_channel_index is not None and start_pattern_index is not None:
        start_idx = None
        for i, (ch, pat) in enumerate(combos):
            if ch["index"] == start_channel_index and pat["index"] == start_pattern_index:
                start_idx = i
                break
        if start_idx is not None:
            combos = combos[start_idx:] + combos[:start_idx]
    
    # Read each combo
    for combo_idx, (ch, pat) in enumerate(combos):
        already_open = (combo_idx == 0 and ch["index"] == start_channel_index 
                       and pat["index"] == start_pattern_index)
        pattern_only = combo_idx > 0
        
        if pattern_only:
            c.call("patterns.select", index=pat["index"])
            time.sleep(0.25)
        elif not already_open:
            c.call("ui.openPianoRoll", channel=ch["index"], pattern=pat["index"])
            time.sleep(0.5)
        
        state_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0,
                                     focus_piano_roll=not already_open)
        notes = (state_result.get("state") or {}).get("notes", []) if state_result.get("ok") else []
        
        results.append({
            "pattern": {"index": pat["index"], "name": pat["name"]},
            "channel": {"index": ch["index"], "name": ch["name"]},
            "notes": notes,
        })
    
    return results, start_pattern_index


def main_demo() -> int:
    """Demo: read notes, modify them, write them back."""
    c = get_client()
    
    banner("Autolocate Write Demo")
    
    if not is_installed():
        print("❌ ComposeWithLLM.pyscript not installed — run install_mac.sh first.")
        return 1
    print("✅ ComposeWithLLM.pyscript found\n")
    
    # Step 1: Read all notes using autolocate
    print("Step 1: Reading all patterns using autolocate...")
    results, start_pattern = read_all_patterns_autolocate(c)
    
    if not results:
        print("❌ Failed to read patterns")
        return 1
    
    print(f"✓ Read {len(results)} pattern/channel combos")
    
    # Step 2: Modify notes (example: transpose all non-empty patterns by +5 semitones)
    banner("Step 2: Modifying notes")
    print("Example: transposing all patterns by +5 semitones...\n")
    
    modified_results = []
    for result in results:
        modified = result.copy()
        notes = result.get("notes", [])
        
        if notes:
            # Transpose by 5 semitones
            transposed = []
            for note in notes:
                new_note = note.copy()
                new_note["midi"] = int(note["midi"] + 5)
                transposed.append(new_note)
            modified["notes"] = transposed
            print(f"  ch[{result['channel']['index']}] pat[{result['pattern']['index']}] → "
                  f"transposed {len(notes)} notes by +5 semitones")
        else:
            print(f"  ch[{result['channel']['index']}] pat[{result['pattern']['index']}] → "
                  f"empty (no change)")
        
        modified_results.append(modified)
    
    # Step 3: Write modified notes back
    banner("Step 3: Writing modified notes back")
    write_result = autolocate_write_patterns(
        c,
        modified_results,
        start_pattern=start_pattern,
        restore_start=True,
    )
    
    if write_result["ok"]:
        print("✅ All patterns updated successfully!")
        return 0
    else:
        print(f"⚠️  {write_result['failed']} patterns failed to update")
        return 1


def main_from_json(json_path: str) -> int:
    """Entry point: read a JSON file produced by piano_roll_read_patterns_autolocate,
    then write those notes back to FL Studio.

    The JSON must have the shape:
        {
            "start_pattern": {"index": int, ...},
            "results": [
                {"pattern": {...}, "channel": {...}, "notes": [...]},
                ...
            ]
        }

    This is exactly the format returned by the MCP tool
    piano_roll_read_patterns_autolocate — just save it, modify the notes,
    then pass the file here.
    """
    import json

    c = get_client()

    if not is_installed():
        print("❌ ComposeWithLLM.pyscript not installed — run install_mac.sh first.")
        return 1

    with open(json_path) as f:
        data = json.load(f)

    results = data.get("results", [])
    start_pattern = (data.get("start_pattern") or {}).get("index")

    if not results:
        print("❌ No results found in JSON")
        return 1

    print(f"✅ Loaded {len(results)} pattern/channel combos from {json_path}")

    write_result = autolocate_write_patterns(
        c,
        results,
        start_pattern=start_pattern,
        restore_start=True,
    )

    if write_result["ok"]:
        print("✅ All patterns updated successfully!")
        return 0
    else:
        print(f"⚠️  {write_result['failed']} patterns failed to update")
        return 1


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) == 2 and _sys.argv[1].endswith(".json"):
        raise SystemExit(main_from_json(_sys.argv[1]))
    else:
        raise SystemExit(main_demo())
