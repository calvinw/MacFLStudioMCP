# Mac Port — Technical Notes

This document captures the journey of porting FLStudioMCP to macOS. The motivating constraint is that **FL Studio 2025 on Mac runs Python 3.12 inside a sub-interpreter with extremely aggressive audit hooks**, breaking the upstream TCP-based architecture entirely.

## Capability probe results

A capability probe was run inside the FL Studio bridge script's `OnInit()` to characterize what the sub-interpreter actually allows. Results:

```
python:     3.12.1
threads:    FAIL — start_new_thread returned NULL
sockets:    FAIL — _socket.socket.__init__ returned NULL
subprocess: FAIL — audit hook returned NULL
tempfile:   FAIL — bad argument type for built-in operation (audit hook)
mkdir:      FAIL — built-in function mkdir returned NULL
unlink:     FAIL — silently (initially observed via never-deleted req files)
rename:     FAIL — error return without exception set
listdir:    OK
open(): OK for read; OK for write to existing files
print() to script output: OK
FL Studio's own API modules (channels, mixer, ...): OK
```

**Inference:** the audit hook is whitelisting only basic file I/O on existing files. Anything that emits an audit event (`subprocess`, `tempfile.NamedTemporaryFile`) or invokes a syscall that creates/destroys a file system entry (`mkdir`, `unlink`, `rename`, `mkfifo`) is blocked.

## Subtree sandbox

A second observation: **the audit hook also restricts the bridge to writing only inside its own directory subtree.** The bridge script (`device_FLStudioMCP.py`) lives in `Hardware/fLMCP Bridge/`. From there:

- Writing to `Hardware/fLMCP Bridge/bus/` ✓ works
- Writing to `Settings/Piano roll scripts/fLMCP_request.json` ✗ fails with `<class '_io.FileIO'> returned NULL`

The piano-roll script (`ComposeWithLLM.pyscript`) lives in `Piano roll scripts/` and **can** write there — each script is sandboxed to its own home directory.

## Architecture decisions

### 1. Drop TCP entirely

Upstream uses a TCP server inside FL Studio (port 9876) with a daemon thread. With sockets and threads both blocked, this is unsalvageable. We replaced it with a file bus.

### 2. File polling driven by OnIdle

The bridge has no event loop of its own — it relies on FL's `OnIdle()` callback firing periodically (~10–30 Hz when the controller is properly bound). Each tick:

