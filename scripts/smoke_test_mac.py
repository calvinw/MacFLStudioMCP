#!/usr/bin/env python3
"""Quick file-bus smoke test for the fLMCP bridge on macOS.

Run this from the venv after FL Studio is open with the fLMCP Bridge
controller enabled. It does a few cheap calls to verify the round-trip
through the file bus is working.

Usage:
    .venv/bin/python scripts/smoke_test_mac.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import BridgeClient
from fl_studio_mcp.protocol import default_bus_dir


def main() -> int:
    bus = default_bus_dir()
    print(f"bus dir: {bus}")
    print(f"bus exists: {bus.exists()}")
    if not bus.exists():
        print("\n⚠️  Bus dir doesn't exist. Make sure:")
        print("   • FL Studio is running")
        print("   • Options → MIDI Settings has a row with Controller type = 'fLMCP Bridge'")
        print("   • That row is Enabled (green)")
        print("   • The script output shows '[fLMCP] bus ready: ...'")
        return 1

    client = BridgeClient(timeout=5.0)

    print("\n--- meta.ping ---")
    t = time.time()
    info = client.ping()
    print(f"  round-trip: {(time.time() - t) * 1000:.1f} ms")
    print(f"  info: {info}")

    print("\n--- meta.info ---")
    info = client.call("meta.info")
    print(f"  {info}")

    print("\n--- transport.status ---")
    status = client.call("transport.status")
    print(f"  {status}")

    print("\n--- patterns.count ---")
    n = client.call("patterns.count")
    print(f"  {n}")

    print("\n--- patterns.list ---")
    plist = client.call("patterns.list")
    print(f"  {plist}")

    print("\n✅ all smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
