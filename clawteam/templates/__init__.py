"""Team template loader — load TOML templates for one-command team launch."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# TOML support: built-in on 3.11+, conditional dependency on 3.10
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[import-not-found,no-redef]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AgentInteractionDef(BaseModel):
    """Per-agent interaction configuration (optional in templates)."""

    thought_policy: str | None = None  # never / on_task_start / on_task_end / on_message
    can_send_to: list[str] = Field(default_factory=lambda: ["*"])
    can_receive_from: list[str] = Field(default_factory=lambda: ["*"])


class AgentDef(BaseModel):
    name: str
    type: str = "general-purpose"
    task: str = ""
    command: list[str] | None = None
    interaction: AgentInteractionDef | None = None


class TaskDef(BaseModel):
    subject: str
    description: str = ""
    owner: str = ""


class InteractionConfigDef(BaseModel):
    """Team-level interaction configuration."""

    protocol: str = "peer_to_peer"  # broadcast / hierarchical / peer_to_peer / consensus
    thought_policy: str = "on_task_end"
    allowed_message_types: list[str] = Field(
        default_factory=lambda: ["message"]
    )


class InteractionPatternDef(BaseModel):
    """A named interaction flow between specific agents."""

    name: str
    participants: list[str]
    flow: str = "sequential"  # sequential / parallel / hybrid
    steps: list[dict[str, Any]] = Field(default_factory=list)
    required_messages: list[str] = Field(default_factory=list)
    optional: bool = False


class ThoughtCategoryDef(BaseModel):
    """A category for organizing thoughts in this template."""

    name: str
    agent_type: str = "*"
    description: str = ""
    fields: list[str] = Field(default_factory=list)


class TemplateDef(BaseModel):
    name: str
    description: str = ""
    command: list[str] = ["claude"]
    backend: str = "tmux"
    leader: AgentDef
    agents: list[AgentDef] = []
    tasks: list[TaskDef] = []
    # Extended fields (all optional for backward compatibility)
    interaction: InteractionConfigDef | None = None
    interaction_patterns: list[InteractionPatternDef] = Field(default_factory=list)
    thought_categories: list[ThoughtCategoryDef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BUILTIN_DIR = Path(__file__).parent
_USER_DIR = Path.home() / ".clawteam" / "templates"


# ---------------------------------------------------------------------------
# Variable substitution helper
# ---------------------------------------------------------------------------

class _SafeDict(dict):
    """dict subclass that keeps unknown {placeholders} intact."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_task(task: str, **variables: str) -> str:
    """Replace {goal}, {team_name}, {agent_name} etc. in task text."""
    return task.format_map(_SafeDict(**variables))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _parse_interaction(raw: dict | None) -> InteractionConfigDef | None:
    if not raw:
        return None
    return InteractionConfigDef(**raw)


def _parse_interaction_def(raw: dict | None) -> AgentInteractionDef | None:
    if not raw:
        return None
    return AgentInteractionDef(**raw)


def _parse_toml(path: Path) -> TemplateDef:
    """Parse a TOML template file into a TemplateDef."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    tmpl = raw.get("template", {})

    # Parse leader (may include interaction config)
    leader_data = tmpl.get("leader", {})
    interaction_data = leader_data.pop("interaction", None)
    leader = AgentDef(**leader_data)
    leader.interaction = _parse_interaction_def(interaction_data)

    # Parse agents (each may include interaction config)
    agents: list[AgentDef] = []
    for a in tmpl.get("agents", []):
        agent_data = a.copy()
        interaction_data = agent_data.pop("interaction", None)
        agent = AgentDef(**agent_data)
        agent.interaction = _parse_interaction_def(interaction_data)
        agents.append(agent)

    # Parse tasks
    tasks = [TaskDef(**t) for t in tmpl.get("tasks", [])]

    # Parse extended sections (optional, backward compatible)
    interaction = _parse_interaction(tmpl.get("interaction"))

    interaction_patterns = []
    for p in tmpl.get("interaction_patterns", []):
        interaction_patterns.append(InteractionPatternDef(**p))

    thought_categories = []
    for c in tmpl.get("thought_categories", []):
        thought_categories.append(ThoughtCategoryDef(**c))

    return TemplateDef(
        name=tmpl.get("name", path.stem),
        description=tmpl.get("description", ""),
        command=tmpl.get("command", ["claude"]),
        backend=tmpl.get("backend", "tmux"),
        leader=leader,
        agents=agents,
        tasks=tasks,
        interaction=interaction,
        interaction_patterns=interaction_patterns,
        thought_categories=thought_categories,
    )


def load_template(name: str) -> TemplateDef:
    """Load a template by name.

    Search order: user templates (~/.clawteam/templates/) first,
    then built-in templates (clawteam/templates/).
    """
    filename = f"{name}.toml"

    # User templates take priority
    user_path = _USER_DIR / filename
    if user_path.is_file():
        return _parse_toml(user_path)

    # Built-in templates
    builtin_path = _BUILTIN_DIR / filename
    if builtin_path.is_file():
        return _parse_toml(builtin_path)

    raise FileNotFoundError(
        f"Template '{name}' not found. "
        f"Searched: {_USER_DIR}, {_BUILTIN_DIR}"
    )


def list_templates() -> list[dict[str, str]]:
    """List all available templates (user + builtin, user overrides builtin)."""
    seen: dict[str, dict[str, str]] = {}

    # Built-in templates first (can be overridden)
    if _BUILTIN_DIR.is_dir():
        for p in sorted(_BUILTIN_DIR.glob("*.toml")):
            try:
                tmpl = _parse_toml(p)
                seen[tmpl.name] = {
                    "name": tmpl.name,
                    "description": tmpl.description,
                    "source": "builtin",
                }
            except Exception:
                continue

    # User templates override
    if _USER_DIR.is_dir():
        for p in sorted(_USER_DIR.glob("*.toml")):
            try:
                tmpl = _parse_toml(p)
                seen[tmpl.name] = {
                    "name": tmpl.name,
                    "description": tmpl.description,
                    "source": "user",
                }
            except Exception:
                continue

    return list(seen.values())
