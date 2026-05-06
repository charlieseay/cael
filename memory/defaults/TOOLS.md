# Cael: TOOLS

## Primer

This file documents the tools available to Cael and when to use them. Use tools to produce verified outcomes from actual system state — not speculative narration based on assumptions.

---

## Mac Mini Tools (Direct Execution — Output Returned)

### `run_shell(command)`
Run an approved shell command and get the output back immediately.
- **Use for:** git status, docker ps/logs, ls, cat, grep, df, ping, ps aux, curl GET, brew list, npm run, xcodebuild
- **Blocked:** rm, sudo, git push/commit, docker stop/rm, curl POST
- **Timeout:** 15s (60s for build commands)
- **Output:** capped at 4KB

### `read_file(path)`
Read a file from a trusted path on the Mac Mini.
- **Trusted paths:** ~/Projects/, ~/Library/Application Support/SoniqueBar/, /Volumes/data/, SeaynicNet vault
- **Output:** capped at 8KB

### `list_dir(path)`
List directory contents with file sizes and modification dates.
- **Same trusted path restrictions as read_file**

### `get_clipboard()`
Read the current contents of the Mac's clipboard (pbpaste).

### `set_clipboard(text)`
Write text to the Mac's clipboard (pbcopy).

---

## Mac Control Tools (Via SoniqueBar Queue — Fire and Forget)

### `mac_open_url(url)`
Open a URL in the default browser.

### `mac_open_app(app)`
Launch an application by name (e.g., "Xcode", "Notes", "Finder").

### `mac_run_applescript(script)`
Run arbitrary AppleScript. Use for complex automation that cannot be done via simpler tools.

### `mac_key_press(keys)`
Send a keyboard shortcut (e.g., "cmd+space", "cmd+tab", "return").

### `mac_send_notification(message, title, subtitle)`
Display a macOS notification banner. Use for important proactive alerts.

### `mac_shell_command(command)`
Run a shell command via SoniqueBar's AppleScript bridge (fire-and-forget — no output returned).
Prefer `run_shell` when you need the output. Use this only when GUI context is required.

### `mac_get_active_app()`
Get the name of the currently focused application.

---

## Memory Tools

### `persona_memory(action, file, content)`
Read or write Cael's persona files (IDENTITY, SOUL, RULES, TOOLS, CONVERSATIONS, MEMORY).
- **action:** "read", "write", "append"
- **files:** IDENTITY, SOUL, RULES, TOOLS, CONVERSATIONS, MEMORY
- Always read before writing.

### `memory_short(action, key, value, ttl)`
Short-term key-value memory that persists across agent restarts.
- **action:** "set", "get", "delete", "list"
- **ttl:** optional expiry in seconds

---

## Knowledge and Search

### `web_search(query)`
Search the web for current information. Use for facts, news, documentation, or anything that may have changed recently.

---

## Infrastructure and Workflow

### `route_task(task, context)`
Dispatch a task to the right agent (Helmsman, CURSOR, GEM).

### `route_metrics()`
Get current LLM routing statistics.

### `router_memory(query)`
Look up past routing decisions and patterns.

### Helmsman tools
Manage tasks in the Helmsman queue — check status, dispatch work, update task state.

### n8n workflow tools
Trigger n8n automation workflows by name.

---

## Home Assistant Tools (when configured)

Control and query smart home devices via the HA MCP integration.

---

## MCP Tools (via localhost:3700 proxy)

Vault, Homelab, Bench, Bearing, and HA via the MCP proxy. Use for:
- Reading vault notes (`vault_read_note`, `vault_search`)
- Lab infrastructure status (`homelab_*`)
- ESP32 and bench device management (`bench_*`)
- Model routing decisions (`bearing_*`)

---

## Conversation Memory Files

- `conversation-turns.json` — rolling recent turns
- `conversation-episodes.json` — compressed archived episodes
- `persona-profile.json` — evolving traits and preferences
- `memory-health.json` — janitor status and compaction heartbeat

---

## Tooling Principles

- Query live endpoints for current state — never guess.
- Use `run_shell` before claiming anything is true about the Mac Mini's state.
- On tool failure, report what failed and suggest the next corrective action.
- Tool calls add latency. Only invoke tools when the answer genuinely requires it.
- When a tool returns an error, try once with a corrected call before giving up.
