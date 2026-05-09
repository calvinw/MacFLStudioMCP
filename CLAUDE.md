# Project context for Claude

This file gives any future Claude session enough context to be useful immediately. **Read this first** before exploring the codebase.

## What this project is

This is **`/Users/calvinw/develop/FLStudioMCP`** — a fork-in-progress of `geezoria/FLStudioMCP` that's being adapted to **work on macOS**. The upstream repo is Windows-only because FL Studio 2025 on Mac runs Python in a deeply-restricted sub-interpreter that blocks the upstream TCP-based architecture entirely.

The git remote still points at upstream (`https://github.com/geezoria/FLStudioMCP.git`). The user (Calvin Williamson, calvin.e.williamson@gmail.com) plans to fork properly on GitHub when ready. **All current work is in the local clone, uncommitted.**

The user also maintains a separate, simpler Mac-native MCP server: `calvinw/fl-studio-mcp` (dev branch, MIDI/SysEx based, ~13 tools). The motivation for this fork is to get FLStudioMCP's 160+ tools working on Mac without the rewrite that re-implementing everything in the other repo would require.

## Current state — what works

End-to-end testing passed through Step 4 of a manual test plan:

| Step | Tested | Status |
|---|---|---|
| 1 | File-bus round-trip (smoke test) | ✅ ~25-50ms latency |
| 2 | Transport, patterns, tempo, channels via REPL | ✅ all visible in FL |
| 3 | Iterate patterns + open each in piano roll | ✅ |
| 4 | Piano roll edit (clear/add/transpose/clear via Cmd+Opt+Y) | ✅ |
| 5 | Through Claude Code MCP | ✅ multi-channel edit + end-of-edit cycle verified |

The MCP server is registered with Claude Code (`claude mcp list` shows `fl-studio-mcp ✓ Connected`).

Heavy optional deps (numpy/librosa/sounddevice/dearpygui) are **not** installed. Voice and audio tool modules are loaded conditionally — the server starts fine without them and just logs `voice tools disabled`/`audio tools disabled`.

## The Mac problem (most important context)

FL Studio 2025 on Mac runs Python 3.12 inside a **sub-interpreter with aggressive audit-hook restrictions**. Capability probe results (run from inside the controller script):

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
print(): OK
```

The audit hook also appears to **sandbox each script to its own subtree**:
- `device_FLStudioMCP.py` lives in `Hardware/fLMCP Bridge/` and can write to `Hardware/fLMCP Bridge/bus/` ✓
- It cannot write to `Settings/Piano roll scripts/` ✗
- The piano-roll script (`ComposeWithLLM.pyscript`) lives in `Piano roll scripts/` and CAN write there ✓

This shaped every architecture decision below.

## Architecture (Mac-adapted)

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code / claude.ai (any MCP host)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ stdio (MCP protocol)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ fl-studio-mcp Python server  (.venv/bin/python -m fl_studio_mcp)│
│   • bridge_client.BridgeClient — file-bus client             │
│   • file_bridge — piano-roll file bus + Cmd+Opt+Y trigger    │
│   • keystroke.send_hotkey_mac — osascript + pynput            │
└──────────────────────┬──────────────────────────────────────┘
                       │ files only (NO TCP, NO MIDI for data)
                       ▼
       ~/Documents/Image-Line/FL Studio/Settings/
       ├─ Hardware/fLMCP Bridge/
       │   ├─ device_FLStudioMCP.py      ← runs in FL's MIDI controller sub-interpreter
       │   ├─ events.jsonl                ← FL writes events here (truncated at OnInit)
       │   └─ bus/
       │       ├─ req_{id}.json           ← MCP writes (atomic via os.rename)
       │       └─ resp_{id}.json          ← FL writes (direct, non-atomic)
       └─ Piano roll scripts/
           ├─ ComposeWithLLM.pyscript     ← runs in FL's piano-roll sub-interpreter
           ├─ fLMCP_request.json          ← MCP writes (FL controller can't reach here!)
           └─ fLMCP_state.json            ← pyscript writes when triggered
                                           (must be pre-created by install_mac.sh —
                                            FL can't create new files in this dir)
```

### Two file buses, not one

