"""Connection + introspection tools for the bridge itself.

Two independent file-buses exist:
  * Main bridge — `Hardware/fLMCP Bridge/bus/` request+response files,
    serviced by `device_FLStudioMCP.py` running as a MIDI controller script.
  * Piano-roll bridge — `Piano roll scripts/fLMCP_request.json`
    + `fLMCP_state.json`, serviced by `ComposeWithLLM.pyscript`,
    triggered via Cmd+Opt+Y / Ctrl+Alt+Y.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..bridge_client import BridgeClient, get_client
from ..file_bridge import is_installed as pr_installed, read_state as pr_state, PR_DIR


def _midi_status() -> dict:
    try:
        info = get_client().ping()
        return {"online": True, **info}
    except Exception as e:
        return {
            "online": False,
            "error": str(e),
            "hint": (
                "Main bridge needs FL Studio running with a MIDI input row using "
                "Controller type = 'fLMCP Bridge'. On macOS that requires the IAC "
                "Driver enabled in Audio MIDI Setup so FL Studio sees a port to "
                "bind the controller script to."
            ),
        }


def _piano_roll_status() -> dict:
    return {
        "installed": pr_installed(),
        "pyscript_dir": str(PR_DIR),
        "last_state": pr_state(),
        "hint": (
            "Open any channel's piano roll, pick `ComposeWithLLM` from the "
            "piano-roll scripts dropdown once. No MIDI device required."
        ),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def fl_ping() -> dict:
        """Report health of BOTH bridges.

        Returns:
            {
              "midi_bridge":   {"online": bool, ...},
              "piano_roll":    {"installed": bool, ...},
              "available_capabilities": [...],
            }
        """
        midi = _midi_status()
        pr = _piano_roll_status()
        caps = []
        if midi.get("online"):
            caps.extend(["transport", "mixer", "channels", "patterns",
                         "plugins", "playlist", "arrangement", "automation",
                         "project", "ui"])
        if pr.get("installed"):
            caps.extend(["piano_roll", "generators(piano-roll emit)"])
        return {
            "midi_bridge": midi,
            "piano_roll": pr,
            "available_capabilities": sorted(set(caps)),
        }

    @mcp.tool()
    def fl_reconnect() -> dict:
        """Reset the bridge client (file-bus has no persistent connection,
        but this clears any client-side state and re-pings)."""
        get_client().close()
        return _midi_status()

    @mcp.tool()
    def fl_bridge_info() -> dict:
        """Detailed info about the main bridge (fails if it's offline)."""
        try:
            return get_client().call("meta.info")
        except Exception as e:
            return {"ok": False, "error": str(e),
                    "hint": "Main bridge offline. fl_ping shows piano-roll fallback status."}

    @mcp.tool()
    def fl_call_raw(action: str, params: dict | None = None) -> dict:
        """Escape hatch: invoke any action the main bridge accepts with arbitrary params."""
        return get_client().call(action, **(params or {}))
