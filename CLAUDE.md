# Project context for Claude

This file gives any future Claude session enough context to be useful immediately.
**Read this entire file before touching any code or making any tool calls.**

---

## Cold-start checklist (read this first every session)

1. This is a macOS FL Studio MCP server. The remote is `https://github.com/calvinw/MacFLStudioMCP.git` (already configured).
2. Everything is committed and pushed. Start by running `git status` to see if there are any uncommitted local changes.
3. **Run tests before every commit:** `cd /Users/calvinw/develop/MacFLStudioMCP && .venv/bin/python -m pytest tests/ -v` — all 15 should pass.
4. **After any code change to the MCP server, tell the user to restart it.** The server runs as a persistent process; changes to `src/fl_studio_mcp/` are not picked up until restart. In Claude Code: `/mcp` → restart `fl-studio-mcp`, or start a fresh session.
5. **Generator tools (`gen_*`) are intentionally disabled.** Do not re-enable them. The LLM computes music theory directly and writes notes with `piano_roll_write_patterns`.
6. **Piano roll workflow is mandatory** — use the `compose` skill. It enforces read → plan → write (plural) → confirm.
7. **No parallel piano roll writes** — they share a single file bus and will race/corrupt.
8. **One-channel-per-pattern navigation** — always use `piano_roll_goto(channel, pattern)` to switch patterns. Never call `pattern_select` or `channel_select` directly for navigation. `piano_roll_goto` uses patterns.select for non-empty patterns (no flicker) and adds openEventEditor only for empty ones. If already on the target pattern, it does nothing.
9. **Writes always call openEventEditor** — `_ensure_piano_roll_on_target` (used by `piano_roll_write_patterns`) always calls `channels.select` + `patterns.select` + `ui.openPianoRoll` regardless of whether the pattern is empty. With `new_window=0` this is a smooth viewport retarget — no window close/reopen. The `current_note_count` param is accepted for backwards compatibility but no longer used.

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
7. **MCP registered** — `claude mcp add --transport stdio fl-studio-mcp -- /Users/calvinw/develop/MacFLStudioMCP/.venv/bin/python -m fl_studio_mcp` (in `~/.claude.json`).

## Files of interest

```
fl_bridge/
├── device_FLStudioMCP.py       # MIDI controller script — file-bus server (runs inside FL)
│                               # also writes events.log (human-readable, tail -f it)
├── event_investigator/
│   └── device_EventInvestigator.py  # standalone event-logger controller (optional)
└── piano_roll/
    ├── ComposeWithLLM.pyscript # piano-roll script — handles add_notes/clear/export_only
    └── fLMCP_bridge.pyscript   # legacy variant, also installed

install_event_investigator.sh   # installs Event Investigator as a separate FL controller
uninstall_event_investigator.sh # removes it

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

## Development rules

- **Run tests before every commit:** `cd /Users/calvinw/develop/MacFLStudioMCP && .venv/bin/python -m pytest tests/ -v` — all 15 must pass.
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
This should no longer happen. `_ensure_piano_roll_on_target` always calls `openEventEditor` with `new_window=0`, which retargets the viewport smoothly without closing or reopening the window — equivalent to double-clicking a pattern in the Playlist. If you see the window close and reopen, check that `new_window=0` is still being passed in `h_ui_open_piano_roll`.

### Reading notes — two cases

**There is no FL API to auto-detect which case applies.** The LLM must ask the user or be told upfront.

Reading notes boils down to two distinct cases depending on how many channels have notes in each pattern.

#### Case 1: One channel per pattern (typical for sequenced projects)

Use `piano_roll_read_patterns_autolocate` (read) and `piano_roll_write_patterns` (write).

**How pattern switching works (reads):**
- `piano_roll_read_patterns_autolocate` uses only `patterns.select` — no `openEventEditor`. For non-empty patterns FL auto-selects the channel and the piano roll follows. For empty patterns the viewport stays wherever it was, but since there are no notes to read, it correctly returns 0 notes. No flicker during reads.

**How pattern switching works (writes):**
- `_ensure_piano_roll_on_target` (called by `piano_roll_write_patterns`) always calls `channels.select` + `patterns.select` + `ui.openPianoRoll` (openEventEditor with `new_window=0`). This guarantees the piano roll viewport is on the correct channel before the pyscript fires — equivalent to double-clicking the pattern in the Playlist. With `new_window=0` there is no window close/reopen.

**Write flow:**

```python
# 1. Read all patterns first (optional but good practice)
read = piano_roll_read_patterns_autolocate()

