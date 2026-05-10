#!/usr/bin/env python3
"""Test FL Studio macOS audit hook restrictions by calling the diagnostic handler.

This script requires FL Studio to be running with the fLMCP Bridge MIDI device enabled.
It calls the meta.testRestrictions handler inside FL's Python sub-interpreter and
reports which operations are blocked by the audit hook.

Usage:
    python scripts/test_mac_audit_hook_restrictions.py

Expected output on macOS (with audit hook):
    sockets:           ✗ BLOCKED
    threads:           ✗ BLOCKED
    subprocess:        ✗ BLOCKED
    tempfile_mkdir:    ✗ BLOCKED
    os_mkdir:          ✗ BLOCKED
    os_unlink:         ✗ BLOCKED
    os_rename:         ✗ BLOCKED
    file_io:           ✓ OK (reading/writing existing files is allowed)
"""

from __future__ import annotations

import sys
from pathlib import Path

from fl_studio_mcp.bridge_client import BridgeClient


def main() -> int:
    """Connect to FL Studio and run the audit hook restriction test."""
    # Locate the bus directory
    base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    bus_dir = base / "Hardware" / "fLMCP Bridge" / "bus"

    if not bus_dir.exists():
        print(f"❌ Bus directory not found: {bus_dir}")
        print("   Make sure FL Studio is running with fLMCP Bridge MIDI device enabled.")
        return 1

    try:
        client = BridgeClient(bus_dir=bus_dir, timeout=2.0)
        results = client.call("meta.testRestrictions")
    except Exception as e:
        print(f"❌ Failed to call meta.testRestrictions: {e}")
        print("   Is FL Studio running with fLMCP Bridge enabled?")
        return 1

    # Pretty-print results
    print("\n" + "=" * 60)
    print("FL Studio macOS Audit Hook Restriction Test Results")
    print("=" * 60 + "\n")

    # Print Python info first
    if "python_version" in results:
        print(f"Python Version:     {results['python_version']}")
        if "python_implementation" in results:
            print(f"Implementation:     {results['python_implementation']}")
        print()

    # Sort for consistent output, excluding version info
    test_ops = sorted(k for k in results.keys()
                     if not k.startswith("python_"))

    for op in test_ops:
        result = results[op]
        if result == "OK":
            symbol = "✓"
            status = "OK"
        else:
            symbol = "✗"
            status = result.replace("BLOCKED: ", "")

        print(f"{op:20} {symbol} {status}")

    print("\n" + "=" * 60)

    # Summary
    blocked_count = sum(1 for r in results.values() if r != "OK")
    total_count = len(results)

    print(f"\nSummary: {blocked_count}/{total_count} operations blocked")

    if blocked_count > 5:
        print("\n✓ Audit hook is actively restricting operations (as expected on macOS).")
        return 0
    else:
        print("\n⚠ Fewer restrictions than expected. Are you running on macOS?")
        return 1


if __name__ == "__main__":
    sys.exit(main())
