# Project context for Claude

This file gives any future Claude session enough context to be useful immediately.
**Read this entire file before touching any code or making any tool calls.**

---

## Cold-start checklist (read this first every session)

1. This is a macOS FL Studio MCP server. The remote is `https://github.com/calvinw/MacFLStudioMCP.git` (already configured).
2. Everything is committed and pushed. Start by running `git status` to see if there are any uncommitted local changes.
3. **Run tests before every commit:** `cd /Users/calvinw/develop/FLStudioMCP && .venv/bin/python -m pytest tests/ -v` — all 15 should pass.
4. **After any code change to the MCP server, tell the user to restart it.** The server runs as a persistent process; changes to `src/fl_studio_mcp/` are not picked up until restart. In Claude Code: `/mcp` → restart `fl-studio-mcp`, or start a fresh session.
5. **Generator tools (`gen_*`) are intentionally disabled.** Do not re-enable them. The LLM computes music theory directly and writes notes with `piano_roll_write_patterns`.
6. **Piano roll workflow is mandatory** — use the `compose` skill. It enforces read → plan → write (plural) → confirm.
7. **No parallel piano roll writes** — they share a single file bus and will race/corrupt.
8. **Channel mute workflow is mandatory during edits** — mute all other channels before editing one, restore when done. See the dedicated section below.

---

## What this project is

