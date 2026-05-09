"""
Shared transport contract for fLMCP <-> FL Studio bridge.

The bridge runs inside FL Studio's Python sub-interpreter, which on macOS blocks
threads, raw sockets, and subprocesses. So we use a plain file bus instead:

    bus_dir/req_{id}.json     written by MCP server, consumed by FL OnIdle
    bus_dir/resp_{id}.json    written by FL OnIdle, consumed by MCP server
    events.jsonl              one JSON record per line, written by FL, tailed by MCP

Atomic writes are achieved with a `.tmp` sibling + os.rename, which is atomic on
POSIX and Windows (within the same directory).

Request envelope:    {"id": int, "action": str, "params": {..}}
Response envelope:   {"id": int, "ok": bool, "result": <any>, "error": str|None}
Event record:        {"event": str, "data": <any>, "ts": float}
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def default_bridge_dir() -> Path:
    """Return the FL Studio Hardware/fLMCP Bridge directory for this platform."""
    if sys.platform == "win32":
        userprofile = os.environ.get("USERPROFILE", str(Path.home()))
        base = Path(userprofile) / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    return base / "Hardware" / "fLMCP Bridge"


def default_bus_dir() -> Path:
    return default_bridge_dir() / "bus"


def default_events_file() -> Path:
    return default_bridge_dir() / "events.jsonl"


@dataclass
class RPCError(RuntimeError):
    action: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.action}: {self.message}"
