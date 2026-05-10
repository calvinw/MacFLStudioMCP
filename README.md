# fLMCP — FL Studio MCP server (macOS)

**Model Context Protocol server that gives Claude (or any MCP client) end-to-end
control of FL Studio — transport, patterns, channels, mixer, plugins, piano roll,
playlist, arrangement, automation, and rendering.**

This is a macOS port of [geezoria/FLStudioMCP](https://github.com/geezoria/FLStudioMCP).

## Requirements

- macOS 12+
- FL Studio 2025 (Producer Edition or higher — needs MIDI scripting)
- Python 3.10+
- Accessibility permission granted to your terminal app (needed for `pynput` to
  send `Cmd+Opt+Y`)

## Install

```bash
git clone https://github.com/calvinw/MacFLStudioMCP.git fLMCP
cd fLMCP
./install_mac.sh
```

The installer:

1. Copies `fl_bridge/device_FLStudioMCP.py` to
   `~/Documents/Image-Line/FL Studio/Settings/Hardware/fLMCP Bridge/`
2. Copies `fl_bridge/piano_roll/ComposeWithLLM.pyscript` to
   `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/`
3. Pre-creates `fLMCP_request.json` and `fLMCP_state.json` as empty stubs.
4. Creates the `bus/` directory.
5. Creates `.venv/` and installs the package editable (`pip install -e .`).
6. Adds an `fl-studio-mcp` entry to `~/.claude.json` (Claude Code).

## One-time setup

### IAC Driver

1. Open **Audio MIDI Setup** (Applications → Utilities).
2. Menu: **Window → Show MIDI Studio**.
3. Double-click **IAC Driver** → check **Device is online** → add a port named
   `fLMCP` (rename the default `Bus 1`). Click Apply.

### Accessibility permission

System Settings → Privacy & Security → Accessibility → enable your terminal
app (e.g. iTerm2, Terminal) **and** Claude Code. Without this `pynput` cannot
send `Cmd+Opt+Y` and piano-roll edits will silently fail.

## FL Studio activation (each launch)

1. Launch FL Studio 2025.
2. **Options → MIDI Settings → Input**: find the `fLMCP` IAC Driver row. Set
   **Controller type** = `fLMCP Bridge`, **Port** = 1, click **Enable**.
3. **Options → MIDI Settings → Output**: same `fLMCP` row, Port = 1.
4. Open FL's script output (**View → Script output**) and confirm you see
   `[fLMCP] bridge ready`.
5. Open any piano roll, click the **scripts dropdown** (top-right corner), and
   click **ComposeWithLLM**. Repeat this step each time you relaunch FL.

## Using with Claude Code (stdio)

The installer already adds the server to `~/.claude.json`. Restart Claude Code
to pick it up, then verify:

```bash
.venv/bin/python scripts/smoke_test_mac.py
```

Expected output: project metadata, transport status, the first few channels /
mixer tracks / patterns, and a round-trip latency around 25–50 ms.

## Using with Claude.ai (HTTP)

Claude.ai connects to MCP servers over HTTP. Start the server in HTTP mode:

```bash
.venv/bin/python -m fl_studio_mcp --transport http --port 8000
```

Keep this terminal open while using Claude.ai.

### Expose the server

Claude.ai runs in the cloud and cannot reach `127.0.0.1` directly. Use
[ngrok](https://ngrok.com) to create a tunnel:

```bash
ngrok http 8000
```

Copy the `https://…ngrok-free.app` URL it prints.

> **Security note:** the tunnel exposes your FL Studio instance to anyone who
> knows the URL. Use ngrok's auth token (or a paid plan with IP allowlist) to
> restrict access.

### Add the server in Claude.ai

1. Go to **claude.ai → Settings → Integrations**.
2. Click **Add MCP server**.
3. Enter the ngrok URL as the server URL.
4. Save. Claude.ai will probe the endpoint and list the available tools.

## Tool catalogue

| Area | Highlights |
| --- | --- |
| Meta | ping, reconnect, bridge info, raw escape hatch |
| Transport | play / stop / record, tempo (undoable), time signature, metronome, jog |
| Patterns | create, rename, clone, color, length, find-by-name |
| Channels | full rack, step sequencer get / set, routing, trigger note |
| Mixer | vol / pan / mute / solo / arm, sends, 3-band EQ, FX slots |
| Plugins | get / set / search params, preset navigation, show editor |
| Piano roll | add, read (single + multi-pattern autolocate), write (single + multi-pattern), clear, quantize, transpose, humanize, duplicate |
| Playlist | tracks, clips, markers |
| Arrangement | current, list, select, jump marker |
| Automation | tempo, channel vol / pan, mixer vol, plugin params |
| Project | metadata, save, save-as, undo / redo, render |
| UI | show / hide windows, hints, scroll to channel |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `bridge unavailable` | FL not running, or the fLMCP Bridge controller isn't enabled. Check Options → MIDI Settings → Input; the fLMCP row should be green with Port = 1. |
| `OnIdle` never fires (no log output) | Both Input **and** Output must be assigned to the IAC fLMCP port at Port = 1. |
| Piano-roll edits silently fail (`ok=False, hotkey_sent=True`) | `ComposeWithLLM` is not the active piano-roll script — click it once from the scripts dropdown. Or Accessibility permission is missing. |
| Piano-roll window disappears/reappears | Use `piano_roll_read_patterns_autolocate` and `piano_roll_write_patterns` (pattern-only switching) to avoid explicit channel retargeting. |
| `pynput` error on install | Make sure Accessibility permission is granted before running the MCP server. |
| `voice_*` / `audio_*` tools missing | Heavy optional deps not installed. Run `pip install "fl-studio-mcp[audio]"` if you need them. |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
```

Tests in `tests/` run entirely offline — no FL Studio needed.

## Contributing

Issues and PRs welcome at <https://github.com/calvinw/MacFLStudioMCP>. Please
run `pytest` before opening a PR.

## License

MIT. See [`LICENSE`](LICENSE) if present, or the `license` field in
[`pyproject.toml`](pyproject.toml).
