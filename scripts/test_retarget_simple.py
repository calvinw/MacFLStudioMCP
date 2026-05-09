#!/usr/bin/env python3
"""Simple test - just call openPianoRoll twice with explicit patterns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client

c = get_client()

print("Test 1: Open piano roll for pattern=1, channel=0")
result1 = c.call("ui.openPianoRoll", channel=0, pattern=1)
print(f"  Result: {result1}")
print()

print("Test 2: Open piano roll for pattern=2, channel=0")
result2 = c.call("ui.openPianoRoll", channel=0, pattern=2)
print(f"  Result: {result2}")
print()

print("Test 3: Open piano roll for pattern=1, channel=0 (again)")
result3 = c.call("ui.openPianoRoll", channel=0, pattern=1)
print(f"  Result: {result3}")
print()

print("Test 4: Open piano roll for channel=0 (no pattern specified)")
result4 = c.call("ui.openPianoRoll", channel=0)
print(f"  Result: {result4}")
