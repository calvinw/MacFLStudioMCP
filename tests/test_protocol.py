"""BridgeClient round-trip test against a fake file-bus 'bridge'."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from fl_studio_mcp.bridge_client import BridgeClient


class FakeBridge:
    """Minimal worker thread that watches a bus dir and answers requests by writing
    response files back. Mimics what device_FLStudioMCP.OnIdle does inside FL.
    """

    def __init__(self, bus_dir: Path):
        self.bus_dir = bus_dir
        self.bus_dir.mkdir(parents=True, exist_ok=True)
        self.responses: dict[str, object] = {
            "meta.ping": {"ok": True, "bridge_version": "fake-0.1"},
            "transport.status": {"is_playing": False, "bpm": 140.0},
        }
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _atomic_write(self, path: Path, text: str) -> None:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, str(path))

    def _loop(self):
        while not self._stop.is_set():
            try:
                names = [
                    n for n in os.listdir(str(self.bus_dir))
                    if n.startswith("req_") and n.endswith(".json")
                ]
            except OSError:
                names = []
            for name in names:
                path = self.bus_dir / name
                try:
                    req = json.loads(path.read_text(encoding="utf-8"))
                    path.unlink()
                except Exception:
                    continue
                req_id = req.get("id")
                action = req.get("action", "")
                if action in self.responses:
                    resp = {"id": req_id, "ok": True, "result": self.responses[action]}
                elif action == "raise.me":
                    resp = {"id": req_id, "ok": False, "error": "boom"}
                else:
                    resp = {"id": req_id, "ok": True,
                            "result": {"echo": req.get("params", {})}}
                self._atomic_write(self.bus_dir / f"resp_{req_id}.json", json.dumps(resp))
            time.sleep(0.005)


@pytest.fixture
def bridge(tmp_path: Path):
    bus = tmp_path / "bus"
    b = FakeBridge(bus)
    b.start()
    yield b
    b.stop()


def test_ping_roundtrip(bridge):
    c = BridgeClient(bus_dir=bridge.bus_dir, timeout=2.0)
    r = c.ping()
    assert r["ok"] is True
    assert r["bridge_version"] == "fake-0.1"


def test_echo_params(bridge):
    c = BridgeClient(bus_dir=bridge.bus_dir, timeout=2.0)
    r = c.call("anything.else", foo=1, bar="baz")
    assert r == {"echo": {"foo": 1, "bar": "baz"}}


def test_error_propagated(bridge):
    c = BridgeClient(bus_dir=bridge.bus_dir, timeout=2.0)
    with pytest.raises(Exception) as exc:
        c.call("raise.me")
    assert "boom" in str(exc.value)


def test_timeout_when_bridge_offline(tmp_path):
    """No worker servicing the bus → call times out with a clear error."""
    c = BridgeClient(bus_dir=tmp_path / "empty_bus", timeout=0.3)
    with pytest.raises(Exception) as exc:
        c.ping()
    msg = str(exc.value).lower()
    assert "bridge did not respond" in msg or "timeout" in msg


def test_concurrent_calls_serialized(bridge):
    """Multiple threads can call concurrently — the lock serializes them but all succeed."""
    c = BridgeClient(bus_dir=bridge.bus_dir, timeout=3.0)
    results: list[object] = []
    errors: list[Exception] = []

    def worker(i: int):
        try:
            results.append(c.call("anything.else", n=i))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 5
    assert {tuple(r["echo"].items()) for r in results} == {(("n", i),) for i in range(5)}
