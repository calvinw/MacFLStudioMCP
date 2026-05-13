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

        First checks if we're already on the target pattern + channel. If so, returns
        immediately without calling openEventEditor — avoids the window rebuild flicker.

        Waits briefly after retargeting so FL's piano roll finishes initialising
        before the next Cmd+Opt+Y keystroke (from piano_roll_add_notes) arrives.
        Script binding persists across channel/pattern switches so no separate
        warmup call is needed.
        """
        # Pre-flight: skip bridge call entirely if already on the right target
        try:
            current_pattern = get_client().call("patterns.current")
            current_channel = get_client().call("channels.selected")
            pr_visible = get_client().call("ui.focusedWindow", name="piano_roll")
        except Exception:
            current_pattern = None
            current_channel = None
            pr_visible = None

        if (
            current_pattern is not None
            and current_channel is not None
            and isinstance(current_pattern, dict)
            and isinstance(current_channel, dict)
        ):
            ch_match = current_channel.get("channel", {}).get("index") == channel
            pat_match = pattern is None or current_pattern.get("index") == pattern
            if ch_match and pat_match:
                return {"ok": True, "channel": channel, "retargeted": False,
                        "no_op": True, "note": "Already on target"}

        result = get_client().call("ui.openPianoRoll", channel=channel, pattern=pattern, force_retarget=True)
        if result.get("retargeted"):
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
