"""UI helpers: focused window, show hints, open editors."""

from __future__ import annotations

import time
from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


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

        Waits briefly after retargeting so FL's piano roll finishes initialising
        before the next Cmd+Opt+Y keystroke (from piano_roll_add_notes) arrives.
        Script binding persists across channel/pattern switches so no separate
        warmup call is needed.
        """
        result = get_client().call("ui.openPianoRoll", channel=channel, pattern=pattern)
        if result.get("retargeted"):
            # Brief settle: give FL's piano roll time to finish initialising so
            # the next Cmd+Opt+Y keystroke (from piano_roll_add_notes) isn't
            # dropped. Script binding persists across channel/pattern switches so
            # we don't need a separate export_only warmup call any more.
            time.sleep(0.2)
        return result

    @mcp.tool()
    def ui_selected_channel() -> dict:
        """Return selected channel index + name."""
        return get_client().call("ui.selectedChannel")

    @mcp.tool()
    def ui_scroll_to_channel(channel: int) -> dict:
        """Scroll the channel rack to show a channel."""
        return get_client().call("ui.scrollToChannel", channel=channel)
