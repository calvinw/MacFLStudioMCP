#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FL_HARDWARE="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/Event Investigator"
SRC="$SCRIPT_DIR/fl_bridge/event_investigator/device_EventInvestigator.py"

die() { echo ""; echo "  ✗ $*"; echo ""; exit 1; }

[ -f "$SRC" ] || die "Missing: $SRC"

echo "Installing Event Investigator..."

mkdir -p "$FL_HARDWARE"
cp "$SRC" "$FL_HARDWARE/"
echo "  ✓ device_EventInvestigator.py → Hardware/Event Investigator/"

# Pre-create the log file — FL's audit hook blocks new-file creation inside the
# controller sandbox, so the script can only *append* to an existing file.
LOG="$FL_HARDWARE/events.log"
[ -f "$LOG" ] || touch "$LOG"
echo "  ✓ events.log initialized: $LOG"

echo ""
echo "Next steps:"
echo "  1. FL Studio: Options → MIDI Settings → Input"
echo "     Find 'Event Investigator' row, set Port = 1, enable it"
echo "  2. Options → MIDI Settings → Output"
echo "     Same row, Port = 1  (OnIdle won't fire without an output port)"
echo "  3. Reload the script: click the controller row → reload, or restart FL Studio"
echo "  4. Watch the log in a terminal:"
echo "     tail -f \"$LOG\""
echo ""
echo "  The Script Output console (Tools → Script Output) shows the same events."
