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


def banner(msg: str) -> None:
    print(f"\n{'─' * 60}\n{msg}\n{'─' * 60}")


def read_notes_for(c, channel: int, pattern: int, settle: float = 0.25) -> list[dict]:
    """Open channel/pattern in the piano roll and export its notes.

    Returns the list of note dicts from ComposeWithLLM's state export.
    Each note has: midi, time_bars, duration_bars, velocity, pan, …
    """
    result = c.call("ui.openPianoRoll", channel=channel, pattern=pattern)
    retargeted = result.get("retargeted", False)
    if retargeted:
        time.sleep(settle)   # let FL finish initialising the new piano roll

    state_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
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

    for ch in channels:
        ch_idx = ch["index"]
        snapshot[ch_idx] = {}
        for pat in patterns:
            pat_idx = pat["index"]
            label = f"ch[{ch_idx}] {ch['name']!r}  ×  pat[{pat_idx}] {pat['name']!r}"
            print(f"\n→ {label}")

            notes = read_notes_for(c, channel=ch_idx, pattern=pat_idx, settle=0.5)
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
            notes = snapshot[ch["index"]][pat["index"]]
            if notes:
                print(f"  ch[{ch['index']}] {ch['name']!r}  ×  pat[{pat['index']}] {pat['name']!r}")
                for n in notes:
                    print(f"    midi={n['midi']:3d}  t={n['time_bars']:.3f}b  "
                          f"dur={n['duration_bars']:.3f}b  vel={n['velocity']:.2f}")

    # Some FL UI views do not repaint reliably after repeated retargeting. Do a
    # final explicit select/open/export refresh for each pattern/channel, then
    # restore the pattern/channel that was selected before the test started.
    banner("Final UI refresh pass")
    for pat in patterns:
        for ch in channels:
            label = f"pat[{pat['index']}] {pat['name']!r} × ch[{ch['index']}] {ch['name']!r}"
            ok = refresh_combo(c, channel=ch["index"], pattern=pat["index"])
            print(f"  {'✓' if ok else '⚠'} refreshed {label}")

    restore_pattern = start_pattern.get("index")
    restore_channel = (start_channel.get("channel") or {}).get("index")
    if restore_pattern is None or restore_channel is None:
        for ch in channels:
            for pat in patterns:
                if snapshot[ch["index"]][pat["index"]]:
                    restore_pattern = pat["index"]
                    restore_channel = ch["index"]
                    break
            if restore_pattern is not None and restore_channel is not None:
                break
    if restore_pattern is not None and restore_channel is not None:
        refresh_combo(c, channel=restore_channel, pattern=restore_pattern)
        print(
            f"\nRestored starting combo: "
            f"ch[{restore_channel}] × pat[{restore_pattern}]"
        )

    print("\n✅ Done. `snapshot` contains all notes — safe to edit now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
