"""Piano roll tools — file-based bridge (NO MIDI required).

Pipeline:
  1. MCP tool stages one or more actions into `fLMCP_request.json` in FL's
     Piano roll scripts folder.
  2. MCP tool sends Ctrl+Alt+Y to the FL Studio window (Win32 SendInput).
  3. FL fires `ComposeWithLLM.pyscript` which drains the request queue via
     `flpianoroll` and writes `fLMCP_state.json`.
  4. MCP tool reads state file and returns it.

This works in FL Studio's piano-roll sub-interpreter context (where daemon
threads are prohibited) because the pyscript finishes quickly and doesn't
try to spawn any threads.

Requirements on user side:
  * `ComposeWithLLM.pyscript` must be installed (done by install_windows.ps1).
  * It must be the currently-selected piano-roll script (piano roll window →
    scripts dropdown → pick `ComposeWithLLM`).
  * The target pattern's piano roll must be open & focused when we fire the
    hotkey. Our keystroke helper brings FL Studio to the foreground, but the
    user should have the correct channel's piano roll open.
"""

from __future__ import annotations

import time
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from ..bridge_client import get_client
from ..file_bridge import stage_and_run

class PianoRollNote(BaseModel):
    midi: int
    time_bars: float | None = None
    duration_bars: float | None = None
    time: float | None = None
    duration: float | None = None
    velocity: float = 0.8
    pan: float | None = None


def _bars_to_quarters(bars: float) -> float:
    return bars * 4.0