# 2. Write — no current_note_count needed; openEventEditor is always called
piano_roll_write_patterns([
    {"channel": 1, "pattern": 2, "notes": [...]},
])
```

**There is no FL API to check a pattern's note count without opening it in the piano roll.** The read sweep (`piano_roll_read_patterns_autolocate`) is the only source of truth. Always read before writing.

**Do not use `channels.selected` to infer piano roll state** — it reflects channel rack selection, which is unrelated to what the piano roll viewport is showing.

#### Case 2: Multiple non-empty channels within the same pattern

Each channel in a pattern has its own independent note set. The piano roll **viewport only shows one channel at a time**, and changing channel rack selection does NOT retarget it. This is the core problem.

**Do NOT use** `ui_open_piano_roll_for_channel` — that tool never calls `openEventEditor`. For the multi-channel case (same pattern, different channel), it silently does nothing and returns a misleading `retargeted: True`. The viewport only updates when `openEventEditor` is called.

**Do use** `fl_call_raw("ui.openPianoRoll", {"channel": N})` to force the retarget:

```python
# 1. Discover which channels exist in the project
channels = channel_all()

# 2. For each channel that might have notes in the target pattern:
for ch in [0, 1, 2, ...]:  # 0-based channel indices
    fl_call_raw("ui.openPianoRoll", {"channel": ch})
    # ^ calls openEventEditor to rebuild the viewport for this channel
    time.sleep(0.2)  # let the window settle
    notes = piano_roll_read()
    # store notes for channel ch

# 3. Restore to the original channel
fl_call_raw("ui.openPianoRoll", {"channel": original_ch})
```

**Trade-off:** `fl_call_raw("ui.openPianoRoll", ...)` calls `openEventEditor` every time, which causes a brief piano roll window rebuild (flicker). This is unavoidable — there's no way to change the viewport without it. The `piano_roll_read_patterns_autolocate` tool exists specifically to avoid this flicker when you only need one channel per pattern.

**When you know the layout up front:** Run `channel_all()` first to see which channels are non-empty in a pattern, then only retarget those.

### Navigation — switching the piano roll to a specific channel

Use `piano_roll_goto(channel, pattern)` — it selects the pattern and, for empty patterns, also calls `openEventEditor` to force the viewport. This is the preferred navigation tool.

For the multi-channel-per-pattern case where you need to force a viewport switch regardless of emptiness, use `fl_call_raw` directly:

```python
fl_call_raw("ui.openPianoRoll", {"channel": N})
```

This calls `openEventEditor` and always retargets the viewport immediately.

### Bridge handlers in device script
`h_pianoroll_*` in `device_FLStudioMCP.py` try to write to `Piano roll scripts/` — blocked on Mac (outside controller sandbox). Tools in `tools/piano_roll.py` correctly route around this via `file_bridge.stage_and_run()`. The handlers are dead code kept for Windows compatibility. Do not try to fix them.

## Test scripts

```bash
cd /Users/calvinw/develop/MacFLStudioMCP

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
- **Reads always restore to the original pattern** — always pass `restore_start=True` on read calls. After sweeping patterns to collect notes, FL must return to whatever pattern the user was viewing before.
- **Writes stay on the edited pattern** — leave `restore_start=False` (default) on write calls. After editing a pattern, FL should land on that pattern even if the user was viewing a different one when they made the request.
- **Duplicate PRForm crash** — always pass `new_window=0` to `openEventEditor` when piano roll is already visible.
- **Generator tools removed** — LLM computes music theory natively; `gen_*` tools were redundant wrappers.
- **Fork remote** — `origin` now points at `https://github.com/calvinw/MacFLStudioMCP.git`.
- **Writes landing on wrong channel** — fixed. `_ensure_piano_roll_on_target` had an early-return when the current pattern index matched the target, skipping `openEventEditor`. The piano roll viewport stayed on whatever channel was last open, causing writes to go to the wrong channel. Fix: always call `channels.select` + `patterns.select` + `ui.openPianoRoll`. Confirmed: `new_window=0` makes this a smooth retarget with no window close/reopen.
- **Human-readable event log** — `device_FLStudioMCP.py` now writes `events.log` alongside `events.jsonl` in the bridge folder. `tail -f ~/Documents/Image-Line/FL\ Studio/Settings/Hardware/fLMCP\ Bridge/events.log` to watch live. A standalone Event Investigator controller (`fl_bridge/event_investigator/`) is also available for deeper debugging without touching the bridge.
