"""fl-studio-mcp — FastMCP entry point.

Run with:
    python -m fl_studio_mcp
or:
    fl-studio-mcp
"""

from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .resources import project as r_project
from .tools import (
    arrangement,
    automation,
    channels,
    generators,
    meta,
    mixer,
    patterns,
    piano_roll,
    playlist,
    plugins,
    project,
    transport,
    ui,
)

# Audio + voice tools depend on heavy optional packages (numpy/librosa/sounddevice/
# dearpygui). Import lazily so the server still starts when those aren't installed.
try:
    from .tools import audio  # type: ignore
except ImportError as _audio_err:
    audio = None
    _audio_import_error: Exception | None = _audio_err
else:
    _audio_import_error = None

try:
    from .tools import voice  # type: ignore
except ImportError as _voice_err:
    voice = None
    _voice_import_error: Exception | None = _voice_err
else:
    _voice_import_error = None

LOG_LEVEL = os.environ.get("FL_MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

log = logging.getLogger("fl_studio_mcp")


def build_app() -> FastMCP:
    mcp = FastMCP(
        "fl-studio-mcp",
        instructions=(
            "MCP server for FL Studio. Exposes full control: transport, patterns, channels, "
            "mixer, plugins, piano roll, playlist, arrangement, automation, rendering, high-level "
            "music generators (chord progressions, basslines, drum grooves). Requires the fLMCP "
            "bridge script installed in FL Studio (see scripts/install_windows.ps1). If calls fail "
            "with 'bridge unavailable', ask the user to ensure FL Studio is running and the "
            "bridge MIDI device is enabled under Options > MIDI > Input."
        ),
    )

    # tool modules
    meta.register(mcp)
    transport.register(mcp)
    patterns.register(mcp)
    channels.register(mcp)
    mixer.register(mcp)
    plugins.register(mcp)
    playlist.register(mcp)
    arrangement.register(mcp)
    automation.register(mcp)
    project.register(mcp)
    ui.register(mcp)
    piano_roll.register(mcp)
    generators.register(mcp)
    if voice is not None:
        voice.register(mcp)
    else:
        log.info("voice tools disabled (install fl-studio-mcp[audio] to enable): %s",
                 _voice_import_error)
    if audio is not None:
        audio.register(mcp)
    else:
        log.info("audio tools disabled (install fl-studio-mcp[audio] to enable): %s",
                 _audio_import_error)

    # resources
    r_project.register(mcp)

    log.info("fl-studio-mcp initialised")
    return mcp


def main() -> None:
    app = build_app()
    app.run()


if __name__ == "__main__":
    main()
