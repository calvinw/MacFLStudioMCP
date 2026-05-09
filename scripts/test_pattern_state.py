#!/usr/bin/env python3
"""Quick test to see pattern state before/after switching."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fl_studio_mcp.bridge_client import get_client

c = get_client()

# Get current state
current = c.call("patterns.current")
print(f"Current pattern: {current}")

# List all
patterns = c.call("patterns.list")["patterns"]
print(f"\nAll patterns: {patterns}")

# Try switching to pattern 2
print("\n--- Switching to pattern 2 ---")
c.call("patterns.select", index=2)

# Check state
current = c.call("patterns.current")
print(f"After switch: {current}")

# Open piano roll
print("\n--- Opening piano roll for channel=0, pattern=2 ---")
result = c.call("ui.openPianoRoll", channel=0, pattern=2)
print(f"Result: {result}")
