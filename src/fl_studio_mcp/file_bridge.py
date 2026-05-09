"""
File-based bridge for piano roll operations.

Works without loopMIDI / any MIDI device — the MCP server writes a request
file that the `ComposeWithLLM.pyscript` (piano roll pyscript) picks up when
it runs. The server triggers the pyscript by synthesising Ctrl+Alt+Y into the
FL Studio window. The pyscript then writes a state file we read back.

This complements `bridge_client.py` (the main file-bus channel for non-piano-roll
operations). Piano roll has its own file-bus because `flpianoroll` is sandboxed
to piano-roll scripts and can only be reached via the Cmd+Opt+Y / Ctrl+Alt+Y
keystroke trick.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("fl_studio_mcp.file_bridge")


def _piano_roll_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.path.expandvars("%USERPROFILE%")) / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    return base / "Piano roll scripts"


PR_DIR = _piano_roll_dir()
REQUEST_FILE = PR_DIR / "fLMCP_request.json"
STATE_FILE = PR_DIR / "fLMCP_state.json"
RESPONSE_FILE = PR_DIR / "fLMCP_response.json"


def is_installed() -> bool:
    """True if the ComposeWithLLM pyscript is present on disk."""
    return (PR_DIR / "ComposeWithLLM.pyscript").exists()


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_request(action: dict) -> None:
    existing = _read_json(REQUEST_FILE)
    if not isinstance(existing, list):
        existing = []
    existing.append(action)
    _write_json(REQUEST_FILE, existing)


def clear_request_queue() -> None:
    _write_json(REQUEST_FILE, [])


def clear_state() -> None:
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except Exception:
        pass


def wait_for_state(deadline_sec: float = 3.0) -> dict | None:
    end = time.monotonic() + deadline_sec
    while time.monotonic() < end:
        data = _read_json(STATE_FILE)
        if data is not None:
            return data
        time.sleep(0.01)
    return None


def stage_and_run(actions: list[dict], wait_sec: float = 3.0) -> dict:
    """Queue one or more piano-roll actions, fire the hotkey, wait for state."""
    from .keystroke import send_hotkey_mac, send_hotkey_windows

    if not is_installed():
        return {
            "ok": False,
            "error": (
                "ComposeWithLLM.pyscript is not installed. Run the installer "
                "or copy fl_bridge/piano_roll/ComposeWithLLM.pyscript into "
                f"{PR_DIR}"
            ),
        }

    clear_state()
    _write_json(REQUEST_FILE, actions)

    if sys.platform == "darwin":
        fired = send_hotkey_mac()
        manual_hint = "Could not auto-press Cmd+Opt+Y. Grant Accessibility permissions to your terminal/Claude in System Settings → Privacy & Security → Accessibility, then press Cmd+Opt+Y manually."
    else:
        fired = send_hotkey_windows()
        manual_hint = "Could not auto-press Ctrl+Alt+Y. Make sure FL Studio is in the foreground and ComposeWithLLM is the active piano-roll script, then press Ctrl+Alt+Y manually."

    state = wait_for_state(wait_sec) if fired else None

    return {
        "ok": bool(fired and state is not None),
        "hotkey_sent": fired,
        "staged_actions": len(actions),
        "state": state,
        "note": None if fired else manual_hint,
    }


def read_state() -> dict | None:
    """Return the most recent state file without running anything."""
    return _read_json(STATE_FILE)