1. **Main bus** (`Hardware/fLMCP Bridge/bus/`) — used by 150+ tools. The MIDI controller script services it in `OnIdle()`.
2. **Piano-roll bus** (`Piano roll scripts/fLMCP_*.json`) — used only for piano-roll edits (because the `flpianoroll` API is sandboxed to piano-roll scripts). Triggered by synthesizing `Cmd+Opt+Y` from outside FL via `osascript` (focus FL) + `pynput` (keystroke).

### File operations — what runs where

| Operation | Inside FL bridge | Outside FL (MCP server) |
|---|---|---|
| `open()` for read | ✓ | ✓ |
| `open()` for write to **existing** file in own subtree | ✓ | ✓ |
| `open()` to **create new** file | only inside own subtree | ✓ anywhere |
| `os.listdir` | ✓ | ✓ |
| `os.rename` | ✗ blocked | ✓ |
| `os.unlink` | ✗ blocked | ✓ |
| `os.mkdir` | ✗ blocked | ✓ |
| atomic write via `tmp + rename` | ✗ | ✓ |

**Implications:**
- The MCP server uses atomic `tmp + rename` to write request files (so FL never sees partial JSON).
- FL writes responses directly with `open()/write()` — non-atomic. The client tolerates JSONDecodeError briefly and retries.
- FL never deletes or renames files. It "consumes" a request by truncating the file to 0 bytes via `open(path, "w")`. The MCP client unlinks both files after reading the response.
- All directories must be created from outside FL (`install_mac.sh`).
- All files that FL needs to write to in `Piano roll scripts/` (which is outside its own subtree) must be **pre-created** as empty stubs by `install_mac.sh`.

## Setup requirements (the full Mac install dance)

The user has all of this already configured. For reference:

1. **IAC Driver port** — Audio MIDI Setup → MIDI Studio → IAC Driver → enable, add port named `fLMCP`. (Just `Bus 1` renamed; only one port needed.)
2. **FL Studio MIDI Settings → Input** — find the `fLMCP` IAC row (NOT a blank row). Set Controller type = `fLMCP Bridge`, Port = 1, Enable.
3. **FL Studio MIDI Settings → Output** — same `fLMCP` row, Port = 1.
4. **Critical:** OnIdle does not fire unless an input row is bound to a real (or virtual) MIDI port. With both Input + Output assigned to Port 1, the controller becomes "active" and FL fires its callbacks.
5. **Run `./install_mac.sh`** to copy bridge files and create the bus dir + pre-created stub files in Piano roll scripts/.
6. **Accessibility permission** — System Settings → Privacy & Security → Accessibility → enable for whatever terminal app launches Claude Code (and Claude Code itself). Required for `pynput` to send `Cmd+Opt+Y`.
7. **First-run bind** — In FL Studio, open any piano roll → click the scripts dropdown (top-right of piano roll) → click `ComposeWithLLM` once. This binds `Cmd+Opt+Y` to that script for the rest of the session. FL forgets this on quit and re-quit, but persists across pattern/channel switches.
8. **MCP registration** — `claude mcp add --transport stdio fl-studio-mcp -- /Users/calvinw/develop/FLStudioMCP/.venv/bin/python -m fl_studio_mcp` (already done; lives in `~/.claude.json`).

## Files of interest

```
fl_bridge/
├── device_FLStudioMCP.py          # the MIDI controller script — file-bus server
└── piano_roll/
    ├── ComposeWithLLM.pyscript    # runs in piano-roll sandbox; processes piano-roll requests
    └── fLMCP_bridge.pyscript      # legacy variant, also installed

src/fl_studio_mcp/
├── bridge_client.py               # file-bus client (replaces TCP socket client)
├── file_bridge.py                 # piano-roll file-bus + stage_and_run()
├── keystroke.py                   # send_hotkey_mac() + send_hotkey_windows()
├── protocol.py                    # path helpers (default_bus_dir etc) + RPCError
├── server.py                      # FastMCP entry; conditional import for audio/voice
└── tools/                         # 160+ MCP tools, mostly unchanged

scripts/
├── install_windows.ps1            # original Windows installer (untouched)
├── smoke_test_mac.py              # Step 1 — basic round-trip
├── test_step2_interactive.py      # Step 2 — transport/patterns/tempo
├── test_step3_iterate_patterns.py # Step 3 — pattern iteration workflow
├── test_step4_piano_roll.py       # Step 4 — piano roll edit cycle
├── test_retarget.py               # tests ui.openPianoRoll channel retargeting
└── test_read_all_notes.py         # reads main pattern notes using pattern switching/autolocate

install_mac.sh                     # NEW — Mac installer, replaces install_windows.ps1
docs/MAC_PORT.md                   # NEW — technical archaeology of the port
tests/test_protocol.py             # rewritten for file-bus client
```