def _ensure_piano_roll_on_target(c, channel: int, pattern: int | None = None) -> bool:
    """Switch the piano roll viewport to the target channel+pattern.

    In one-channel-per-pattern mode, patterns.select causes FL to auto-select
    the pattern's channel in the channel rack. We check channels.selected AFTER
    the pattern switch — if it already matches the target channel, the piano roll
    viewport is already correct and we can skip openEventEditor (which causes the
    window flash). openEventEditor is only called when the channel still doesn't
    match after the pattern switch.
    """
    current_pattern = c.call("patterns.current")
    if pattern is not None and current_pattern.get("index") != pattern:
        c.call("patterns.select", index=pattern)
        time.sleep(0.2)

    sel = c.call("channels.selected")
    current_channel = (sel.get("channel") or {}).get("index")
    if current_channel != channel:
        result = c.call("ui.openPianoRoll", channel=channel, force_retarget=True)
        if result.get("retargeted"):
            time.sleep(0.25)

    return True


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def piano_roll_status() -> dict:
        """Report whether the file-based piano-roll bridge is installed/reachable.

        Use this to verify the pyscript is in place before issuing edits.
        """
        from ..file_bridge import PR_DIR, STATE_FILE, is_installed, read_state
        return {
            "installed": is_installed(),
            "pyscript_dir": str(PR_DIR),
            "last_state_file": str(STATE_FILE),
            "last_state": read_state(),
        }

    @mcp.tool()
    def piano_roll_add_notes(notes: list[PianoRollNote],
                             clear_first: bool = False) -> dict:
        """Add notes to the currently-open piano roll (works WITHOUT MIDI).

        `notes`: list of {midi: int, time_bars: float, duration_bars: float,
                          velocity: 0..1, pan?: -1..1}.

        Before calling, make sure:
          1. In FL Studio, open the target channel's piano roll (double-click
             the channel in the Channel Rack).
          2. Pick `ComposeWithLLM` from the piano-roll scripts dropdown.
        """
        actions: list[dict] = []
        if clear_first:
            actions.append({"action": "clear"})
        pyscript_notes = []
        for n in notes:
            time_bars = n.time_bars if n.time_bars is not None else (n.time if n.time is not None else 0.0)
            duration_bars = n.duration_bars if n.duration_bars is not None else (n.duration if n.duration is not None else 1.0)
            pyscript_notes.append({
                "midi": int(n.midi),
                "time": _bars_to_quarters(float(time_bars)),
                "duration": _bars_to_quarters(float(duration_bars)),
                "velocity": float(n.velocity),
                **({"pan": float(n.pan)} if n.pan is not None else {}),
            })
        actions.append({"action": "add_notes", "notes": pyscript_notes})
        return stage_and_run(actions)

    @mcp.tool()
    def piano_roll_add_chord(midi_notes: list[int],
                             time_bars: float = 0.0,
                             duration_bars: float = 1.0,
                             velocity: float = 0.8) -> dict:
        """Add a chord at a given bar position."""
        return stage_and_run([{
            "action": "add_chord",
            "time": _bars_to_quarters(time_bars),
            "duration": _bars_to_quarters(duration_bars),
            "notes": [{"midi": int(m), "velocity": velocity} for m in midi_notes],
        }])

    @mcp.tool()
    def piano_roll_add_arpeggio(midi_notes: list[int],
                                time_bars: float = 0.0,
                                step_bars: float = 0.25,
                                note_duration_bars: float = 0.25,
                                velocity: float = 0.8,
                                direction: Literal["up", "down", "updown", "random"] = "up",
                                repeats: int = 1) -> dict:
        """Arpeggiate a chord into sequential notes."""
        import random
        seq = list(midi_notes)
        if direction == "down":
            seq.reverse()
        elif direction == "updown":
            seq = seq + seq[-2:0:-1]
        elif direction == "random":
            random.shuffle(seq)

        pyscript_notes = []
        total = len(seq) * max(1, int(repeats))
        for i in range(total):
            pyscript_notes.append({
                "midi": int(seq[i % len(seq)]),
                "time": _bars_to_quarters(time_bars + i * step_bars),
                "duration": _bars_to_quarters(note_duration_bars),
                "velocity": velocity,
            })
        return stage_and_run([{"action": "add_notes", "notes": pyscript_notes}])

    @mcp.tool()
    def piano_roll_delete_notes(notes: list[dict]) -> dict:
        """Delete notes by {midi, time_bars} match."""
        converted = [{"midi": int(n["midi"]),
                      "time": _bars_to_quarters(float(n["time_bars"]))}
                     for n in notes]
        return stage_and_run([{"action": "delete_notes", "notes": converted}])

    @mcp.tool()
    def piano_roll_clear() -> dict:
        """Remove every note in the currently-open piano roll."""
        return stage_and_run([{"action": "clear"}])

    @mcp.tool()
    def piano_roll_read() -> dict:
        """Read back the current piano-roll state (returns all notes)."""
        return stage_and_run([{"action": "export_only"}], wait_sec=5.0)

    @mcp.tool()
    def piano_roll_read_patterns_autolocate(patterns_to_read: list[int] | None = None,
                                           restore_start: bool = True,
                                           navigate_after_pattern: int | None = None,
                                           navigate_after_channel: int | None = None) -> dict:
        """Read notes across patterns using FL's auto-located piano-roll channel.

        This avoids explicit channel retargeting/openEventEditor. It changes only
        the selected pattern, triggers ComposeWithLLM, and records the selected
        channel FL reports after each pattern switch.

        After the sweep, if navigate_after_pattern is provided, FL is left on that
        pattern (and optionally channel) so the UI is already showing the edit target
        while the LLM plans its changes. Use this whenever you know ahead of time
        which pattern will be edited first.
        """
        c = get_client()
        start_pattern = c.call("patterns.current")
        start_channel = c.call("channels.selected")
        all_patterns = c.call("patterns.list").get("patterns", [])

        wanted = set(patterns_to_read or [p["index"] for p in all_patterns])
        patterns = [p for p in all_patterns if p["index"] in wanted]
        start_idx = start_pattern.get("index")
        if start_idx is not None:
            for i, pat in enumerate(patterns):
                if pat["index"] == start_idx:
                    patterns = patterns[i:] + patterns[:i]
                    break

        results = []
        for i, pat in enumerate(patterns):
            if i > 0 or pat["index"] != start_idx:
                c.call("patterns.select", index=pat["index"])
                time.sleep(0.2)

            read_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
            selected_channel = c.call("channels.selected").get("channel")
            state = read_result.get("state") or {}
            results.append({
                "pattern": pat,
                "channel": selected_channel,
                "ok": bool(read_result.get("ok")),
                "hotkey_sent": read_result.get("hotkey_sent"),
                "note_count": len(state.get("notes") or []),
                "notes": state.get("notes") or [],
            })

        restored = None
        if restore_start and start_idx is not None:
            c.call("patterns.select", index=start_idx)
            time.sleep(0.2)
            restore_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
            restored = {
                "pattern": start_pattern,
                "channel": start_channel.get("channel"),
                "ok": bool(restore_result.get("ok")),
            }
        elif navigate_after_pattern is not None:
            # Navigate to the first edit target so FL shows it while LLM plans
            c.call("patterns.select", index=navigate_after_pattern)
            if navigate_after_channel is not None:
                c.call("channels.select", index=navigate_after_channel)
            time.sleep(0.2)

        return {
            "start_pattern": start_pattern,
            "start_channel": start_channel.get("channel"),
            "results": results,
            "restored": restored,
            "total_notes": sum(r["note_count"] for r in results),
        }

    @mcp.tool()
    def piano_roll_write_pattern(
        channel: int,
        pattern: int,
        notes: list[PianoRollNote],
        clear_first: bool = True,
        restore_start: bool = False,
    ) -> dict:
        """Write notes to a specific channel × pattern using autolocate-style switching.

        Mirrors piano_roll_read_patterns_autolocate: switches to the target
        pattern via patterns.select (no openEventEditor, no visual flicker),
        selects the channel, then stages a clear+add_notes action sequence and
        fires Cmd+Opt+Y.

        Args:
            channel: Channel rack index (0-based).
            pattern: Pattern index (1-based, as returned by patterns.list).
            notes: List of notes with midi, time_bars, duration_bars, velocity.
            clear_first: Clear the pattern before writing (default True).
            restore_start: Restore the original pattern/channel when done (default False — stays on last edited).

        Returns:
            {ok, note_count, hotkey_sent, restored}
        """
        c = get_client()

        # Remember starting position so we can restore it
        start_pattern = c.call("patterns.current")
        start_channel = c.call("channels.selected")
        start_pat_idx = start_pattern.get("index")

        # Switch to target pattern + channel, force-retarget only if needed
        _ensure_piano_roll_on_target(c, channel, pattern)

        # Convert bar-based notes to quarter-note times expected by pyscript
        pyscript_notes = []
        for n in notes:
            time_bars = n.time_bars if n.time_bars is not None else (
                n.time if n.time is not None else 0.0)
            duration_bars = n.duration_bars if n.duration_bars is not None else (
                n.duration if n.duration is not None else 1.0)
            pyscript_notes.append({
                "midi": int(n.midi),
                "time": _bars_to_quarters(float(time_bars)),
                "duration": _bars_to_quarters(float(duration_bars)),
                "velocity": float(n.velocity),
                **({"pan": float(n.pan)} if n.pan is not None else {}),
            })

        actions: list[dict] = []
        if clear_first:
            actions.append({"action": "clear"})
        actions.append({"action": "add_notes", "notes": pyscript_notes})

        write_result = stage_and_run(actions, wait_sec=5.0)

        # Restore starting pattern/channel
        restored = None
        if restore_start and start_pat_idx is not None:
            c.call("patterns.select", index=start_pat_idx)
            start_ch = (start_channel.get("channel") or {}).get("index")
            if start_ch is not None:
                c.call("channels.select", index=start_ch)
            time.sleep(0.2)
            restore_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
            restored = {
                "pattern": start_pattern,
                "channel": start_channel.get("channel"),
                "ok": bool(restore_result.get("ok")),
            }

        return {
            "ok": write_result.get("ok", False),
            "note_count": len(pyscript_notes),
            "hotkey_sent": write_result.get("hotkey_sent"),
            "restored": restored,
        }

    @mcp.tool()
    def piano_roll_write_patterns(
        writes: list[dict],
        clear_first: bool = True,
        restore_start: bool = False,
    ) -> dict:
        """Write notes to multiple channel × pattern pairs sequentially, restoring only at the end.

        Mirrors piano_roll_read_patterns_autolocate: iterates through all writes
        in order without jumping back between each one, then restores to the
        original pattern/channel once at the very end.

        Args:
            writes: List of {channel: int, pattern: int, notes: [{midi, time_bars, duration_bars, velocity}]}.
            clear_first: Clear each pattern before writing (default True).
            restore_start: Restore the original pattern/channel after all writes (default False — stays on last edited).

        Returns:
            {results: [{channel, pattern, ok, note_count, hotkey_sent}], restored}
        """
        c = get_client()

        start_pattern = c.call("patterns.current")
        start_channel = c.call("channels.selected")
        start_pat_idx = start_pattern.get("index")
        start_ch_idx = (start_channel.get("channel") or {}).get("index")

        results = []
        for entry in writes:
            channel = int(entry["channel"])
            pattern = int(entry["pattern"])
            raw_notes = entry.get("notes", [])

            # Force the piano roll viewport to the target channel+pattern
            _ensure_piano_roll_on_target(c, channel, pattern)

            pyscript_notes = []
            for n in raw_notes:
                time_bars = float(n.get("time_bars") or n.get("time") or 0.0)
                duration_bars = float(n.get("duration_bars") or n.get("duration") or 1.0)
                pyscript_notes.append({
                    "midi": int(n["midi"]),
                    "time": _bars_to_quarters(time_bars),
                    "duration": _bars_to_quarters(duration_bars),
                    "velocity": float(n.get("velocity", 0.8)),
                    **({"pan": float(n["pan"])} if "pan" in n else {}),
                })

            actions: list[dict] = []
            if clear_first:
                actions.append({"action": "clear"})
            actions.append({"action": "add_notes", "notes": pyscript_notes})

            write_result = stage_and_run(actions, wait_sec=5.0)
            results.append({
                "channel": channel,
                "pattern": pattern,
                "ok": write_result.get("ok", False),
                "note_count": len(pyscript_notes),
                "hotkey_sent": write_result.get("hotkey_sent"),
            })

        restored = None
        if restore_start and start_pat_idx is not None:
            c.call("patterns.select", index=start_pat_idx)
            if start_ch_idx is not None:
                c.call("channels.select", index=start_ch_idx)
            time.sleep(0.2)
            restore_result = stage_and_run([{"action": "export_only"}], wait_sec=5.0)
            restored = {
                "pattern": start_pattern,
                "channel": start_channel.get("channel"),
                "ok": bool(restore_result.get("ok")),
            }

        return {
            "results": results,
            "restored": restored,
            "total_notes": sum(r["note_count"] for r in results),
        }

    @mcp.tool()
    def piano_roll_quantize(grid_bars: float = 0.25,
                            strength: float = 1.0) -> dict:
        """Snap existing notes to a grid."""
        return stage_and_run([{
            "action": "quantize",
            "grid": _bars_to_quarters(grid_bars),
            "strength": strength,
        }])

    @mcp.tool()
    def piano_roll_transpose(semitones: int) -> dict:
        """Shift every note by N semitones."""
        return stage_and_run([{"action": "transpose", "semitones": int(semitones)}])

    @mcp.tool()
    def piano_roll_humanize(timing_jitter_bars: float = 0.02,
                            velocity_jitter: float = 0.1) -> dict:
        """Add subtle timing+velocity randomisation."""
        return stage_and_run([{
            "action": "humanize",
            "timing_jitter": _bars_to_quarters(timing_jitter_bars),
            "velocity_jitter": velocity_jitter,
        }])

    @mcp.tool()
    def piano_roll_duplicate(source_time_bars: float,
                             length_bars: float,
                             dest_time_bars: float) -> dict:
        """Copy a time-range of notes to another location."""
        return stage_and_run([{
            "action": "duplicate",
            "source_time": _bars_to_quarters(source_time_bars),
            "length": _bars_to_quarters(length_bars),
            "dest_time": _bars_to_quarters(dest_time_bars),
        }])
