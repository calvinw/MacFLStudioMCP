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
        """Switch the piano roll to show a given channel/pattern without closing the window.

        In one-channel-per-pattern mode, selecting the pattern causes FL to
        auto-select its channel and update the piano roll viewport — no
        openEventEditor call needed (which would cause the window to disappear
        and reappear). openEventEditor is only called as a last resort when the
        channel still doesn't match after the pattern switch.
        """
        c = get_client()

        current_pattern = c.call("patterns.current")
        current_channel = c.call("channels.selected")
        ch_index = (current_channel.get("channel") or {}).get("index")
        pat_index = current_pattern.get("index") if isinstance(current_pattern, dict) else None

        pat_match = pattern is None or pat_index == pattern
        ch_match = ch_index == channel

        if pat_match and ch_match:
            return {"ok": True, "channel": channel, "retargeted": False, "no_op": True}

        # In one-channel-per-pattern mode, selecting the pattern causes FL to
        # update the piano roll viewport without rebuilding the window.
        if pattern is not None and not pat_match:
            c.call("patterns.select", index=pattern)
            time.sleep(0.15)

        return {"ok": True, "channel": channel, "retargeted": True, "via": "pattern_select"}

    @mcp.tool()
    def ui_selected_channel() -> dict:
        """Return selected channel index + name."""
        return get_client().call("ui.selectedChannel")

    @mcp.tool()
    def ui_scroll_to_channel(channel: int) -> dict:
        """Scroll the channel rack to show a channel."""
        return get_client().call("ui.scrollToChannel", channel=channel)
