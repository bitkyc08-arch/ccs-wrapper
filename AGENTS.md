# AGENTS.md — CCS Wrapper

## Overview

This is a proxy wrapper (`thinking-wrapper.py`) for CCS (Claude Code Switch, `:8317`).
It runs on `:8318` and adds model aliasing, thinking parameter injection, and Codex effort routing.

## Architecture

```
Client → :8318 (this wrapper) → :8317 (CCS) → Provider (Antigravity/Codex/Copilot)
```

Two inbound endpoints:
- `/v1/messages` — Anthropic Messages format (Claude Code CLI)
- `/v1/chat/completions` — OpenAI format (VS Code Copilot BYOK)

## Key Behavior

### Model Aliasing (`MODEL_ALIASES` dict)

Before routing, the wrapper remaps model names:

```python
MODEL_ALIASES = {
    "claude-haiku-4-5-20251001":  "claude-sonnet-4-6",       # Haiku slot upgrade
    "claude-haiku-4-5":           "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929": "gpt-5.3-codex-xhigh",     # Default Sonnet → Codex
    "claude-sonnet-4-5":          "gpt-5.3-codex-xhigh",
    "claude-sonnet-4":            "gpt-5.3-codex-xhigh",
}
```

This means Claude Code's default Sonnet slot silently routes to Codex xhigh.

### 3-Route Logic (both endpoints)

1. **Thinking** (`claude-*-thinking`): Injects `thinking: {type: "adaptive", effort: "max"}`, caps `max_tokens` to 16K
2. **Codex Effort** (`*-xhigh`, `*-high`, etc.): Parses suffix → `reasoning_effort` param → routes to `/api/provider/codex/`
3. **Passthrough**: Everything else forwards to CCS unchanged

### Sub-path Proxy

`/v1/messages/{path}` (e.g. `count_tokens`) is proxied to CCS directly.

## File Structure

```
ccs-wrapper/
├── thinking-wrapper.py   ← Single-file proxy (FastAPI + httpx + uvicorn)
├── requirements.txt      ← fastapi, uvicorn, httpx
├── README.md             ← Human documentation
└── AGENTS.md             ← This file
```

## Dependencies

- CCS must be running on `localhost:8317` (configured in `CCS_BASE` constant)
- Codex OAuth must be connected in CCS for effort models
- Python packages: `fastapi`, `uvicorn`, `httpx`

## Running

```bash
# Direct
python3 thinking-wrapper.py --port 8318

# Background (macOS launchd)
launchctl start com.ccs.thinking-wrapper
```

## Modifying

- **Add model aliases**: Edit `MODEL_ALIASES` dict at top of file
- **Change thinking effort**: Edit `THINKING_MODELS` dict (effort: max/high/medium/low)
- **Change CCS backend**: Edit `CCS_BASE` constant
- **After changes**: Restart via `launchctl stop com.ccs.thinking-wrapper && launchctl start com.ccs.thinking-wrapper`

## Logs

- stdout: Log path configured in LaunchAgent plist (default: `~/.ccs/cliproxy/logs/wrapper-stdout.log`)
- Key log patterns:
  - `📨 [messages] model_a → model_b` = alias remap
  - `🔧 [messages] Codex effort: base + level` = effort routing
  - `🔍 [messages] Thinking: model, effort=X` = thinking injection
  - `💰 Usage: in=X out=Y` = token usage
