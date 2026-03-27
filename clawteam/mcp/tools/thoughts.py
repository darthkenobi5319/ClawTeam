"""Thought and reasoning MCP tools."""

from __future__ import annotations

from clawteam.mcp.helpers import coerce_enum, fail, to_payload
from clawteam.team.thoughts import ThoughtFilter, ThoughtStore, ThoughtType


def thought_save(
    team_name: str,
    agent_name: str,
    thought_type: str,
    content: str,
    category: str = "",
    task_id: str | None = None,
    related_thought_id: str | None = None,
    message_id: str | None = None,
    fields: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Save a thought/reasoning entry from an agent."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    tt = coerce_enum(ThoughtType, thought_type)
    if not tt:
        fail(f"Invalid thought_type: {thought_type}")
    thought = ThoughtStore(team_name).save_thought(
        agent_name=agent_name,
        thought_type=tt,
        content=content,
        category=category,
        task_id=task_id,
        related_thought_id=related_thought_id,
        message_id=message_id,
        fields=fields,
        metadata=metadata,
    )
    return to_payload(thought)


def thought_get(team_name: str, thought_id: str) -> dict:
    """Get a single thought by ID."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    thought = ThoughtStore(team_name).get_thought(thought_id)
    if thought is None:
        fail(f"Thought '{thought_id}' not found")
    return to_payload(thought)


def thought_query(
    team_name: str,
    agent_name: str | None = None,
    thought_type: str | None = None,
    category: str | None = None,
    task_id: str | None = None,
    related_thought_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    fields: dict | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Query thoughts with optional filters."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    f = ThoughtFilter(
        agent_name=agent_name,
        thought_type=coerce_enum(ThoughtType, thought_type),
        category=category,
        task_id=task_id,
        related_thought_id=related_thought_id,
        start_time=start_time,
        end_time=end_time,
        fields=fields or {},
    )
    return to_payload(ThoughtStore(team_name).query_thoughts(f, limit=limit, offset=offset))


def thought_agent(
    team_name: str,
    agent_name: str,
    thought_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get all thoughts from a specific agent."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    return to_payload(
        ThoughtStore(team_name).get_agent_thoughts(
            agent_name=agent_name,
            limit=limit,
            thought_type=coerce_enum(ThoughtType, thought_type),
        )
    )


def thought_task(
    team_name: str,
    task_id: str,
    limit: int = 100,
) -> list[dict]:
    """Get all thoughts related to a specific task."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    return to_payload(ThoughtStore(team_name).get_task_thoughts(task_id, limit=limit))


def thought_chain(
    team_name: str,
    root_thought_id: str,
    max_depth: int = 10,
) -> list[dict]:
    """Get a chain of related thoughts (parent-child relationships)."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    return to_payload(
        ThoughtStore(team_name).get_thought_chain(root_thought_id, max_depth=max_depth)
    )


def thought_search(
    team_name: str,
    query: str,
    limit: int = 100,
) -> list[dict]:
    """Full-text search through thought content."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    return to_payload(ThoughtStore(team_name).search_thoughts(query, limit=limit))


def thought_summary(team_name: str) -> dict:
    """Get aggregated summary of all thoughts for a team."""
    from clawteam.mcp.helpers import require_team

    require_team(team_name)
    return to_payload(ThoughtStore(team_name).get_summary())
