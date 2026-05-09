"""
File-bus client that talks to the FL Studio bridge script.

The MCP server writes a JSON request file (`bus_dir/req_{id}.json`), then polls
for the matching `resp_{id}.json`. Writes are atomic (`.tmp` + os.rename) so the
bridge never sees a half-written request. Responses are deleted after read.

This replaces the older TCP transport — FL Studio's Mac sub-interpreter blocks
sockets/threads/subprocesses, so files are the only viable channel.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from .protocol import RPCError, default_bus_dir

# Re-export RPCError so tools that did `from ..bridge_client import RPCError` still work.
__all__ = ["BridgeClient", "RPCError", "get_client"]

log = logging.getLogger("fl_studio_mcp.bridge")

POLL_INTERVAL_SEC = 0.02   # 20 ms — file polling cadence
DEFAULT_TIMEOUT = 10.0


class BridgeClient:
    def __init__(self, bus_dir: Path | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.bus_dir = Path(bus_dir) if bus_dir else default_bus_dir()
        self.timeout = timeout
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    # ---- connection lifecycle -------------------------------------------------
    def is_connected(self) -> bool:
        """The bridge is 'connected' if its bus dir exists. The bridge script
        creates it in OnInit, so its presence implies FL has loaded the script."""
        return self.bus_dir.exists()

    def close(self) -> None:
        # nothing to do — no persistent resources
        pass

    # ---- request/response -----------------------------------------------------
    def call(self, action: str, **params: Any) -> Any:
        req_id = next(self._ids)
        envelope = {"id": req_id, "action": action, "params": params}
        req_path = self.bus_dir / f"req_{req_id}.json"
        resp_path = self.bus_dir / f"resp_{req_id}.json"
        tmp_path = self.bus_dir / f"req_{req_id}.json.tmp"

        with self._lock:
            try:
                self.bus_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise RPCError(action=action, message=f"bus dir not writable: {e}") from e

            # atomic write of request
            try:
                tmp_path.write_text(
                    json.dumps(envelope, separators=(",", ":"), ensure_ascii=False),
                    encoding="utf-8",
                )
                os.replace(str(tmp_path), str(req_path))
            except OSError as e:
                raise RPCError(action=action, message=f"failed to stage request: {e}") from e

            # poll for response. FL writes resp_*.json non-atomically (audit hook
            # blocks os.rename inside FL), so we may briefly read an empty or
            # partial file — JSONDecodeError just means "writer not done" → retry.
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if resp_path.exists():
                    try:
                        text = resp_path.read_text(encoding="utf-8")
                    except OSError:
                        time.sleep(POLL_INTERVAL_SEC / 2)
                        continue
                    if not text.strip():
                        # writer truncated the file but hasn't written content yet
                        time.sleep(POLL_INTERVAL_SEC / 2)
                        continue
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        # mid-write; retry
                        time.sleep(POLL_INTERVAL_SEC / 2)
                        continue

                    # success — clean up both files (FL can't unlink, so we do it)
                    for p in (resp_path, req_path):
                        try:
                            if p.exists():
                                p.unlink()
                        except OSError:
                            pass

                    if data.get("ok"):
                        return data.get("result")
                    raise RPCError(
                        action=action,
                        message=str(data.get("error") or "unknown error"),
                    )
                time.sleep(POLL_INTERVAL_SEC)

            # timeout — clean up the request file so it doesn't stick around
            try:
                if req_path.exists():
                    req_path.unlink()
            except OSError:
                pass
            raise RPCError(
                action=action,
                message=f"bridge did not respond within {self.timeout}s "
                        f"(is FL Studio running with the fLMCP Bridge controller enabled?)",
            )

    # ---- convenience ----------------------------------------------------------
    def ping(self) -> dict:
        return self.call("meta.ping")


_singleton: BridgeClient | None = None
_singleton_lock = threading.Lock()


def get_client() -> BridgeClient:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = BridgeClient()
        return _singleton
