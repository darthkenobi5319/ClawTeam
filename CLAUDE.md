# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClawTeam is a framework-agnostic multi-agent coordination CLI. AI agents self-organize into teams, divide work, and collaborate. Compatible with Claude Code, Codex, Cursor, and any CLI agent. Python 3.10+, MIT license.

## Build & Development Commands

```bash
# Install
pip install -e ".[dev]"       # Editable install with dev deps
pip install -e ".[p2p]"       # With ZeroMQ P2P transport

# Lint
ruff check clawteam/ tests/

# Test
python -m pytest tests/ -v --tb=short

# Run a single test file
python -m pytest tests/test_mailbox.py -v

# Run a single test by name
python -m pytest tests/test_mailbox.py::test_send_and_receive -v

# CLI entry points
clawteam              # Main CLI (Typer app)
clawteam-mcp          # MCP server (FastMCP, 25 tools)
python -m clawteam    # Alternative invocation

# Website (separate Node project)
npm run dev           # Vite dev server
npm run build         # Build to docs/ (GitHub Pages)
```

## Architecture

All core code lives in `clawteam/`. The CLI is a monolithic Typer app at `clawteam/cli/commands.py`.

### Pluggable Backend Pattern

Three subsystems use abstract base classes with factory functions:
- **Transport** (`clawteam/transport/`): `FileTransport` (default) and `P2PTransport` (ZeroMQ). Factory: `get_transport()`.
- **Task Store** (`clawteam/store/`): `FileTaskStore` on `BaseTaskStore`. Factory: `get_task_store()`.
- **Spawn Backend** (`clawteam/spawn/`): `TmuxBackend` and `SubprocessBackend` on `SpawnBackend`. Factory: `get_backend()`.

### File-Based State

All persistent state lives in `~/.clawteam/` (override with `CLAWTEAM_DATA_DIR`). Uses `atomic_write_text()` (mkstemp + os.replace) and advisory file locking (fcntl/msvcrt). Structure: `teams/`, `inboxes/`, `tasks/`, `snapshots/`, `workspaces/`, `events/`, `plans/`, `templates/`.

### Key Modules

| Module | Purpose |
|--------|---------|
| `cli/commands.py` | All CLI subcommands (config, team, inbox, task, cost, spawn, board, launch, etc.) |
| `team/` | Team coordination: manager, mailbox, tasks, plans, snapshots, lifecycle, costs |
| `store/` | Pluggable task storage (file-based, extensible) |
| `transport/` | Pluggable message transport (file-based or ZeroMQ P2P) |
| `spawn/` | Agent process spawning (tmux or subprocess) |
| `board/` | Monitoring dashboard: terminal renderer, HTTP server (stdlib SSE) |
| `mcp/` | MCP server wrapping core logic into 25 tools |
| `templates/` | TOML team archetypes with variable substitution (`{goal}`, `{team_name}`) |
| `workspace/` | Git worktree management per-agent (`clawteam/{team}/{agent}` branches) |
| `config.py` | Persistent config (`~/.clawteam/config.json`), env var hierarchy |
| `identity.py` | Agent identity, dual env var prefix (`CLAWTEAM_*` and `CLAUDE_CODE_*`) |
| `fileutil.py` | Atomic writes and cross-platform file locking |
| `paths.py` | Identifier validation and path traversal protection (`ensure_within_root`) |

### Important Patterns

- **Pydantic v2 throughout**: All data models (TeamMember, TeamConfig, TeamMessage, TaskItem, AgentProfile, etc.)
- **Config priority**: env var > config file > default. Dual-prefix: reads `CLAWTEAM_*` first, falls back to `CLAUDE_CODE_*`.
- **Template system**: TOML files define team archetypes with leader/agents/tasks and `{variable}` substitution.
- **Workspace isolation**: Each agent gets a git worktree on branch `clawteam/{team}/{agent}`.

## Testing

- Framework: pytest 9.x, 33 test files in `tests/`
- `conftest.py` auto-redirects `CLAWTEAM_DATA_DIR` and `HOME` to `tmp_path` for isolation
- CI runs on Python 3.10/3.11/3.12, ubuntu + macos

## Linting

Ruff with rules E, F, I, N, W (ignoring E501). Line length 100. Target Python 3.10.

## Environment Variables

- `CLAWTEAM_DATA_DIR` — Override data directory
- `CLAWTEAM_TRANSPORT` — Transport backend: `file` (default) or `p2p`
- `CLAWTEAM_TASK_STORE` — Task store backend: `file` (default)
- `CLAWTEAM_AGENT_NAME`, `CLAWTEAM_AGENT_ID`, `CLAWTEAM_TEAM_NAME` — Agent identity
- `CLAUDE_CODE_*` equivalents are read as fallback for all `CLAWTEAM_*` vars

## Website

Separate React + Vite project in `website/`, builds to `docs/` for GitHub Pages. Not part of the Python package.
