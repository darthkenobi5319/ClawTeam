"""Interaction pattern manager for coordinating agent communication.

Validates messages against template-defined interaction rules and
provides pattern-step tracking for multi-step workflows.
"""

from __future__ import annotations

from typing import Any

from clawteam.team.mailbox import MailboxManager
from clawteam.team.models import MessageType
from clawteam.templates import AgentInteractionDef as AgentInteractionDefModel
from clawteam.templates import InteractionPatternDef, load_template


class InteractionError(Exception):
    """Raised when a message violates the team's interaction rules."""


class InteractionManager:
    """Validates and manages agent communication patterns.

    Loads rules from a team's template (if any) and enforces them
    on send operations.
    """

    def __init__(
        self,
        team_name: str,
        mailbox: MailboxManager,
        template_name: str | None = None,
    ):
        self.team_name = team_name
        self.mailbox = mailbox
        self.template_name = template_name
        self._template = None

        if template_name:
            try:
                self._template = load_template(template_name)
            except FileNotFoundError:
                pass

    # -- Validation -----------------------------------------------------------

    def validate_message(
        self,
        from_agent: str,
        to_agent: str,
        msg_type: MessageType,
    ) -> tuple[bool, str | None]:
        """Check whether a message conforms to the template's rules.

        Returns (allowed, reason).  When no template is loaded everything
        is allowed.
        """
        if not self._template or not self._template.interaction:
            return True, None

        # Check allowed message types
        allowed = self._template.interaction.allowed_message_types
        if msg_type.value not in allowed:
            return False, (
                f"Message type '{msg_type.value}' not in allowed types: {allowed}"
            )

        # Check send permission
        from_cfg = self._get_agent_interaction(from_agent)
        if from_cfg:
            if "*" not in from_cfg.can_send_to and to_agent not in from_cfg.can_send_to:
                return False, (
                    f"Agent '{from_agent}' is not allowed to send to '{to_agent}'"
                )

        # Check receive permission
        to_cfg = self._get_agent_interaction(to_agent)
        if to_cfg:
            if "*" not in to_cfg.can_receive_from and from_agent not in to_cfg.can_receive_from:
                return False, (
                    f"Agent '{to_agent}' is not allowed to receive from '{from_agent}'"
                )

        return True, None

    # -- Validated send -------------------------------------------------------

    def send_validated(
        self,
        from_agent: str,
        to_agent: str,
        msg_type: MessageType,
        content: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send a message after validation. Raises InteractionError on rejection."""
        allowed, reason = self.validate_message(from_agent, to_agent, msg_type)
        if not allowed:
            raise InteractionError(f"Message rejected: {reason}")
        return self.mailbox.send(
            from_agent=from_agent,
            to=to_agent,
            content=content,
            msg_type=msg_type,
            **kwargs,
        )

    # -- Pattern queries ------------------------------------------------------

    def get_pattern(self, pattern_name: str) -> InteractionPatternDef | None:
        """Look up an interaction pattern by name."""
        if not self._template:
            return None
        for p in self._template.interaction_patterns:
            if p.name == pattern_name:
                return p
        return None

    def get_next_step(
        self,
        pattern_name: str,
        current_agent: str,
    ) -> dict[str, Any] | None:
        """Return the next step in an interaction pattern, or None."""
        pattern = self.get_pattern(pattern_name)
        if not pattern:
            return None

        current_idx = -1
        for i, step in enumerate(pattern.steps):
            if step.get("agent") == current_agent:
                current_idx = i
                break

        if current_idx == -1:
            return None

        if current_idx + 1 < len(pattern.steps):
            return {
                "nextStep": pattern.steps[current_idx + 1],
                "stepIndex": current_idx + 1,
                "totalSteps": len(pattern.steps),
                "complete": False,
            }
        return {"complete": True}

    def list_patterns(self) -> list[InteractionPatternDef]:
        """Return all interaction patterns defined in the template."""
        return list(self._template.interaction_patterns) if self._template else []

    # -- Thought policy -------------------------------------------------------

    def get_thought_policy(self, agent_name: str) -> str:
        """Get the thought saving policy for an agent.

        Falls back to team default, then to 'on_task_end'.
        """
        default = "on_task_end"
        if not self._template:
            return default

        if self._template.interaction:
            default = self._template.interaction.thought_policy

        cfg = self._get_agent_interaction(agent_name)
        if cfg and cfg.thought_policy:
            return cfg.thought_policy

        return default

    # -- Helpers --------------------------------------------------------------

    def _get_agent_interaction(self, agent_name: str) -> AgentInteractionDefModel | None:
        """Get the interaction config for an agent, or None."""
        if not self._template:
            return None
        if self._template.leader.name == agent_name:
            return self._template.leader.interaction
        for agent in self._template.agents:
            if agent.name == agent_name:
                return agent.interaction
        return None