1. `os.listdir(bus_dir)` for `req_*.json` files
2. Filter out zero-byte files (those are already-consumed requests)
3. Read each remaining request via `open()` + `json.loads`
4. Truncate the file to mark it consumed (`open(path, 'w')` with no content — we can't `os.unlink`)
5. Execute the action through the FL API
6. Write the response directly to `resp_{id}.json` via `open()` + `write()` (non-atomic)

### 3. Atomic-write asymmetry

Because `os.rename` is blocked inside FL, only the MCP server (which runs *outside* the sub-interpreter) can do atomic writes:

- **MCP → FL** (request): MCP writes to `req_{id}.json.tmp`, then `os.rename` to `req_{id}.json`. FL never sees a partial request.
- **FL → MCP** (response): FL writes directly to `resp_{id}.json`. MCP polls; if it reads mid-write, JSONDecodeError fires and we retry on the next 20ms tick.

### 4. MCP client handles all cleanup

Since FL can't `unlink`, the MCP client deletes both files (request + response) after a successful round-trip. On timeout, the client cleans up the request file. This means:

- The bus dir never accumulates stale state in the success path
- A server crash after writing a request but before reading the response leaves a stale request — but FL truncates it after consuming, so it's harmless on next listdir scan (zero-byte → filtered out)

### 5. Pre-create directories and stub files via install_mac.sh

FL can't `mkdir`. Both `Hardware/fLMCP Bridge/bus/` and the piano-roll stub files (`fLMCP_request.json`, `fLMCP_state.json`) must exist before FL Studio starts up. `install_mac.sh` creates them all.

### 6. Stateless on-demand queries

Upstream uses some server-push events (`transport.tick`, `refresh`, `projectLoad`) over the TCP connection. We dropped those for now — events can be appended to `events.jsonl` and tailed by the MCP server, but no consumer needs them yet, so the work is deferred.

This actually fixes a problem the user had in their other repo (`calvinw/fl-studio-mcp`), where they tracked FL state in Python via `device_FLResponse.py` + `OnDirtyChannel`/`OnRefresh` callbacks. The state mirror was complex (channels, patterns, focused window, target-channel menu interactions) and prone to drift. Our model is simpler: no state mirror, just ask FL each time.

### 7. Mac keystroke for the piano-roll Cmd+Opt+Y trick

`flpianoroll` (the only API for adding/deleting notes) is sandboxed to piano-roll scripts. The bridge can't call it. The trick is to install a piano-roll script (`ComposeWithLLM.pyscript`) that's bound to `Cmd+Opt+Y`, then synthesize that keystroke from outside FL after staging a JSON request file.

We added a Mac implementation in `keystroke.py`:

```python
def send_hotkey_mac() -> bool:
    # Bring FL Studio to front
    subprocess.run(['osascript', '-e',
                    'tell application "System Events" to '
                    'tell process "OsxFL" to set frontmost to true'])
    time.sleep(0.1)
    # Send keystroke
    from pynput.keyboard import Key, Controller
    kb = Controller()
    kb.press(Key.cmd); kb.press(Key.alt)
    time.sleep(0.05)
    kb.press('y'); kb.release('y')
    time.sleep(0.05)
    kb.release(Key.alt); kb.release(Key.cmd)
    return True
```

Requires Accessibility permission in System Settings → Privacy & Security → Accessibility for whatever terminal launches the MCP server.

### 8. Piano roll channel retargeting

`ui.showWindow(piano_roll)` opens the window but doesn't pick which channel's notes are loaded. To force retargeting:

```python
event_id = channels.getRecEventId(channel_index)
visible = ui.getVisible(piano_roll_window) == 1
new_window = 0 if visible else 1
ui.openEventEditor(event_id, 1, new_window)  # mode=1 → piano-roll editor
```

**Important:** when `visible=True`, `new_window=0` reuses the existing window. Passing `new_window=1` repeatedly creates duplicate `PRForm` components and crashes FL Studio with:

```
Exception: Duplicate name: A component named "PRForm" already exists
```

### 9. Optional heavy deps

`tools/audio.py` and `tools/voice.py` import `numpy`, `librosa`, etc. at module load. These are heavy and not needed for the core 90% of functionality. `server.py` imports them inside `try/except ImportError` and skips registration if unavailable, logging `voice tools disabled` / `audio tools disabled`.

## Setup gotcha: OnIdle won't fire without a port binding

Spent about an hour confused about why `OnInit` ran but `OnIdle` never fired. Cause: the user had set `Controller type = fLMCP Bridge` on a blank row in MIDI Settings → Input, but no MIDI port was assigned to that row.

**FL Studio only fires `OnIdle` for controllers that are bound to an actual MIDI port** (real or virtual). The fix: create an IAC Driver port in Audio MIDI Setup (named `fLMCP`), find the corresponding row in FL's MIDI Input list, set Controller type + Port = 1 + Enable. Same for Output.

A heartbeat log in `OnIdle` is a useful diagnostic — if no heartbeats appear within ~10 seconds, the controller is loaded but not active.

## Failure modes still possible

- **Piano roll visual cache staleness** — when reusing the piano-roll window (`new_window=0`), notes can briefly appear missing until the user closes+reopens. Workaround: live with it.
- **The user must run `ComposeWithLLM` once via the piano-roll scripts dropdown** at the start of each FL session. `Cmd+Opt+Y` re-runs whichever piano-roll script was last launched manually.
- **The user must have the right channel × pattern's piano roll loaded before piano-roll edits.** Programmatic retargeting via `ui.openPianoRoll` works (see point 8 above), but if the user manually navigates afterward without going through `ui.openPianoRoll`, the next piano-roll edit will affect whichever channel is currently shown.

## Files changed in the port

- `fl_bridge/device_FLStudioMCP.py` — replaced TCP server (~250 lines deleted) with file-bus polling (~80 lines added). Bridge handlers unchanged.
- `src/fl_studio_mcp/bridge_client.py` — full rewrite, file-bus instead of TCP socket.
- `src/fl_studio_mcp/protocol.py` — stripped TCP framing helpers; now exposes path helpers + `RPCError`.
- `src/fl_studio_mcp/file_bridge.py` — minor docstring updates.
- `src/fl_studio_mcp/keystroke.py` — added `send_hotkey_mac`, kept `send_hotkey_windows`.
- `src/fl_studio_mcp/server.py` — conditional import for audio/voice tools.
- `src/fl_studio_mcp/tools/meta.py` — updated docstrings/hints for file-bus terminology.
- `tests/test_protocol.py` — rewrote against fake worker thread that watches a tmp bus dir.
- `pyproject.toml` — added `[mac]` optional extra (`pynput`).
- `install_mac.sh` — NEW.
- `scripts/smoke_test_mac.py`, `scripts/test_step{2,3,4}_*.py`, `scripts/test_retarget.py` — NEW.
