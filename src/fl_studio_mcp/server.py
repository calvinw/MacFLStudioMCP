"""fl-studio-mcp — FastMCP entry point.

Run with:
    python -m fl_studio_mcp                        # stdio (default)
    python -m fl_studio_mcp --transport http       # streamable-http on port 8000
    python -m fl_studio_mcp --transport http --port 9000 --host 127.0.0.1
or:
    fl-studio-mcp
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .resources import project as r_project
from .tools import (
    arrangement,
    automation,
    channels,
    # generators,  # disabled: LLM can compute music theory and emit notes directly
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


def build_app(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    mcp = FastMCP(
        "fl-studio-mcp",
        instructions=(
            "MCP server for FL Studio on macOS. Exposes full control: transport, patterns, channels, "
            "mixer, plugins, piano roll, playlist, arrangement, automation, and rendering. "
            "Requires the fLMCP bridge script installed in FL Studio (see install_mac.sh). If calls "
            "fail with 'bridge unavailable', ensure FL Studio is running and the fLMCP Bridge MIDI "
            "device is enabled under Options > MIDI Settings > Input with an IAC Driver port."
        ),
        host=host,
        port=port,
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
    # generators.register(mcp)  # disabled: LLM computes music theory natively
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
    parser = argparse.ArgumentParser(description="FL Studio MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transport (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transport (default: 8000)")
    args = parser.parse_args()

    app = build_app(host=args.host, port=args.port)
    if args.transport == "http":
        app.run(transport="streamable-http")
    else:
        app.run()


if __name__ == "__main__":
    main()
