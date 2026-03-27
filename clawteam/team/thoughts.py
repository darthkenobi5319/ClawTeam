"""Thought and reasoning persistence for team agents.

Each thought is stored as a separate JSON file:
    ``{data_dir}/thoughts/{team}/thought-{id}.json``

Follows the same file-based patterns as CostStore and FileTaskStore.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from clawteam.fileutil import atomic_write_text, file_locked
from clawteam.paths import ensure_within_root, validate_identifier
from clawteam.team.models import get_data_dir

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ThoughtType(str, Enum):
    reasoning = "reasoning"
    decision = "decision"
    observation = "observation"
    hypothesis = "hypothesis"
    feedback = "feedback"
    critique = "critique"
    insight = "insight"
    question = "question"
    plan = "plan"
    summary = "summary"
    custom = "custom"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ThoughtEntry(BaseModel):
    """A single thought/reasoning entry from an agent."""

    model_config = {"populate_by_name": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_name: str = Field(alias="agentName")
    team_name: str = Field(alias="teamName")

    # Content
    thought_type: ThoughtType = Field(alias="thoughtType")
    category: str = ""
    content: str

    # Context links
    task_id: str | None = Field(default=None, alias="taskId")
    related_thought_id: str | None = Field(default=None, alias="relatedThoughtId")
    message_id: str | None = Field(default=None, alias="messageId")

    # Extensible structured data
    fields: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    created_at: str = Field(default_factory=_now_iso, alias="createdAt")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThoughtFilter(BaseModel):
    """Filter for querying thoughts."""

    model_config = {"populate_by_name": True}

    agent_name: str | None = None
    thought_type: ThoughtType | None = None
    category: str | None = None
    task_id: str | None = None
    related_thought_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class ThoughtSummary(BaseModel):
    """Aggregated summary of thoughts."""

    model_config = {"populate_by_name": True}

    total_thoughts: int = Field(alias="totalThoughts")
    by_agent: dict[str, int] = Field(alias="byAgent")
    by_type: dict[str, int] = Field(alias="byType")
    by_category: dict[str, int] = Field(alias="byCategory")
    time_range: tuple[str, str] | None = Field(default=None, alias="timeRange")


# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

def _thoughts_root(team_name: str) -> Path:
    d = ensure_within_root(
        get_data_dir() / "thoughts",
        validate_identifier(team_name, "team name"),
    )
    d.mkdir(parents=True, exist_ok=True)
    return d


def _thought_path(team_name: str, thought_id: str) -> Path:
    return _thoughts_root(team_name) / f"thought-{thought_id}.json"


def _summary_cache_path(team_name: str) -> Path:
    return _thoughts_root(team_name) / "summary.json"


# ---------------------------------------------------------------------------
# Summary cache (mirrors CostStore pattern)
# ---------------------------------------------------------------------------

class _SummaryCache(BaseModel):
    model_config = {"populate_by_name": True}

    team_name: str = Field(alias="teamName")
    total: int = 0
    by_agent: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    earliest: str = ""
    latest: str = ""


def _load_cache(team_name: str) -> _SummaryCache | None:
    path = _summary_cache_path(team_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cache = _SummaryCache.model_validate(data)
        return cache if cache.team_name == team_name else None
    except Exception:
        return None


def _write_cache(team_name: str, cache: _SummaryCache) -> None:
    atomic_write_text(
        _summary_cache_path(team_name),
        cache.model_dump_json(indent=2, by_alias=True),
    )


# ---------------------------------------------------------------------------
# ThoughtStore
# ---------------------------------------------------------------------------

class ThoughtStore:
    """File-based thought storage.

    Each thought is a JSON file at ``{data_dir}/thoughts/{team}/thought-{id}.json``.
    A summary cache is maintained for fast aggregate queries.
    """

    def __init__(self, team_name: str):
        self.team_name = team_name

    # -- Write ----------------------------------------------------------------

    def save_thought(
        self,
        agent_name: str,
        thought_type: ThoughtType,
        content: str,
        category: str = "",
        task_id: str | None = None,
        related_thought_id: str | None = None,
        message_id: str | None = None,
        fields: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ThoughtEntry:
        """Persist a new thought entry."""
        thought = ThoughtEntry(
            agent_name=agent_name,
            team_name=self.team_name,
            thought_type=thought_type,
            category=category,
            content=content,
            task_id=task_id,
            related_thought_id=related_thought_id,
            message_id=message_id,
            fields=fields or {},
            metadata=metadata or {},
        )
        atomic_write_text(
            _thought_path(self.team_name, thought.id),
            thought.model_dump_json(indent=2, by_alias=True),
        )
        # Best-effort cache update
        try:
            self._update_cache(thought)
        except Exception:
            pass
        return thought

    # -- Read -----------------------------------------------------------------

    def get_thought(self, thought_id: str) -> ThoughtEntry | None:
        """Retrieve a single thought by ID."""
        path = _thought_path(self.team_name, thought_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ThoughtEntry.model_validate(data)
        except Exception:
            return None

    def query_thoughts(
        self,
        filter_obj: ThoughtFilter | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ThoughtEntry]:
        """Query thoughts with optional filters, newest first."""
        root = _thoughts_root(self.team_name)
        thoughts: list[ThoughtEntry] = []
        for f in sorted(root.glob("thought-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                thought = ThoughtEntry.model_validate(data)
            except Exception:
                continue
            if filter_obj and not self._matches(thought, filter_obj):
                continue
            thoughts.append(thought)
        thoughts.sort(key=lambda t: t.created_at, reverse=True)
        return thoughts[offset: offset + limit]

    def get_agent_thoughts(
        self,
        agent_name: str,
        limit: int = 100,
        thought_type: ThoughtType | None = None,
    ) -> list[ThoughtEntry]:
        """Get all thoughts from a specific agent."""
        return self.query_thoughts(
            ThoughtFilter(agent_name=agent_name, thought_type=thought_type),
            limit=limit,
        )

    def get_task_thoughts(self, task_id: str, limit: int = 100) -> list[ThoughtEntry]:
        """Get all thoughts related to a specific task."""
        return self.query_thoughts(ThoughtFilter(task_id=task_id), limit=limit)

    def get_thought_chain(self, root_id: str, max_depth: int = 10) -> list[ThoughtEntry]:
        """Follow related_thought_id links to build a thought chain."""
        chain: list[ThoughtEntry] = []
        current_id = root_id
        for _ in range(max_depth):
            thought = self.get_thought(current_id)
            if thought is None:
                break
            chain.append(thought)
            children = self.query_thoughts(
                ThoughtFilter(related_thought_id=current_id), limit=1
            )
            if not children:
                break
            current_id = children[0].id
        return chain

    def search_thoughts(self, query: str, limit: int = 100) -> list[ThoughtEntry]:
        """Full-text search through thought content and fields."""
        root = _thoughts_root(self.team_name)
        query_lower = query.lower()
        results: list[ThoughtEntry] = []
        for f in sorted(root.glob("thought-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                thought = ThoughtEntry.model_validate(data)
            except Exception:
                continue
            if query_lower in thought.content.lower():
                results.append(thought)
                continue
            for value in thought.fields.values():
                if query_lower in str(value).lower():
                    results.append(thought)
                    break
        results.sort(key=lambda t: t.created_at, reverse=True)
        return results[:limit]

    def get_summary(self) -> ThoughtSummary:
        """Aggregated summary (uses cache when available)."""
        cache = _load_cache(self.team_name)
        if cache is None:
            cache = self._rebuild_cache()
        time_range = None
        if cache.earliest and cache.latest:
            time_range = (cache.earliest, cache.latest)
        return ThoughtSummary(
            total_thoughts=cache.total,
            by_agent=cache.by_agent,
            by_type=cache.by_type,
            by_category=cache.by_category,
            time_range=time_range,
        )

    # -- Cache management ----------------------------------------------------

    def _update_cache(self, thought: ThoughtEntry) -> None:
        cache_path = _summary_cache_path(self.team_name)
        with file_locked(cache_path):
            cache = _load_cache(self.team_name) or _SummaryCache(
                team_name=self.team_name
            )
            cache.total += 1
            cache.by_agent[thought.agent_name] = (
                cache.by_agent.get(thought.agent_name, 0) + 1
            )
            cache.by_type[thought.thought_type.value] = (
                cache.by_type.get(thought.thought_type.value, 0) + 1
            )
            if thought.category:
                cache.by_category[thought.category] = (
                    cache.by_category.get(thought.category, 0) + 1
                )
            if not cache.earliest or thought.created_at < cache.earliest:
                cache.earliest = thought.created_at
            if not cache.latest or thought.created_at > cache.latest:
                cache.latest = thought.created_at
            _write_cache(self.team_name, cache)

    def _rebuild_cache(self) -> _SummaryCache:
        """Full scan to rebuild the summary cache."""
        root = _thoughts_root(self.team_name)
        cache = _SummaryCache(team_name=self.team_name)
        for f in sorted(root.glob("thought-*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                thought = ThoughtEntry.model_validate(data)
            except Exception:
                continue
            cache.total += 1
            cache.by_agent[thought.agent_name] = (
                cache.by_agent.get(thought.agent_name, 0) + 1
            )
            cache.by_type[thought.thought_type.value] = (
                cache.by_type.get(thought.thought_type.value, 0) + 1
            )
            if thought.category:
                cache.by_category[thought.category] = (
                    cache.by_category.get(thought.category, 0) + 1
                )
            if not cache.earliest or thought.created_at < cache.earliest:
                cache.earliest = thought.created_at
            if not cache.latest or thought.created_at > cache.latest:
                cache.latest = thought.created_at
        _write_cache(self.team_name, cache)
        return cache

    # -- Filter ---------------------------------------------------------------

    @staticmethod
    def _matches(thought: ThoughtEntry, f: ThoughtFilter) -> bool:
        if f.agent_name and thought.agent_name != f.agent_name:
            return False
        if f.thought_type and thought.thought_type != f.thought_type:
            return False
        if f.category and thought.category != f.category:
            return False
        if f.task_id and thought.task_id != f.task_id:
            return False
        if f.related_thought_id and thought.related_thought_id != f.related_thought_id:
            return False
        if f.start_time and thought.created_at < f.start_time:
            return False
        if f.end_time and thought.created_at > f.end_time:
            return False
        for key, value in f.fields.items():
            if thought.fields.get(key) != value:
                return False
        return True
