# fLMCP — FL Studio MCP server (macOS)

**Model Context Protocol server that gives Claude (or any MCP client) end-to-end
control of FL Studio — transport, patterns, channels, mixer, plugins, piano roll,
playlist, arrangement, automation, and rendering.**

This is a macOS port of [geezoria/FLStudioMCP](https://github.com/geezoria/FLStudioMCP).
The upstream repo is Windows-only. FL Studio 2025 on macOS runs Python in a
heavily-restricted sub-interpreter that blocks sockets, threads, subprocesses,
and most filesystem operations — so the upstream TCP architecture cannot work on
Mac. This fork replaces it with a file-bus approach that works within those
constraints.

## Why not TCP / sockets?

The upstream server opens a TCP socket inside FL's Python interpreter
(`127.0.0.1:9876`). On Windows this works because FL ships `_socket.pyd` in a
permissive environment. On macOS, FL Studio 2025 runs Python 3.12 inside a
**sub-interpreter with aggressive audit-hook restrictions**:

```
threads:    FAIL — start_new_thread returned NULL
sockets:    FAIL — _socket.socket.__init__ returned NULL
subprocess: FAIL — audit hook blocks
tempfile:   FAIL — audit hook blocks
mkdir:      FAIL — audit hook blocks
unlink:     FAIL — audit hook blocks
rename:     FAIL — audit hook blocks
listdir:    OK
open() / read / write to existing files in own subtree: OK
```

There is currently no known way to open a socket inside FL Studio's Python
interpreter on macOS. If a future FL update lifts these restrictions the server
can be switched back to TCP with minimal changes — the file-bus is a thin layer
on top of the same RPC protocol.

## Architecture (macOS file-bus)

```
┌─────────────────────────────────────────────────────────────┐
│ Claude / any MCP host                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ stdio (MCP protocol)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ fl-studio-mcp  (.venv/bin/python -m fl_studio_mcp)          │
│   • BridgeClient — file-bus RPC client                      │
│   • file_bridge  — piano-roll bus + Cmd+Opt+Y trigger       │
│   • keystroke    — osascript focus + pynput keystroke       │
└──────────────────────┬──────────────────────────────────────┘
                       │ plain files only  (no TCP, no MIDI data)
                       ▼
  ~/Documents/Image-Line/FL Studio/Settings/
  ├─ Hardware/fLMCP Bridge/
  │   ├─ device_FLStudioMCP.py      ← MIDI controller script (runs inside FL)
  │   └─ bus/
  │       ├─ req_{id}.json           ← MCP writes (atomic tmp+rename)
  │       └─ resp_{id}.json          ← FL writes (direct open/write)
  └─ Piano roll scripts/
      ├─ ComposeWithLLM.pyscript     ← piano-roll script (runs inside FL)
      ├─ fLMCP_request.json          ← staged piano-roll actions
      └─ fLMCP_state.json            ← result written by pyscript
```

### How requests flow

1. The MCP server writes a JSON request to `bus/req_{id}.json` atomically
   (write to a temp file, then `os.rename`).
2. FL's MIDI controller script polls in `OnIdle()`, finds the request, executes
   the FL Python API call on FL's main thread, and writes the response to
   `bus/resp_{id}.json`.
3. The MCP server reads the response, tolerating brief `JSONDecodeError` while
   FL is still writing, then deletes both files.

Piano-roll edits use a second bus (`fLMCP_request.json`) because the
`flpianoroll` module is only available inside piano-roll scripts. The MCP server
stages the edit, then synthesises `Cmd+Opt+Y` via `osascript` (focus FL) +
`pynput` (keystroke) to trigger `ComposeWithLLM.pyscript`.

### Why IAC Driver instead of loopMIDI

On Windows the upstream used loopMIDI to give FL's MIDI controller script a
port to bind to (FL's `OnIdle` callback only fires when a controller is active).
On macOS the equivalent is the built-in **IAC Driver** — no third-party software
needed. No MIDI data actually flows through it; the port is purely a heartbeat
so FL keeps the controller script alive.

## Install

Requirements:

- macOS 12+
- FL Studio 2025 (Producer Edition or higher — needs MIDI scripting)
- Python 3.10+ (used once to create the venv)
- Accessibility permission granted to your terminal app (needed for `pynput` to
  send `Cmd+Opt+Y`)

```bash
git clone https://github.com/calvinw/FLStudioMCP.git fLMCP
cd fLMCP
./install_mac.sh
```

What the installer does:

1. Copies `fl_bridge/device_FLStudioMCP.py` to
   `~/Documents/Image-Line/FL Studio/Settings/Hardware/fLMCP Bridge/`
2. Copies `fl_bridge/piano_roll/ComposeWithLLM.pyscript` to
   `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/`
3. Pre-creates `fLMCP_request.json` and `fLMCP_state.json` as empty stubs
   (FL's sandbox can write to existing files but cannot create new ones outside
   its own subtree).
4. Creates `bus/` directory for the main file-bus.
5. Creates `.venv/` and installs the MCP package editable (`pip install -e .`).
6. Adds an `fl-studio-mcp` entry to `~/.claude.json` (Claude Code).

### IAC Driver setup (one-time)

1. Open **Audio MIDI Setup** (Applications → Utilities).
2. Menu: **Window → Show MIDI Studio**.
3. Double-click **IAC Driver** → check **Device is online** → add a port named
   `fLMCP` (rename the default `Bus 1`). Click Apply.

### FL Studio-side activation

1. Launch FL Studio 2025.
2. **Options → MIDI Settings → Input**: find the `fLMCP` IAC Driver row. Set
   **Controller type** = `fLMCP Bridge`, **Port** = 1, click **Enable**.
3. **Options → MIDI Settings → Output**: same `fLMCP` row, Port = 1.
   *(Both Input and Output must be assigned — FL only fires `OnIdle` on active
   controllers, and a controller is only considered active when both directions
   are bound.)*
4. Open FL's script output (**View → Script output**) and confirm you see
   `[fLMCP] bridge ready`.
5. Open any piano roll, click the **scripts dropdown** (top-right corner of the
   piano roll window), and click **ComposeWithLLM**. This binds `Cmd+Opt+Y` to
   the pyscript. FL remembers this across pattern/channel switches for the
   session, but forgets it on quit — repeat step 5 each time you relaunch FL.
6. Restart Claude Code so it picks up the new MCP entry.

### Accessibility permission

System Settings → Privacy & Security → Accessibility → enable your terminal
app (e.g. iTerm2, Terminal) **and** Claude Code. Without this `pynput` cannot
send `Cmd+Opt+Y` and piano-roll edits will silently fail.

## Quick check

```bash
.venv/bin/python scripts/smoke_test_mac.py
```

Expected output: project metadata, transport status, the first few channels /
mixer tracks / patterns, and a round-trip latency around 25–50 ms.

## Piano roll edit workflow

**Always follow this sequence. Skipping steps causes stale writes or FL jumping
around visually.**

1. **Read first** — `piano_roll_read_patterns_autolocate()` before any write.
2. **Plan** — derive notes from the read data; never invent from memory.
3. **Write** — `piano_roll_write_patterns` (plural) for multi-pattern edits.
   Do not call `piano_roll_write_pattern` (singular) in a loop — it fires a
   separate `Cmd+Opt+Y` per write and is slower.
4. **Confirm** — read again if there is any doubt the write landed.

Pattern writes share a single file bus and a single `Cmd+Opt+Y` trigger —
**do not fire writes in parallel**; they will race and corrupt each other.

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
| Piano-roll edits silently fail (`ok=False, hotkey_sent=True`) | `ComposeWithLLM` is not the active piano-roll script — click it once from the scripts dropdown. Or Accessibility permission is missing for your terminal / Claude Code. |
| Piano-roll window disappears/reappears | Explicit channel retargeting uses `openEventEditor`, which can rebuild the window. Use `piano_roll_read_patterns_autolocate` and `piano_roll_write_patterns` (pattern-only switching) to avoid this. |
| `pynput` error on install | Make sure Accessibility permission is granted before running the MCP server, not just before the keystroke. |
| `voice_*` / `audio_*` tools missing | Heavy optional deps not installed. Run `pip install "fl-studio-mcp[audio]"` if you need them. |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
```

Tests in `tests/` run entirely offline — the bridge is faked, so FL Studio does
not need to be running.

## Contributing

Issues and PRs welcome at <https://github.com/calvinw/FLStudioMCP>. Please run
`pytest` before opening a PR. Bug reports are much easier to act on if they
include the FL build number (`Help → About`) and the relevant snippet from
**View → Script output**.

## License

MIT. See [`LICENSE`](LICENSE) if present, or the `license` field in
[`pyproject.toml`](pyproject.toml).
