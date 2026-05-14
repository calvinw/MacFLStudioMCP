#!/bin/bash
set -e

FL_HARDWARE="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware/Event Investigator"

echo "Uninstalling Event Investigator..."

if [ -d "$FL_HARDWARE" ]; then
    rm -rf "$FL_HARDWARE"
    echo "  ✓ Removed: $FL_HARDWARE"
else
    echo "  ! Not found: $FL_HARDWARE (nothing to remove)"
fi

echo ""
echo "Done. Remove the controller from FL Studio manually:"
echo "  Options → MIDI Settings → Input → find 'Event Investigator' row → disable"
