# fLMCP — FL Studio MCP server (macOS)

**Model Context Protocol server that gives Claude (or any MCP client) end-to-end
control of FL Studio — transport, patterns, channels, mixer, plugins, piano roll,
playlist, arrangement, automation, and rendering.**

This is a macOS port of [geezoria/FLStudioMCP](https://github.com/geezoria/FLStudioMCP).
The original repo has a good overview of the architecture and what is possible —
this fork adapts it for macOS where FL Studio's Python interpreter blocks sockets,
threads, and subprocesses, requiring a file-bus approach instead of TCP.

**See it in action:**

[![FLStudioMCP demo](https://img.youtube.com/vi/np0DxRHHmsQ/maxresdefault.jpg)](https://youtu.be/np0DxRHHmsQ?si=1u5Bi02eK1uj5EIz)

## Two ways to use it

**Agentic tools (Claude Code, OpenCode, Codex)** — the MCP server runs on your
Mac as a subprocess of your coding agent using stdio transport. This is the
default mode and requires no networking.

**Web-based remote MCP connectors (Claude.ai, Mistral.ai)** — the server runs
as a persistent HTTP process on your Mac and is exposed via a public URL using
a cloudflared tunnel. Both Claude.ai and Mistral.ai support remote MCP connectors,
including on their **free tiers**, so you can control FL Studio from either site
without a paid subscription.

## Requirements

- macOS 12+
- FL Studio 2025 (Producer Edition or higher — needs MIDI scripting)
- Python 3.10+
- Accessibility permission granted to your terminal app (needed for `pynput` to
  send `Cmd+Opt+Y`)

## Install

```bash
git clone https://github.com/calvinw/MacFLStudioMCP.git
cd MacFLStudioMCP
./install_mac.sh
```

The installer:

1. Copies `fl_bridge/device_FLStudioMCP.py` to
   `~/Documents/Image-Line/FL Studio/Settings/Hardware/fLMCP Bridge/`
2. Copies `fl_bridge/piano_roll/ComposeWithLLM.pyscript` to
   `~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts/`
3. Pre-creates `fLMCP_request.json` and `fLMCP_state.json` as empty stubs.
4. Creates the `bus/` directory.
5. Creates `.venv/` and installs the package with Mac dependencies (`pip install -e ".[mac]"`).
6. Registers the server with Claude Code via `claude mcp add`.

## One-time setup

### IAC Driver

1. Open **Audio MIDI Setup** (Applications → Utilities).
2. Menu: **Window → Show MIDI Studio**.
3. Double-click **IAC Driver** → check **Device is online** → add a port named
   `fLMCP` (rename the default `Bus 1`). Click Apply.

![IAC Driver setup](https://github.com/user-attachments/assets/498d813f-145c-415b-92e4-6c1e8fc61733)

![IAC Driver port](https://github.com/user-attachments/assets/2d0482d8-d2a6-4e33-b0c8-a429515c88d5)

### Accessibility permission

System Settings → Privacy & Security → Accessibility → enable your terminal
app (e.g. iTerm2, Terminal) **and** Claude Code. Without this `pynput` cannot
send `Cmd+Opt+Y` and piano-roll edits will silently fail.

## FL Studio activation

### One-time MIDI setup

1. Launch FL Studio 2025.
2. **Options → MIDI Settings → Input**: find the `fLMCP` IAC Driver row. Set
   **Controller type** = `fLMCP Bridge`, **Port** = 1, click **Enable**.
3. **Options → MIDI Settings → Output**: same `fLMCP` row, Port = 1.
   *(The IAC Driver requires both Input and Output to be bound — FL only keeps
   a controller script's `OnIdle` firing when both directions are active.)*

![MIDI Settings](https://github.com/user-attachments/assets/531e0c61-f0cb-4c2d-bd0e-0a045c308cb7)

FL remembers these settings — you only need to do this once.

### Each launch

1. Open FL's script output (**View → Script output**) and confirm you see
   `[fLMCP] bridge ready`.
2. Open any piano roll, click the **scripts dropdown** (top-right corner), and
   click **ComposeWithLLM**. FL forgets this on quit, so repeat each time you
   relaunch FL.

## Using with Claude Code (stdio)

The installer registers the server via `claude mcp add`. Restart Claude Code
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
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
to create a free tunnel with a random public URL — no account required:

```bash
cloudflared tunnel --url http://localhost:8000
```

It prints a line like:

```
Your quick Tunnel has been created! Visit it at (it may take some time to be fully reachable):
https://random-words-here.trycloudflare.com
```

Copy that `https://…trycloudflare.com` URL — you'll use it in the next step.

> **Security note:** the tunnel exposes your FL Studio instance to anyone who
> knows the URL. The random URL is unguessable, but stop the tunnel when you're
> done to close access.

### Add the server in Claude.ai

1. Go to **claude.ai → Settings → Integrations**.
2. Click **Add custom integration** (or **Add MCP server**).
3. Fill in the fields:
   - **Name:** `FLStudioMCP`
   - **URL:** `https://random-words-here.trycloudflare.com/mcp`
     *(replace `random-words-here` with the actual subdomain from your tunnel)*
   - **Authentication:** None
4. Click **Save**. Claude.ai will connect and list the available tools.

## License

MIT. See [`LICENSE`](LICENSE) if present, or the `license` field in
[`pyproject.toml`](pyproject.toml).
