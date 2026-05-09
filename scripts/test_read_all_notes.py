#!/usr/bin/env python3
"""Read all MIDI notes from every channel × pattern combination.

This is the correct pre-edit snapshot workflow:

  For each (channel, pattern):
    1. ui.openPianoRoll(channel, pattern)  — retarget FL's piano roll
    2. export_only via Cmd+Opt+Y           — ComposeWithLLM dumps state
    3. collect state["notes"]

Prerequisites:
  • ComposeWithLLM is the active piano-roll script (bound once from the
    piano roll scripts dropdown — persists across channel/pattern switches)
  • Terminal has Accessibility permission so pynput can send Cmd+Opt+Y
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client
from fl_studio_mcp.file_bridge import is_installed, stage_and_run


# Project-specific main-channel map for this test session. This avoids retargeting
# through known-empty channel/pattern combinations, which makes FL's piano-roll UI
# flicker less while still reading the musically relevant notes.
MAIN_CHANNEL_BY_PATTERN_NAME = {
    "Chords": "Dark Resonance",
    "Melody 1": "Funky Electricity",
}


def banner(msg: str) -> None:
    print(f"\n{'─' * 60}\n{msg}\n{'─' * 60}")


def read_notes_for(c, channel: int, pattern: int, settle: float = 0.25,
                   already_open: bool = False,
                   pattern_only: bool = False) -> list[dict]:
    """Open channel/pattern in the piano roll and export its notes.

    Returns the list of note dicts from ComposeWithLLM's state export.
    Each note has: midi, time_bars, duration_bars, velocity, pan, …
    """
    retargeted = False
    if pattern_only:
        c.call("patterns.select", index=pattern)
        time.sleep(settle)
    elif not already_open:
        result = c.call("ui.openPianoRoll", channel=channel, pattern=pattern)
        retargeted = result.get("retargeted", False)
        if retargeted:
            time.sleep(settle)   # let FL finish initialising the new piano roll

    state_result = stage_and_run(
        [{"action": "export_only"}],
        wait_sec=5.0,
        focus_piano_roll=not already_open,
    )
    if not state_result.get("ok"):
        print(f"    ⚠ export failed: hotkey_sent={state_result.get('hotkey_sent')} "
              f"  retargeted={retargeted}")
        if state_result.get("note"):
            print(f"    hint: {state_result['note']}")
        return []

    return (state_result.get("state") or {}).get("notes", [])


def refresh_combo(c, channel: int, pattern: int, settle: float = 0.35) -> bool:
    """Select/open a combo and run one export pass to refresh FL's piano roll."""
    c.call("patterns.select", index=pattern)
    c.call("channels.select", index=channel)
    result = c.call("ui.openPianoRoll", channel=channel, pattern=pattern)
    if result.get("retargeted"):
        time.sleep(settle)
    state_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
    return bool(state_result.get("ok"))


def ordered_combos(channels: list[dict], patterns: list[dict], start_channel: int | None,
                   start_pattern: int | None) -> list[tuple[dict, dict]]:
    """Return channel/pattern pairs, starting with the currently focused pair."""
    channel_by_name = {ch["name"]: ch for ch in channels}
    combos = []
    for pat in patterns:
        main_channel_name = MAIN_CHANNEL_BY_PATTERN_NAME.get(pat["name"])
        main_channel = channel_by_name.get(main_channel_name) if main_channel_name else None
        if main_channel:
            combos.append((main_channel, pat))

    if not combos:
        combos = [(ch, pat) for ch in channels for pat in patterns]

    if start_channel is None or start_pattern is None:
        return combos
    start_idx = None
    for i, (ch, pat) in enumerate(combos):
        if ch["index"] == start_channel and pat["index"] == start_pattern:
            start_idx = i
            break
    if start_idx is None:
        return combos
    return combos[start_idx:] + combos[:start_idx]


