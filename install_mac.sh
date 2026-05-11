#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FL_HARDWARE="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/fLMCP Bridge"
FL_PIANO_ROLL="$HOME/Documents/Image-Line/FL Studio/Settings/Piano roll scripts"

# ── helper ───────────────────────────────────────────────────────────────────
die() { echo ""; echo "  ✗ $*"; echo ""; exit 1; }

# ── source file sanity check ─────────────────────────────────────────────────
for f in \
  "$SCRIPT_DIR/fl_bridge/device_FLStudioMCP.py" \
  "$SCRIPT_DIR/fl_bridge/piano_roll/ComposeWithLLM.pyscript" \
  "$SCRIPT_DIR/fl_bridge/piano_roll/fLMCP_bridge.pyscript"
do
  [ -f "$f" ] || die "Missing source file: $f
  Make sure you cloned the full repository before running this script."
done

# ── FL bridge files ───────────────────────────────────────────────────────────
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
[ -f "$FL_PIANO_ROLL/fLMCP_state.json" ]   || echo "{}" > "$FL_PIANO_ROLL/fLMCP_state.json"
echo "  ✓ fLMCP_request.json + fLMCP_state.json initialized"

# ── find Python 3.10+ ─────────────────────────────────────────────────────────
echo ""
echo "Setting up Python venv..."

# Search order: versioned names first (prefer newer), then fall back to generic.
# Covers: PATH, Homebrew (Apple Silicon + Intel), pyenv shims, python.org installer.
PYTHON=""
SEARCH_CANDIDATES=(
  python3.13 python3.12 python3.11 python3.10
  /opt/homebrew/bin/python3.13
  /opt/homebrew/bin/python3.12
  /opt/homebrew/bin/python3.11
  /opt/homebrew/bin/python3.10
  /usr/local/bin/python3.13
  /usr/local/bin/python3.12
  /usr/local/bin/python3.11
  /usr/local/bin/python3.10
  "$HOME/.pyenv/shims/python3"
  python3
)

for candidate in "${SEARCH_CANDIDATES[@]}"; do
  resolved=$(command -v "$candidate" 2>/dev/null || echo "")
  [ -z "$resolved" ] && [ -x "$candidate" ] && resolved="$candidate"
  [ -z "$resolved" ] && continue

  ver=$("$resolved" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
  if [ "$ver" = "True" ]; then
    PYTHON="$resolved"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  die "Python 3.10 or newer is required but was not found.

  Install it from https://www.python.org/downloads/
  (download the macOS installer, run it, then re-run this script)"
fi

echo "  Using $PYTHON ($("$PYTHON" --version))"

# Remove stale venv if it was built with a different Python (e.g. after a
# failed first run with the wrong Python version).
if [ -d "$SCRIPT_DIR/.venv" ]; then
  existing=$("$SCRIPT_DIR/.venv/bin/python" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
  if [ "$existing" != "True" ]; then
    echo "  Removing stale .venv (wrong Python version)..."
    rm -rf "$SCRIPT_DIR/.venv"
  fi
fi

"$PYTHON" -m venv "$SCRIPT_DIR/.venv"
"$SCRIPT_DIR/.venv/bin/pip" install -q --upgrade pip
"$SCRIPT_DIR/.venv/bin/pip" install -q -e "$SCRIPT_DIR"[mac]
echo "  ✓ .venv ready and fl-studio-mcp[mac] installed"

# ── MCP registration ──────────────────────────────────────────────────────────
echo ""
echo "MCP server command (add this to your MCP client):"
echo "  $SCRIPT_DIR/.venv/bin/python -m fl_studio_mcp"
echo ""

if command -v claude &>/dev/null; then
  echo "  Claude Code detected — registering automatically..."
  claude mcp remove fl-studio-mcp 2>/dev/null || true
  if claude mcp add --transport stdio fl-studio-mcp -- "$SCRIPT_DIR/.venv/bin/python" -m fl_studio_mcp 2>/dev/null; then
    echo "  ✓ fl-studio-mcp registered with Claude Code"
  else
    echo "  ! Auto-registration failed. Add it manually in Claude Code:"
    echo "    claude mcp add --transport stdio fl-studio-mcp -- $SCRIPT_DIR/.venv/bin/python -m fl_studio_mcp"
  fi
else
  echo "  Claude Code CLI not found — add the server manually in your MCP client."
  echo "  For Claude Code:  claude mcp add --transport stdio fl-studio-mcp -- $SCRIPT_DIR/.venv/bin/python -m fl_studio_mcp"
  echo "  For claude.ai:    Settings → Connectors → add the command above as a custom connector"
fi

# ── done ──────────────────────────────────────────────────────────────────────
echo ""
echo "Done. Next steps:"
echo "  1. FL Studio: Options → MIDI Settings → Input → Controller type = 'fLMCP Bridge', Port = 1, Enable"
echo "               Options → MIDI Settings → Output → same fLMCP row, Port = 1"
echo "  2. Confirm in FL script output: [fLMCP] bridge ready"
echo "  3. Open any piano roll → scripts dropdown → pick ComposeWithLLM"
echo "  4. System Settings → Privacy & Security → Accessibility → add your terminal and Claude Code"
echo "  5. Restart Claude Code"
