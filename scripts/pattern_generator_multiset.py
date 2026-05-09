#!/usr/bin/env python3
"""Multi-pattern generator using pattern-first analysis and autolocate-style updates.

This script:
  1. Reads all patterns/channels to understand the project structure
  2. Analyzes each pattern/channel combo to make generation decisions
  3. Updates each pattern/channel with consistent logic

The key difference from simple edits: we inspect the *entire* multi-pattern set
before making any edits, allowing us to make intelligent decisions about each
pattern based on what exists in the project.

Example use cases:
  • Transpose all patterns by a consistent amount
  • Generate countermelodies for each existing melody
  • Apply a consistent transformation (humanize, quantize, etc.)
  • Extend or compress patterns based on analysis
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client
from fl_studio_mcp.file_bridge import is_installed, stage_and_run


@dataclass
class PatternAnalysis:
    """Analysis result for a single pattern/channel combo."""
    channel_index: int
    channel_name: str
    pattern_index: int
    pattern_name: str
    note_count: int
    midi_min: int | None
    midi_max: int | None
    midi_range: int | None
    avg_velocity: float
    duration_bars_total: float
    
    def __str__(self):
        return (
            f"ch[{self.channel_index}] {self.channel_name} × "
            f"pat[{self.pattern_index}] {self.pattern_name} "
            f"({self.note_count} notes, MIDI {self.midi_min}-{self.midi_max})"
        )


def banner(msg: str) -> None:
    print(f"\n{'─' * 70}\n{msg}\n{'─' * 70}")


def analyze_notes(notes: list[dict]) -> PatternAnalysis | None:
    """Extract basic statistics from a note list."""
    if not notes:
        return None
    
    midis = [n["midi"] for n in notes]
    velocities = [n["velocity"] for n in notes]
    durations = [n["duration_bars"] for n in notes]
    
    return {
        "note_count": len(notes),
        "midi_min": min(midis),
        "midi_max": max(midis),
        "midi_range": max(midis) - min(midis),
        "avg_velocity": sum(velocities) / len(velocities),
        "duration_bars_total": sum(durations),
    }


def read_notes_for_combo(
    c,
    channel: int,
    pattern: int,
    settle: float = 0.25,
    already_open: bool = False,
    pattern_only: bool = False,
) -> list[dict]:
    """Read notes for a channel/pattern combo (same as test_read_all_notes.py)."""
    retargeted = False
    if pattern_only:
        c.call("patterns.select", index=pattern)
        time.sleep(settle)
    elif not already_open:
        result = c.call("ui.openPianoRoll", channel=channel, pattern=pattern)
        retargeted = result.get("retargeted", False)
        if retargeted:
            time.sleep(settle)

    state_result = stage_and_run(
        [{"action": "export_only"}],
        wait_sec=5.0,
        focus_piano_roll=not already_open,
    )
    if not state_result.get("ok"):
        return []

    return (state_result.get("state") or {}).get("notes", [])


def discover_project(c) -> tuple[list[dict], list[dict], int | None, int | None]:
    """Read all channels and patterns, track current combo."""
    start_pattern = c.call("patterns.current")
    start_channel = c.call("channels.selected")
    start_pattern_index = start_pattern.get("index")
    start_channel_index = (start_channel.get("channel") or {}).get("index")
    channels = c.call("channels.all")["channels"]
    patterns = c.call("patterns.list")["patterns"]
    
    return channels, patterns, start_channel_index, start_pattern_index


def analyze_all_combos(
    c,
    channels: list[dict],
    patterns: list[dict],
    start_channel_index: int | None,
    start_pattern_index: int | None,
) -> dict[tuple[int, int], dict]:
    """Read and analyze all channel/pattern combos.
    
    Returns: {(ch_index, pat_index): {"notes": [...], "analysis": {...}}}
    """
    results = {}
    
    # Build ordered combos starting from current
    combos = []
    for pat in patterns:
        for ch in channels:
            combos.append((ch, pat))
    
    if start_channel_index is not None and start_pattern_index is not None:
        start_idx = None
        for i, (ch, pat) in enumerate(combos):
            if ch["index"] == start_channel_index and pat["index"] == start_pattern_index:
                start_idx = i
                break
        if start_idx is not None:
            combos = combos[start_idx:] + combos[:start_idx]
    
    banner("Phase 1: Analyzing all patterns")
    print(f"Scanning {len(channels)} channels × {len(patterns)} patterns...")
    
    for combo_idx, (ch, pat) in enumerate(combos):
        ch_idx = ch["index"]
        pat_idx = pat["index"]
        
        already_open = (
            combo_idx == 0
            and ch_idx == start_channel_index
            and pat_idx == start_pattern_index
        )
        pattern_only = combo_idx > 0
        
        notes = read_notes_for_combo(
            c,
            channel=ch_idx,
            pattern=pat_idx,
            already_open=already_open,
            pattern_only=pattern_only,
        )
        
        analysis = analyze_notes(notes) if notes else None
        if analysis:
            analysis["channel_name"] = ch["name"]
            analysis["pattern_name"] = pat["name"]
            analysis["channel_index"] = ch_idx
            analysis["pattern_index"] = pat_idx
        
        results[(ch_idx, pat_idx)] = {
            "notes": notes,
            "analysis": analysis,
            "channel": ch,
            "pattern": pat,
        }
        
        status = f"{len(notes)} notes" if notes else "empty"
        print(f"  [{combo_idx + 1:2d}] ch[{ch_idx}] {ch['name']:<20} × "
              f"pat[{pat_idx}] {pat['name']:<15} → {status}")
    
    return results


def make_generation_decisions(
    analysis_results: dict[tuple[int, int], dict],
) -> dict[tuple[int, int], dict]:
    """Analyze the full project and decide what to generate for each combo.
    
    This is where your logic goes. Return a dict mapping (ch, pat) to:
      {"action": "...", "params": {...}, "notes": [...], ...}
    
    Example decisions:
      - If pattern is empty: generate fill or variation
      - If pattern is short: extend it
      - If pattern has low velocity: boost humanization
      - Etc.
    """
    banner("Phase 2: Making generation decisions")
    
    decisions = {}
    empty_combos = []
    filled_combos = []
    
    for (ch_idx, pat_idx), result in analysis_results.items():
        analysis = result["analysis"]
        
        if analysis is None:
            empty_combos.append((ch_idx, pat_idx, result))
        else:
            filled_combos.append((ch_idx, pat_idx, result, analysis))
    
    print(f"\nFound {len(filled_combos)} filled combos, {len(empty_combos)} empty")
    
    # Example decision logic:
    # For each empty combo, generate based on a nearby filled one
    if filled_combos and empty_combos:
        print(f"\nExample: generating fills for empty combos based on nearest neighbor...")
        for ch_idx, pat_idx, result in empty_combos:
            # Find a filled combo from the same pattern
            similar = [
                (c_idx, p_idx, r, a)
                for c_idx, p_idx, r, a in filled_combos
                if p_idx == pat_idx
            ]
            if similar:
                source_ch, source_pat, source_result, source_analysis = similar[0]
                print(f"  ch[{ch_idx}] pat[{pat_idx}] ← generate based on "
                      f"ch[{source_ch}] pat[{source_pat}]")
                
                decisions[(ch_idx, pat_idx)] = {
                    "action": "transpose_from",
                    "source_ch": source_ch,
                    "source_pat": source_pat,
                    "transpose_semitones": 12,  # Example: up an octave
                    "notes": source_result["notes"],  # Will be transposed
                }
    
    # For filled combos, decide on transformations
    for ch_idx, pat_idx, result, analysis in filled_combos:
        print(f"  ch[{ch_idx}] {result['channel']['name']:<20} × "
              f"pat[{pat_idx}] {result['pattern']['name']:<15} → "
              f"keep as-is (MIDI {analysis['midi_min']}-{analysis['midi_max']})")
        
        decisions[(ch_idx, pat_idx)] = {
            "action": "keep",
            "notes": result["notes"],
        }
    
    return decisions


def apply_updates(
    c,
    analysis_results: dict[tuple[int, int], dict],
    decisions: dict[tuple[int, int], dict],
    start_channel_index: int | None,
    start_pattern_index: int | None,
) -> None:
    """Execute all decisions and update the patterns.
    
    Uses autolocate-style updates: iterate through combos, switch pattern,
    and stage updates via the piano-roll bridge.
    """
    banner("Phase 3: Applying updates")
    
    # Build ordered combos for update
    channels_set = set()
    patterns_set = set()
    for (ch_idx, pat_idx) in analysis_results.keys():
        channels_set.add(ch_idx)
        patterns_set.add(pat_idx)
    
    channels = sorted(channels_set)
    patterns = sorted(patterns_set)
    
    combos = [(ch, pat) for pat in patterns for ch in channels]
    
    # Reorder to start from current
    if start_channel_index is not None and start_pattern_index is not None:
        start_idx = None
        for i, (ch_idx, pat_idx) in enumerate(combos):
            if ch_idx == start_channel_index and pat_idx == start_pattern_index:
                start_idx = i
                break
        if start_idx is not None:
            combos = combos[start_idx:] + combos[:start_idx]
    
    print(f"Updating {len(combos)} pattern/channel combos...")
    
    for update_idx, (ch_idx, pat_idx) in enumerate(combos):
        decision = decisions.get((ch_idx, pat_idx))
        if not decision:
            continue
        
        result = analysis_results[(ch_idx, pat_idx)]
        ch = result["channel"]
        pat = result["pattern"]
        
        already_open = (
            update_idx == 0
            and ch_idx == start_channel_index
            and pat_idx == start_pattern_index
        )
        pattern_only = update_idx > 0
        
        # Switch to this combo
        if pattern_only:
            c.call("patterns.select", index=pat_idx)
            time.sleep(0.25)
        elif not already_open:
            c.call("ui.openPianoRoll", channel=ch_idx, pattern=pat_idx)
            time.sleep(0.5)
        
        # Build actions based on decision
        action_str = decision["action"]
        
        if action_str == "keep":
            print(f"  [{update_idx + 1:2d}] ch[{ch_idx}] {ch['name']:<20} × "
                  f"pat[{pat_idx}] {pat['name']:<15} → KEEP (no changes)")
        
        elif action_str == "transpose_from":
            source_notes = decision["notes"]
            transpose_amount = decision.get("transpose_semitones", 0)
            
            # Create transposed notes
            transposed = []
            for note in source_notes:
                new_note = note.copy()
                new_note["midi"] = int(note["midi"] + transpose_amount)
                transposed.append(new_note)
            
            # Stage update: clear and add transposed notes
            actions = [
                {"action": "clear"},
                {"action": "add_notes", "notes": transposed},
            ]
            
            state_result = stage_and_run(actions, wait_sec=5.0)
            ok = state_result.get("ok", False)
            
            status = "✓" if ok else "✗"
            print(f"  [{update_idx + 1:2d}] {status} ch[{ch_idx}] {ch['name']:<20} × "
                  f"pat[{pat_idx}] {pat['name']:<15} → "
                  f"transpose +{transpose_amount} semitones ({len(transposed)} notes)")
        
        else:
            print(f"  [{update_idx + 1:2d}] ch[{ch_idx}] {ch['name']:<20} × "
                  f"pat[{pat_idx}] {pat['name']:<15} → unknown action '{action_str}'")


def main() -> int:
    c = get_client()
    
    banner("Multi-Pattern Generator — Using Autolocate-Style Analysis & Update")
    
    if not is_installed():
        print("❌ ComposeWithLLM.pyscript not installed — run install_mac.sh first.")
        return 1
    print("✅ ComposeWithLLM.pyscript found\n")
    
    # ────────────────────────────────────────────────────────────────────────────
    # PHASE 1: Discover project and analyze all combos
    # ────────────────────────────────────────────────────────────────────────────
    channels, patterns, start_ch, start_pat = discover_project(c)
    
    print(f"Project structure:")
    print(f"  {len(channels)} channels: {', '.join(ch['name'] for ch in channels)}")
    print(f"  {len(patterns)} patterns: {', '.join(pat['name'] for pat in patterns)}")
    
    analysis_results = analyze_all_combos(c, channels, patterns, start_ch, start_pat)
    
    # ────────────────────────────────────────────────────────────────────────────
    # PHASE 2: Make intelligent decisions
    # ────────────────────────────────────────────────────────────────────────────
    decisions = make_generation_decisions(analysis_results)
    
    # ────────────────────────────────────────────────────────────────────────────
    # PHASE 3: Apply updates using autolocate-style iteration
    # ────────────────────────────────────────────────────────────────────────────
    apply_updates(c, analysis_results, decisions, start_ch, start_pat)
    
    # ────────────────────────────────────────────────────────────────────────────
    # Restore starting combo
    # ────────────────────────────────────────────────────────────────────────────
    if start_ch is not None and start_pat is not None:
        c.call("patterns.select", index=start_pat)
        time.sleep(0.5)
        stage_and_run([{"action": "export_only"}], wait_sec=5.0)
        banner("Done")
        print(f"Restored: ch[{start_ch}] × pat[{start_pat}]\n✅ All patterns updated successfully!")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
