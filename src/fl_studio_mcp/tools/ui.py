"""UI helpers: focused window, show hints, open editors."""

from __future__ import annotations

import time
from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client
from ..file_bridge import is_installed, stage_and_run


WindowName = Literal["mixer", "channel_rack", "playlist", "piano_roll", "browser", "plugin"]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def ui_focused_window() -> dict:
        """Return info about the currently focused FL Studio window."""
        return get_client().call("ui.focusedWindow")

    @mcp.tool()
    def ui_show_window(name: WindowName, focus: bool = True) -> dict:
        """Open / focus a main window by name."""
        return get_client().call("ui.showWindow", name=name, focus=focus)

    @mcp.tool()
    def ui_hide_window(name: WindowName) -> dict:
        """Close a main window."""
        return get_client().call("ui.hideWindow", name=name)

    @mcp.tool()
    def ui_hint(message: str) -> dict:
        """Display a transient hint message in FL Studio's status bar."""
        return get_client().call("ui.hint", message=message)

    @mcp.tool()
    def ui_open_piano_roll_for_channel(channel: int, pattern: int | None = None) -> dict:
        """Open the piano roll for a given channel (optionally switch pattern first).

        After retargeting, waits for the piano roll to settle then fires a
        no-op script run to re-bind ComposeWithLLM as the active script and
        redraw the viewport. This ensures subsequent piano_roll_add_notes calls
        work correctly without requiring a manual ComposeWithLLM click.
        """
        result = get_client().call("ui.openPianoRoll", channel=channel, pattern=pattern)
        if result.get("retargeted") and is_installed():
            # Give the piano roll time to finish initialising before triggering
            # the script — without this delay the keystroke lands too early and
            # FL Studio ignores it, leaving ComposeWithLLM unbound.
            time.sleep(1.0)
            refresh = stage_and_run([{"action": "export_only"}])
            result["viewport_refresh"] = {
                "ok": refresh.get("ok"),
                "hotkey_sent": refresh.get("hotkey_sent"),
            }
        return result

    @mcp.tool()
    def ui_selected_channel() -> dict:
        """Return selected channel index + name."""
        return get_client().call("ui.selectedChannel")

    @mcp.tool()
    def ui_scroll_to_channel(channel: int) -> dict:
        """Scroll the channel rack to show a channel."""
        return get_client().call("ui.scrollToChannel", channel=channel)