def main() -> int:
    c = get_client()

    banner("Pre-flight")
    if not is_installed():
        print("❌ ComposeWithLLM.pyscript not installed — run install_mac.sh first.")
        return 1
    print("✅ ComposeWithLLM.pyscript found")

    # ── Discover channels and patterns ──────────────────────────────────────
    start_pattern = c.call("patterns.current")
    start_channel = c.call("channels.selected")
    start_pattern_index = start_pattern.get("index")
    start_channel_index = (start_channel.get("channel") or {}).get("index")
    channels = c.call("channels.all")["channels"]
    patterns = c.call("patterns.list")["patterns"]

    print(f"\nChannels ({len(channels)}):")
    for ch in channels:
        print(f"  [{ch['index']}] {ch['name']}")

    print(f"\nPatterns ({len(patterns)}):")
    for p in patterns:
        print(f"  [{p['index']}] {p['name']}")

    # ── Read notes for every combination ────────────────────────────────────
    banner("Reading notes — channel × pattern")

    # snapshot[channel_index][pattern_index] = list of note dicts
    snapshot: dict[int, dict[int, list[dict]]] = {}

    combos = ordered_combos(channels, patterns, start_channel_index, start_pattern_index)
    if start_channel_index is not None and start_pattern_index is not None:
        print(f"\nStarting from current combo: ch[{start_channel_index}] × pat[{start_pattern_index}]")

    for ch in channels:
        ch_idx = ch["index"]
        snapshot[ch_idx] = {}

    for combo_index, (ch, pat) in enumerate(combos):
        ch_idx = ch["index"]
        pat_idx = pat["index"]
        label = f"ch[{ch_idx}] {ch['name']!r}  ×  pat[{pat_idx}] {pat['name']!r}"
        print(f"\n→ {label}")

        already_open = (
            combo_index == 0
            and ch_idx == start_channel_index
            and pat_idx == start_pattern_index
        )
        pattern_only = combo_index > 0
        notes = read_notes_for(
            c,
            channel=ch_idx,
            pattern=pat_idx,
            settle=0.5,
            already_open=already_open,
            pattern_only=pattern_only,
        )
        snapshot[ch_idx][pat_idx] = notes

        if notes:
            midis = sorted(n["midi"] for n in notes)
            print(f"  {len(notes)} note(s): midi={midis}")
        else:
            print(f"  (empty)")

    # ── Summary ─────────────────────────────────────────────────────────────
    banner("Snapshot summary")
    total_notes = sum(
        len(notes)
        for pat_dict in snapshot.values()
        for notes in pat_dict.values()
    )
    print(f"Total notes across all channel × pattern combos: {total_notes}")
    print()

    # Print non-empty combos in detail
    for ch in channels:
        for pat in patterns:
            notes = snapshot.get(ch["index"], {}).get(pat["index"], [])
            if notes:
                print(f"  ch[{ch['index']}] {ch['name']!r}  ×  pat[{pat['index']}] {pat['name']!r}")
                for n in notes:
                    print(f"    midi={n['midi']:3d}  t={n['time_bars']:.3f}b  "
                          f"dur={n['duration_bars']:.3f}b  vel={n['velocity']:.2f}")

    restore_pattern = start_pattern_index
    restore_channel = start_channel_index
    if restore_pattern is None or restore_channel is None:
        for ch in channels:
            for pat in patterns:
                if snapshot.get(ch["index"], {}).get(pat["index"], []):
                    restore_pattern = pat["index"]
                    restore_channel = ch["index"]
                    break
            if restore_pattern is not None and restore_channel is not None:
                break
    if restore_pattern is not None and restore_channel is not None:
        c.call("patterns.select", index=restore_pattern)
        time.sleep(0.5)
        stage_and_run([{"action": "export_only"}], wait_sec=5.0)
        print(
            f"\nRestored starting combo: "
            f"ch[{restore_channel}] × pat[{restore_pattern}]"
        )

    print("\n✅ Done. `snapshot` contains all notes — safe to edit now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
