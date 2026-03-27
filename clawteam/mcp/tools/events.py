"""Event log MCP tools for interaction history queries."""

from __future__ import annotations

from clawteam.mcp.helpers import coerce_enum, team_mailbox, to_payload
from clawteam.team.models import MessageType


def events_get(
    team_name: str,
    limit: int = 100,
    msg_type: str | None = None,
    from_agent: str | None = None,
    to_agent: str | None = None,
) -> list[dict]:
    """Get interaction event log with optional filters."""
    events = team_mailbox(team_name).get_event_log(limit=limit * 2)
    filtered = []
    for event in events:
        if msg_type and event.type != coerce_enum(MessageType, msg_type):
            continue
        if from_agent and event.from_agent != from_agent:
            continue
        if to_agent and event.to != to_agent:
            continue
        filtered.append(event)
        if len(filtered) >= limit:
            break
    return to_payload(filtered)


def events_by_agent(
    team_name: str,
    agent_name: str,
    direction: str = "all",
    limit: int = 100,
) -> list[dict]:
    """Get all events involving a specific agent.

    direction: 'sent', 'received', or 'all'.
    """
    events = team_mailbox(team_name).get_event_log(limit=limit * 2)
    filtered = []
    for event in events:
        if direction == "sent" and event.from_agent != agent_name:
            continue
        if direction == "received" and event.to != agent_name:
            continue
        if event.from_agent != agent_name and event.to != agent_name:
            continue
        filtered.append(event)
        if len(filtered) >= limit:
            break
    return to_payload(filtered)


def events_conversation(
    team_name: str,
    request_id: str,
) -> list[dict]:
    """Get all events in a conversation (same request_id), chronological."""
    events = team_mailbox(team_name).get_event_log(limit=1000)
    conversation = [e for e in events if e.request_id == request_id]
    conversation.sort(key=lambda e: e.timestamp)
    return to_payload(conversation)


def events_summary(team_name: str) -> dict:
    """Get interaction statistics for a team."""
    events = team_mailbox(team_name).get_event_log(limit=10000)
    by_agent: dict[str, int] = {}
    by_type: dict[str, int] = {}
    pairs: dict[str, int] = {}
    for event in events:
        by_agent[event.from_agent] = by_agent.get(event.from_agent, 0) + 1
        by_type[event.type.value] = by_type.get(event.type.value, 0) + 1
        if event.to:
            pair = f"{event.from_agent}->{event.to}"
            pairs[pair] = pairs.get(pair, 0) + 1
    return to_payload({
        "total": len(events),
        "byAgent": by_agent,
        "byType": by_type,
        "topPairs": sorted(pairs.items(), key=lambda x: x[1], reverse=True)[:10],
    })
