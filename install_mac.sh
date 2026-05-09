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
echo "Done. Next steps:"
echo "  1. In FL Studio: Options → MIDI Settings → Input → set Controller type = 'fLMCP Bridge' → Enable"
echo "  2. Confirm in MIDI script output: [fLMCP] TCP server listening on 127.0.0.1:9876"
echo "  3. Open any piano roll → scripts dropdown → pick ComposeWithLLM"
echo "  4. System Settings → Privacy & Security → Accessibility → add your terminal and Claude Code"
echo "  5. Restart Claude Code"