macOS port of [geezoria/FLStudioMCP](https://github.com/geezoria/FLStudioMCP). The upstream is Windows-only; FL Studio 2025 on macOS runs Python in a heavily-restricted sub-interpreter that blocks the upstream TCP architecture entirely. This fork replaces TCP with a file-bus that works within those constraints.

Calvin Williamson (calvin.e.williamson@gmail.com) maintains this repo. There is also a separate simpler Mac-native MCP server at `calvinw/fl-studio-mcp` (MIDI/SysEx, ~13 tools) — this fork exists to get the full 160+ tool surface working on Mac.

## Current state

All core functionality is working and committed:

| Step | What | Status |
|---|---|---|
| 1 | File-bus round-trip | ✅ ~25-50ms latency |
| 2 | Transport, patterns, tempo, channels | ✅ |
| 3 | Pattern iteration + piano roll open | ✅ |
| 4 | Piano roll edit via Cmd+Opt+Y | ✅ |
| 5 | Full Claude Code MCP session | ✅ multi-channel edit confirmed |

The MCP server is registered with Claude Code (`claude mcp list` shows `fl-studio-mcp ✓ Connected`).

Heavy optional deps (numpy/librosa/sounddevice/dearpygui) are **not** installed — voice and audio tools load conditionally; the server starts fine without them.

## Intentional decisions — do not undo

### Generator tools are disabled

`generators.register(mcp)` is commented out in `server.py`. All `gen_*` tools
(scales, chords, progressions, arpeggios, basslines, drum patterns, melodies)
are removed from the MCP tool list.

**Reason:** The LLM can compute all music theory natively. These tools were
redundant wrappers around hardcoded templates. The correct workflow is:
- LLM reasons about MIDI note numbers directly
- Writes notes with `piano_roll_write_patterns`
- Uses `channel_set_step_sequence` for drum step patterns

To re-enable generators: uncomment `# generators,` in the imports and
`# generators.register(mcp)` in `build_app()` in `src/fl_studio_mcp/server.py`.

---

## The Mac problem (why everything is files)

FL Studio 2025 on macOS runs Python 3.12 inside a **sub-interpreter with aggressive audit-hook restrictions**:

```
threads:    FAIL — start_new_thread returned NULL
sockets:    FAIL — _socket.socket.__init__ returned NULL
subprocess: FAIL — audit hook blocks
tempfile:   FAIL — audit hook blocks
mkdir:      FAIL — audit hook blocks
unlink:     FAIL — audit hook blocks
rename:     FAIL — audit hook blocks
listdir:    OK
open()/read/write to existing files: OK
```

The audit hook also **sandboxes each script to its own subtree**:
- `device_FLStudioMCP.py` lives in `Hardware/fLMCP Bridge/` — can write to `bus/` ✓, cannot write to `Piano roll scripts/` ✗
- `ComposeWithLLM.pyscript` lives in `Piano roll scripts/` — can write there ✓

There is currently no known way to open a socket inside FL Studio's Python interpreter on macOS. If a future FL update lifts these restrictions the server can switch back to TCP with minimal changes.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code / any MCP host                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │ stdio (MCP protocol)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ fl-studio-mcp  (.venv/bin/python -m fl_studio_mcp)          │
│   • BridgeClient  — file-bus RPC client                     │
│   • file_bridge   — piano-roll bus + Cmd+Opt+Y trigger      │
│   • keystroke     — osascript focus + pynput keystroke      │
└──────────────────────┬──────────────────────────────────────┘
                       │ plain files only (no TCP, no MIDI data)
                       ▼
  ~/Documents/Image-Line/FL Studio/Settings/
  ├─ Hardware/fLMCP Bridge/
  │   ├─ device_FLStudioMCP.py      ← MIDI controller (runs inside FL)
  │   └─ bus/
  │       ├─ req_{id}.json           ← MCP writes (atomic tmp+rename)
  │       └─ resp_{id}.json          ← FL writes (direct open/write)
  └─ Piano roll scripts/
      ├─ ComposeWithLLM.pyscript     ← piano-roll script (runs inside FL)
      ├─ fLMCP_request.json          ← staged piano-roll actions (pre-created stub)
      └─ fLMCP_state.json            ← result written by pyscript (pre-created stub)
```

### Two file buses

1. **Main bus** (`bus/`) — 150+ tools. Controller script polls in `OnIdle()`.
2. **Piano-roll bus** (`fLMCP_*.json`) — piano-roll edits only. Triggered by `Cmd+Opt+Y` via osascript + pynput.

### File operations — what runs where

| Operation | Inside FL bridge | Outside FL (MCP server) |
|---|---|---|
| `open()` read | ✓ | ✓ |
| `open()` write to existing file in own subtree | ✓ | ✓ |
| `open()` create new file | own subtree only | ✓ anywhere |
| `os.listdir` | ✓ | ✓ |
| `os.rename` | ✗ blocked | ✓ |
| `os.unlink` | ✗ blocked | ✓ |
| `os.mkdir` | ✗ blocked | ✓ |
| atomic write via tmp+rename | ✗ | ✓ |

**Key implications:**
- MCP server uses atomic `tmp + rename` for requests (FL never sees partial JSON).
- FL writes responses directly — non-atomic. Client retries on JSONDecodeError.
- FL "consumes" requests by truncating to 0 bytes via `open(path, "w")`. MCP client unlinks both files after reading.
- All dirs must be created from outside FL (`install_mac.sh`). All files FL writes to in `Piano roll scripts/` must be pre-created as stubs.

## Setup (already done — for reference only)

1. **IAC Driver** — Audio MIDI Setup → MIDI Studio → IAC Driver → enable → port named `fLMCP`.
2. **FL MIDI Input** — `fLMCP` row, Controller type = `fLMCP Bridge`, Port = 1, Enable.
3. **FL MIDI Output** — same row, Port = 1. *(Both required — OnIdle only fires on active controllers.)*
4. **`./install_mac.sh`** — copies bridge files, creates `bus/`, pre-creates stub files.
5. **Accessibility permission** — System Settings → Privacy & Security → Accessibility → terminal app + Claude Code. Required for `pynput`.
6. **First-run bind** — open any piano roll → scripts dropdown → click `ComposeWithLLM`. Repeat each FL relaunch.
7. **MCP registered** — `claude mcp add --transport stdio fl-studio-mcp -- /Users/calvinw/develop/FLStudioMCP/.venv/bin/python -m fl_studio_mcp` (in `~/.claude.json`).

## Files of interest

```
fl_bridge/
├── device_FLStudioMCP.py       # MIDI controller script — file-bus server (runs inside FL)
└── piano_roll/
    ├── ComposeWithLLM.pyscript # piano-roll script — handles add_notes/clear/export_only
    └── fLMCP_bridge.pyscript   # legacy variant, also installed

src/fl_studio_mcp/
├── bridge_client.py            # file-bus RPC client
├── file_bridge.py              # piano-roll bus + stage_and_run()
├── keystroke.py                # send_hotkey_mac() — osascript focus + pynput Cmd+Opt+Y
├── protocol.py                 # path helpers + RPCError
├── server.py                   # FastMCP entry; generators disabled here
└── tools/
    ├── piano_roll.py           # primary piano roll tools incl. write_pattern(s)
    ├── generators.py           # DISABLED — kept for reference / possible re-enable
    └── ...                     # transport, channels, mixer, patterns, etc.

scripts/
├── smoke_test_mac.py           # Step 1 — basic round-trip test
├── test_step2_interactive.py   # Step 2 — transport/patterns/tempo
├── test_step3_iterate_patterns.py
├── test_step4_piano_roll.py    # Step 4 — piano roll edit cycle
├── test_retarget.py            # piano roll channel retargeting
├── test_read_all_notes.py      # multi-pattern autolocate read
├── pattern_writer_autolocate.py  # reference: autolocate write pattern
└── pattern_generator_multiset.py # reference: multi-pattern analysis before edits

install_mac.sh                  # Mac installer
tests/
├── test_protocol.py            # file-bus client tests (all offline)
├── test_server_build.py        # verifies tool list; asserts gen_* are absent
└── test_generators.py          # music theory unit tests (generators.py still importable)
```

## Channel mute workflow — MANDATORY during edits

**Always mute other channels before editing a channel, unmute when done.**

### Editing a single channel

1. Read all channel mute states (`channel_all`) so you know the current state.
2. **Mute all channels except the one being edited** (`channel_mute` with `muted=True`).
3. Make the edit (piano roll write, step sequence, etc.).
4. **Unmute all channels** that were unmuted before you started.

### Editing multiple channels sequentially

1. Read all channel mute states.
2. For each channel to edit:
   - Mute all *other* channels.
   - Make the edit.
3. When all edits are done, **unmute every channel** that was unmuted before you started.

### Why this matters

The user can hear each channel in isolation as it is being edited, without other parts masking or interfering. Never leave channels in a different mute state than they were in at the start of the session — always restore.

---

## Development rules

- **Run tests before every commit:** `cd /Users/calvinw/develop/FLStudioMCP && .venv/bin/python -m pytest tests/ -v` — all 15 must pass.
- **Smoke test with FL running** for any change that touches `bridge_client.py`, `file_bridge.py`, `device_FLStudioMCP.py`, or `ComposeWithLLM.pyscript`: `.venv/bin/python scripts/smoke_test_mac.py`
- **Do not add `os.mkdir`, threads, subprocess, or sockets inside the FL bridge** — all blocked by audit hook.
- **Do not pass `new_window=1` to `openEventEditor` repeatedly** — crashes FL with duplicate PRForm.
- **Do not remove the IAC port** — OnIdle won't fire without it.
- **Do not re-enable generators** without discussing it first — they were removed intentionally.

## Troubleshooting

### "bridge unavailable"
1. FL Studio not running, or fLMCP Bridge controller not enabled (Input row should be green, Port=1).
2. OnIdle not firing — check both Input AND Output are assigned to the fLMCP IAC port at Port=1.
3. `bus/` dir missing — run `./install_mac.sh`.

### Piano-roll edits silently fail (`ok=False, hotkey_sent=True`)
1. `ComposeWithLLM` not the active piano-roll script — click it once from the scripts dropdown.
2. Accessibility permission missing for terminal / Claude Code.
3. Piano roll open on wrong channel (use pattern-only switching via `piano_roll_read_patterns_autolocate`).

### Piano roll window disappears/reappears
Explicit channel retargeting uses `openEventEditor` which rebuilds the window. Prefer `piano_roll_read_patterns_autolocate` and `piano_roll_write_patterns` (pattern-only switching) to avoid it.

### Bridge handlers in device script
`h_pianoroll_*` in `device_FLStudioMCP.py` try to write to `Piano roll scripts/` — blocked on Mac (outside controller sandbox). Tools in `tools/piano_roll.py` correctly route around this via `file_bridge.stage_and_run()`. The handlers are dead code kept for Windows compatibility. Do not try to fix them.

## Test scripts

```bash
cd /Users/calvinw/develop/FLStudioMCP

# Unit tests (all offline, no FL needed) — run before every commit
.venv/bin/python -m pytest tests/ -v
# Expected: 15 passed

# Live tests (FL must be running)
.venv/bin/python scripts/smoke_test_mac.py        # basic round-trip ~25-50ms
.venv/bin/python scripts/test_step2_interactive.py
.venv/bin/python scripts/test_step3_iterate_patterns.py
.venv/bin/python scripts/test_step4_piano_roll.py
.venv/bin/python scripts/test_retarget.py
.venv/bin/python scripts/test_read_all_notes.py
```

## Recently resolved

- **TCP sockets on Mac** — blocked by audit hook. File-bus is the current approach; no known workaround.
- **Notes wiped during end-of-edit cycle** — fixed. `stage_and_run` was appending to `fLMCP_request.json` instead of overwriting; stale `clear` actions accumulated. Fixed by using a single `_write_json()` call.
- **FL jumping between patterns during multi-pattern write** — fixed. Use `piano_roll_write_patterns` (plural), not `piano_roll_write_pattern` (singular) in a loop.
- **FL jumping back to original pattern/channel after reads and writes** — fixed. `restore_start` now defaults to `False` on all three piano roll tools. FL stays on the last edited/read pattern. Pass `restore_start=True` explicitly only when a deliberate jump-back is needed.
- **Duplicate PRForm crash** — always pass `new_window=0` to `openEventEditor` when piano roll is already visible.
- **Generator tools removed** — LLM computes music theory natively; `gen_*` tools were redundant wrappers.
- **Fork remote** — `origin` now points at `https://github.com/calvinw/MacFLStudioMCP.git`.
