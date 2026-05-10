#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FL_HARDWARE="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/fLMCP Bridge"
FL_PIANO_ROLL="$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts"

echo "Installing fLMCP bridge files..."

mkdir -p "$FL_HARDWARE"
mkdir -p "$FL_HARDWARE/bus"
cp "$SCRIPT_DIR/fl_bridge/device_FLStudioMCP.py" "$FL_HARDWARE/"
echo "  ✓ device_FLStudioMCP.py → Hardware/fLMCP Bridge/"
echo "  ✓ bus/ directory created (FL's sub-interpreter can't mkdir)"

mkdir -p "$FL_PIANO_ROLL"
cp "$SCRIPT_DIR/fl_bridge/piano_roll/ComposeWithLLM.pyscript" "$FL_PIANO_ROLL/"
cp "$SCRIPT_DIR/fl_bridge/piano_roll/fLMCP_bridge.pyscript" "$FL_PIANO_ROLL/"
echo "  ✓ ComposeWithLLM.pyscript → Piano roll scripts/"
echo "  ✓ fLMCP_bridge.pyscript → Piano roll scripts/"

# FL's audit hook blocks new-file creation; pre-create empty stub files
# so the bridge only ever needs to *write* to existing files.
[ -f "$FL_PIANO_ROLL/fLMCP_request.json" ] || echo "[]" > "$FL_PIANO_ROLL/fLMCP_request.json"
[ -f "$FL_PIANO_ROLL/fLMCP_state.json" ] || echo "{}" > "$FL_PIANO_ROLL/fLMCP_state.json"
echo "  ✓ fLMCP_request.json + fLMCP_state.json initialized"

echo ""
echo "Setting up Python venv..."
[ -d "$SCRIPT_DIR/.venv" ] || python3 -m venv "$SCRIPT_DIR/.venv"
"$SCRIPT_DIR/.venv/bin/pip" install -q -e "$SCRIPT_DIR"[mac]
echo "  ✓ .venv ready and fl-studio-mcp[mac] installed"

echo ""
echo "Registering with Claude Code..."
claude mcp remove fl-studio-mcp 2>/dev/null || true
claude mcp add --transport stdio fl-studio-mcp -- "$SCRIPT_DIR/.venv/bin/python" -m fl_studio_mcp 2>/dev/null && \
  echo "  ✓ fl-studio-mcp registered with Claude Code" || \
  echo "  ! Could not register with Claude Code (is it installed?). Add manually with:" && \
  echo "      claude mcp add --transport stdio fl-studio-mcp -- $SCRIPT_DIR/.venv/bin/python -m fl_studio_mcp"

echo ""
echo "Done. Next steps:"
echo "  1. IAC Driver: Audio MIDI Setup → IAC Driver → enable, add port named 'fLMCP'"
echo "  2. FL Studio: Options → MIDI Settings → Input → Controller type = 'fLMCP Bridge', Port = 1, Enable"
echo "               Options → MIDI Settings → Output → same fLMCP row, Port = 1"
echo "  3. Confirm in FL script output: [fLMCP] bridge ready"
echo "  4. Open any piano roll → scripts dropdown → pick ComposeWithLLM"
echo "  5. System Settings → Privacy & Security → Accessibility → add your terminal and Claude Code"
echo "  6. Restart Claude Code"