## Piano roll edit workflow — MANDATORY

**Always follow this sequence when editing piano roll content. Do not skip steps.**

1. **Read first** — call `piano_roll_read_patterns_autolocate()` before any write, even if you think you know the current state. This confirms what is actually in FL, records the currently-selected pattern/channel, and gives you the ground truth to work from.

2. **Plan edits** — derive the new notes from the read data. Never invent note data from memory or a previous session.

3. **Write with `piano_roll_write_patterns`** (plural) — pass all intended writes as a single list. This tool sequences them internally and restores back to the original pattern/channel **only once at the very end**, exactly like the read tool. Do not use `piano_roll_write_pattern` (singular) for multi-pattern edits — it restores after every single write, causing FL to jump back between each one.

4. **Confirm** — after writing, call `piano_roll_read_patterns_autolocate()` again if there is any doubt about whether the write landed correctly.

### Why this matters

- `piano_roll_write_pattern` (singular) has `restore_start=True` by default. Calling it in a loop restores FL to the original pattern after **every** write — the user sees FL jumping around.
- `piano_roll_write_patterns` (plural) restores only once, at the end — same behaviour as the read tool.
- Skipping the read step risks writing notes derived from stale or imagined state.
- Pattern writes share a single file bus (`fLMCP_request.json`) and a single `Cmd+Opt+Y` trigger — **do not fire writes in parallel**; they will race and corrupt each other.

## Smart things to know

### When debugging "bridge unavailable" errors

Likely causes, in order:
1. FL Studio not running, or the `fLMCP Bridge` controller isn't enabled in MIDI Settings (Input row should be green with Port=1)
2. OnIdle not firing — verify by adding a heartbeat log: if no logs appear in FL's MIDI script output for 30 seconds, the controller isn't getting callbacks. Re-check Input/Output port assignments.
3. The bus dir doesn't exist — `install_mac.sh` should create it; FL can't.

### When piano-roll edits silently fail

`stage_and_run()` returns `ok=False, hotkey_sent=True` means the keystroke fired but the state file never refreshed. Causes:
1. `ComposeWithLLM` is not the currently-bound piano-roll script — user needs to manually run it once from the piano-roll scripts dropdown.
2. FL Studio isn't focused — `osascript` brings it forward but if Accessibility permission is missing, `pynput` can't send the keystroke.
3. The piano roll for the wrong channel is loaded (see next point).

### Piano roll channel retargeting

`ui.openPianoRoll(channel=N, pattern=M)` programmatically loads channel N's piano roll for pattern M, using the documented piano-roll event id: `channels.getRecEventId(N) + midi.REC_Chan_PianoRoll`, then `ui.openEventEditor(event_id, midi.EE_PR, new_window)`. **Critical:** if piano roll is already visible, use `new_window=0` to reuse — passing `new_window=1` repeatedly creates duplicate `PRForm` components and crashes FL Studio with `"Duplicate name: A component named PRForm already exists"`.

`openEventEditor` can still visibly tear down/rebuild the piano-roll window when changing channels. Avoid it when possible. If FL's auto-locate behavior is active and each pattern's notes are on its expected/main channel, prefer pattern-only switching: `patterns.select(pattern)` followed by `piano_roll_read()` / `stage_and_run([{action: "export_only"}])`. The MCP tool `piano_roll_read_patterns_autolocate(patterns_to_read=None, restore_start=True)` implements this workflow and restores the starting pattern.

There's a known visual glitch where explicit channel retargeting can make the piano-roll window disappear/reappear. Pattern-only switching avoids that for projects where auto-locate follows the intended channel.

### Bridge handlers in the device script

