#!/usr/bin/env python3
"""Step 4 — exercise the piano-roll bridge (Cmd+Opt+Y trick).

This goes through the second, separate file-bus that piano-roll editing uses.
The MCP server stages JSON requests in `fLMCP_request.json`, fires the
Cmd+Opt+Y keystroke, and `ComposeWithLLM.pyscript` running inside FL Studio
applies the edits via the `flpianoroll` API and writes `fLMCP_state.json` back.

This script uses `stage_and_run()` directly, exactly like the real MCP tool
wrappers in `tools/piano_roll.py` do. We don't go through the main bridge for
the actual edits — only for FL API setup (selecting channel, opening piano roll).

Prerequisites:
  • ComposeWithLLM is selected as the active piano-roll script
    (open any piano roll → scripts dropdown → ComposeWithLLM)
  • Terminal has Accessibility permission so pynput can send the keystroke
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client
from fl_studio_mcp.file_bridge import is_installed as pr_installed, stage_and_run, read_state


def banner(label: str) -> None:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")


def report(result: dict) -> None:
    print(f"  ok={result.get('ok')}  hotkey_sent={result.get('hotkey_sent')}  "
          f"staged={result.get('staged_actions')}")
    if not result.get("hotkey_sent") and result.get("note"):
        print(f"  hint: {result['note']}")
    state = result.get("state") or read_state()
    if state:
        notes = state.get("notes", [])
        print(f"  piano roll has {len(notes)} note(s) "
              f"(midi: {[n.get('midi') for n in notes]})")


def main() -> int:
    c = get_client()

    banner("Pre-flight checks")
    print(f"ComposeWithLLM.pyscript installed: {pr_installed()}")
    if not pr_installed():
        print("\n❌ pyscript not installed. Re-run install_mac.sh.")
        return 1

    pattern_index = 2     # 'Melody 1' — won't clobber 'Chords'
    channel_index = 0     # Dark Resonance

    banner(f"Step 4a — focus pattern={pattern_index}, channel={channel_index}")
    # main bridge does FL API setup (selecting channel/pattern/piano-roll window)
    c.call("patterns.select", index=pattern_index)
    c.call("channels.select", index=channel_index)
    c.call("ui.openPianoRoll", channel=channel_index, pattern=pattern_index)
    print("FL should now show Melody 1's piano roll for Dark Resonance.")
    time.sleep(1.0)

    # ---- 4b — clear, then add a C major chord ------------------------------
    banner("Step 4b — clear + add C major chord at beat 1, 1 bar long")
    result = stage_and_run([
        {"action": "clear"},
        {"action": "add_chord",
         "time": 0.0,            # quarter notes
         "duration": 4.0,        # 1 bar = 4 quarters
         "notes": [{"midi": 60, "velocity": 0.85},
                   {"midi": 64, "velocity": 0.85},
                   {"midi": 67, "velocity": 0.85}]},
    ], wait_sec=3.0)
    report(result)

    # ---- 4c — read back ----------------------------------------------------
    banner("Step 4c — refresh state via export_only")
    result = stage_and_run([{"action": "export_only"}], wait_sec=3.0)
    report(result)

    # ---- 4d — transpose +12 semis ------------------------------------------
    banner("Step 4d — transpose all notes +12 semitones")
    result = stage_and_run([{"action": "transpose", "semitones": 12}], wait_sec=3.0)
    report(result)
    notes = (result.get("state") or read_state() or {}).get("notes", [])
    if notes:
        midis = sorted(n["midi"] for n in notes)
        print(f"  midi numbers after transpose: {midis} (should be [72, 76, 79])")

    # ---- 4e — clear --------------------------------------------------------
    banner("Step 4e — clear the piano roll")
    result = stage_and_run([{"action": "clear"}], wait_sec=3.0)
    report(result)

    banner("✅ Step 4 complete")
    print("If you saw the chord appear, jump up an octave, then disappear,")
    print("the piano-roll bridge + Cmd+Opt+Y trick are fully working on Mac.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
