# Copyright (c) Microsoft. All rights reserved.

"""AgentFrameworkAgent wrapper for AG-UI protocol - Clean Architecture."""

from collections.abc import AsyncGenerator
from typing import Any, cast

from ag_ui.core import BaseEvent
from agent_framework import AgentProtocol

from ._confirmation_strategies import ConfirmationStrategy, DefaultConfirmationStrategy
from ._orchestrators import (
    DefaultOrchestrator,
    ExecutionContext,
    HumanInTheLoopOrchestrator,
    Orchestrator,
)


class AgentConfig:
    """Configuration for agent wrapper."""

    def __init__(
        self,
        state_schema: Any | None = None,
        predict_state_config: dict[str, dict[str, str]] | None = None,
        require_confirmation: bool = True,
    ):
        """Initialize agent configuration.

        Args:
            state_schema: Optional state schema for state management; accepts dict or Pydantic model/class
            predict_state_config: Configuration for predictive state updates
            require_confirmation: Whether predictive updates require confirmation
        """
        self.state_schema = self._normalize_state_schema(state_schema)
        self.predict_state_config = predict_state_config or {}
        self.require_confirmation = require_confirmation

    @staticmethod
    def _normalize_state_schema(state_schema: Any | None) -> dict[str, Any]:
        """Accept dict or Pydantic model/class and return a properties dict."""
        if state_schema is None:
            return {}

        if isinstance(state_schema, dict):
            return cast(dict[str, Any], state_schema)

        base_model_type: type[Any] | None
        try:
            from pydantic import BaseModel as ImportedBaseModel

            base_model_type = ImportedBaseModel
        except Exception:  # pragma: no cover
            base_model_type = None

        if base_model_type is not None and isinstance(state_schema, base_model_type):
            schema_dict = state_schema.__class__.model_json_schema()
            return schema_dict.get("properties", {}) or {}

        if base_model_type is not None and isinstance(state_schema, type) and issubclass(state_schema, base_model_type):
            schema_dict = state_schema.model_json_schema()
            return schema_dict.get("properties", {}) or {}

        return {}


class AgentFrameworkAgent:
    """Wraps Agent Framework agents for AG-UI protocol compatibility.

    Translates between Agent Framework's AgentProtocol and AG-UI's event-based
    protocol. Uses orchestrators to handle different execution flows (standard
    execution, human-in-the-loop, etc.). Orchestrators are checked in order;
    the first matching orchestrator handles the request.

    Supports predictive state updates for agentic generative UI, with optional
    confirmation requirements configurable per use case.
    """

    def __init__(
        self,
        agent: AgentProtocol,
        name: str | None = None,
        description: str | None = None,
        state_schema: Any | None = None,
        predict_state_config: dict[str, dict[str, str]] | None = None,
        require_confirmation: bool = True,
        orchestrators: list[Orchestrator] | None = None,
        confirmation_strategy: ConfirmationStrategy | None = None,
    ):
        """Initialize the AG-UI compatible agent wrapper.

        Args:
            agent: The Agent Framework agent to wrap
            name: Optional name for the agent
            description: Optional description
            state_schema: Optional state schema for state management; accepts dict or Pydantic model/class
            predict_state_config: Configuration for predictive state updates.
                Format: {"state_key": {"tool": "tool_name", "tool_argument": "arg_name"}}
            require_confirmation: Whether predictive updates require confirmation.
                Set to False for agentic generative UI that updates automatically.
            orchestrators: Custom orchestrators (auto-configured if None).
                Orchestrators are checked in order; first match handles the request.
            confirmation_strategy: Strategy for generating confirmation messages.
                Defaults to DefaultConfirmationStrategy if None.
        """
        self.agent = agent
        self.name = name or getattr(agent, "name", "agent")
        self.description = description or getattr(agent, "description", "")

        self.config = AgentConfig(
            state_schema=state_schema,
            predict_state_config=predict_state_config,
            require_confirmation=require_confirmation,
        )

        # Configure orchestrators
        if orchestrators is None:
            self.orchestrators = self._default_orchestrators()
        else:
            self.orchestrators = orchestrators

        # Configure confirmation strategy
        if confirmation_strategy is None:
            self.confirmation_strategy: ConfirmationStrategy = DefaultConfirmationStrategy()
        else:
            self.confirmation_strategy = confirmation_strategy

    def _default_orchestrators(self) -> list[Orchestrator]:
        """Create default orchestrator chain.

        Returns:
            List of orchestrators in priority order. First matching orchestrator
            handles the request, so order matters.
        """
        return [
            HumanInTheLoopOrchestrator(),  # Handle tool approval responses
            # Add more specialized orchestrators here as needed
            DefaultOrchestrator(),  # Fallback: standard agent execution
        ]

    async def run_agent(
        self,
        input_data: dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Run the agent and yield AG-UI events.

        This is the ONLY public method - much simpler than the original 376-line
        implementation. All orchestration logic has been extracted into dedicated
        Orchestrator classes.

        The method creates an ExecutionContext with all needed data, then finds
        the first orchestrator that can handle the request and delegates to it.

        Args:
            input_data: The AG-UI run input containing messages, state, etc.

        Yields:
            AG-UI events

        Raises:
            RuntimeError: If no orchestrator matches (should never happen if
                DefaultOrchestrator is last in the chain)
        """
        # Create execution context with all needed data
        context = ExecutionContext(
            input_data=input_data,
            agent=self.agent,
            config=self.config,
            confirmation_strategy=self.confirmation_strategy,
        )

        # Find matching orchestrator and execute
        for orchestrator in self.orchestrators:
            if orchestrator.can_handle(context):
                async for event in orchestrator.run(context):
                    yield event
                return

        # Should never reach here if DefaultOrchestrator is last
        raise RuntimeError("No orchestrator matched - check configuration")


__all__ = [
    "AgentFrameworkAgent",
    "AgentConfig",
]
