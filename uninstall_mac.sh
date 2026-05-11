#!/bin/bash
set -e

FL_HARDWARE="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/fLMCP Bridge"
FL_PIANO_ROLL="$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts"

echo "Uninstalling fLMCP bridge files..."

# Hardware controller + bus directory
if [ -d "$FL_HARDWARE" ]; then
  rm -f "$FL_HARDWARE/device_FLStudioMCP.py"
  rm -rf "$FL_HARDWARE/bus"
  rmdir "$FL_HARDWARE" 2>/dev/null && echo "  ✓ Removed Hardware/fLMCP Bridge/" || \
    echo "  ~ Hardware/fLMCP Bridge/ not empty (other files present), left in place"
else
  echo "  ~ Hardware/fLMCP Bridge/ not found, skipping"
fi

# Piano roll scripts
for f in ComposeWithLLM.pyscript fLMCP_bridge.pyscript fLMCP_request.json fLMCP_state.json; do
  if [ -f "$FL_PIANO_ROLL/$f" ]; then
    rm -f "$FL_PIANO_ROLL/$f"
    echo "  ✓ Removed Piano roll scripts/$f"
  fi
done

# Deregister from Claude Code if CLI is available
echo ""
if command -v claude &>/dev/null; then
  if claude mcp remove fl-studio-mcp 2>/dev/null; then
    echo "  ✓ fl-studio-mcp removed from Claude Code"
  else
    echo "  ~ fl-studio-mcp was not registered with Claude Code"
  fi
else
  echo "  Claude Code CLI not found — nothing to deregister"
fi

echo ""
echo "Done. The .venv and project folder were not touched."
echo "To remove those too:  rm -rf .venv"