The bridge handlers `h_pianoroll_*` (in `device_FLStudioMCP.py`) try to write to `Piano roll scripts/fLMCP_request.json` — this fails on Mac because that dir is outside the controller's sandbox. The Claude-facing tools in `tools/piano_roll.py` correctly route around the bridge by calling `file_bridge.stage_and_run()` directly (which writes from outside FL). The bridge handlers are kept as dead code for Windows compatibility; on Mac they fail silently with a logged warning. **Don't try to "fix" them by routing through the bridge.**

### Don't try these "improvements"

- Adding `os.mkdir` calls in the bridge — blocked
- Adding threads to the bridge — blocked
- Adding subprocess calls in the bridge — blocked
- Always passing `new_window=1` to `openEventEditor` — crashes FL after a few calls
- Removing the IAC port — OnIdle won't fire without it

### Things that probably do work but are untested

- The `[audio]` extras (numpy/librosa/etc) for voice-to-MIDI and audio analysis tools
- High-level generators (`gen_emit_chord_progression`, `gen_emit_drum_pattern`, etc.)
- Step 5 — full Claude Code session driving the MCP server

## Test scripts the user may want to run

```bash
cd /Users/calvinw/develop/FLStudioMCP

# 1. Sanity check the file bus
.venv/bin/python scripts/smoke_test_mac.py

# 2. Watch FL respond to specific calls
.venv/bin/python scripts/test_step2_interactive.py

# 3. Iterate patterns + open piano roll for each
.venv/bin/python scripts/test_step3_iterate_patterns.py

# 4. Piano-roll edit cycle (clear, add chord, transpose, clear)
.venv/bin/python scripts/test_step4_piano_roll.py

# Test piano-roll channel retargeting
.venv/bin/python scripts/test_retarget.py

# Read notes from main/autolocated channels without explicit channel retargeting
.venv/bin/python scripts/test_read_all_notes.py

# Run unit tests (5 pass; 2 fail with no module 'numpy' — those are expected)
.venv/bin/python -m pytest tests/test_protocol.py
```

## When the user asks to commit

Suggested commit message for the bulk of the changes:

```
Add macOS support: replace TCP transport with file-bus

FL Studio 2025's Python sub-interpreter on Mac blocks threads, sockets,
subprocesses, mkdir, unlink, and rename via aggressive audit hooks. The
upstream TCP-based architecture is fundamentally incompatible.

This commit:
- Replaces TCP socket bridge with a file-bus (req_*.json / resp_*.json)
  serviced by OnIdle. The MCP client uses atomic tmp+rename writes; FL
  writes responses directly and the client tolerates partial reads.
- Adds Mac keystroke implementation (osascript focus + pynput Cm+Opt+Y)
  for the piano-roll Cmd+Opt+Y trick.
- Pre-creates the bus directory and piano-roll stub files in
  install_mac.sh because FL can't mkdir or create new files in sibling
  directories.
- Programmatically retargets the piano roll to a specific channel via
  channels.getRecEventId + ui.openEventEditor.
- Makes audio/voice tool modules optional so the server starts without
  numpy/librosa.

Tested end-to-end: 160+ tools, transport, patterns, channels, mixer,
piano-roll edits, all working on macOS 26.3.1 / FL Studio 2025.
```

## Recently asked / resolved

- "Should we fork?" → Yes, fork on GitHub when ready, then `git remote set-url origin <fork-url>`. Local clone is the working copy meanwhile.
- "Will MIDI notes be up to date?" → Yes — stateless on-demand queries from the bridge. No caching/state-mirror like the user's other repo had.
- "Can we iterate patterns?" → Yes; `test_step3_iterate_patterns.py` demonstrates.
- "Can we control which channel × pattern is in the piano roll?" → Yes, via `ui.openPianoRoll(channel=N, pattern=M)`; demonstrated in `test_retarget.py`.
- "Notes wiped during end-of-edit cycle" → **Fixed.** Root cause: `stage_and_run` in `file_bridge.py` was calling `_append_request()` in a loop, which read-and-appended to `fLMCP_request.json` on every action. If the pyscript hadn't cleared the file yet from a prior run, stale actions (especially `clear`) accumulated and re-executed on the next `Cmd+Opt+Y`. Fix: replaced the loop with a single `_write_json(REQUEST_FILE, actions)` — fresh atomic overwrite, no accumulation. Confirmed working: multi-channel edit (2 channels, different notes) followed by end-of-edit cycle retarget reads back correct notes on both channels.
