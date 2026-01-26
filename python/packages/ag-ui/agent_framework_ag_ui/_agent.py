# Copyright (c) Microsoft. All rights reserved.

"""AgentFrameworkAgent wrapper for AG-UI protocol."""

from collections.abc import AsyncGenerator
from typing import Any, cast

from ag_ui.core import BaseEvent
from agent_framework import AgentProtocol

from ._run import run_agent_stream


class AgentConfig:
    """Configuration for agent wrapper."""

    def __init__(
        self,
        state_schema: Any | None = None,
        predict_state_config: dict[str, dict[str, str]] | None = None,
        use_service_thread: bool = False,
        require_confirmation: bool = True,
    ):
        """Initialize agent configuration.

        Args:
            state_schema: Optional state schema for state management; accepts dict or Pydantic model/class
            predict_state_config: Configuration for predictive state updates
            use_service_thread: Whether the agent thread is service-managed
            require_confirmation: Whether predictive updates require user confirmation before applying
        """
        self.state_schema = self._normalize_state_schema(state_schema)
        self.predict_state_config = predict_state_config or {}
        self.use_service_thread = use_service_thread
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
            schema_dict = state_schema.__class__.model_json_schema()  # type: ignore[union-attr]
            return schema_dict.get("properties", {}) or {}

        if base_model_type is not None and isinstance(state_schema, type) and issubclass(state_schema, base_model_type):
            schema_dict = state_schema.model_json_schema()  # type: ignore[union-attr]
            return schema_dict.get("properties", {}) or {}  # type: ignore

        return {}


class AgentFrameworkAgent:
    """Wraps Agent Framework agents for AG-UI protocol compatibility.

    Translates between Agent Framework's AgentProtocol and AG-UI's event-based
    protocol. Follows a simple linear flow: RunStarted -> content events -> RunFinished.
    """

    def __init__(
        self,
        agent: AgentProtocol,
        name: str | None = None,
        description: str | None = None,
        state_schema: Any | None = None,
        predict_state_config: dict[str, dict[str, str]] | None = None,
        require_confirmation: bool = True,
        use_service_thread: bool = False,
    ):
        """Initialize the AG-UI compatible agent wrapper.

        Args:
            agent: The Agent Framework agent to wrap
            name: Optional name for the agent
            description: Optional description
            state_schema: Optional state schema for state management; accepts dict or Pydantic model/class
            predict_state_config: Configuration for predictive state updates
            require_confirmation: Whether predictive updates require user confirmation before applying
            use_service_thread: Whether the agent thread is service-managed
        """
        self.agent = agent
        self.name = name or getattr(agent, "name", "agent")
        self.description = description or getattr(agent, "description", "")

        self.config = AgentConfig(
            state_schema=state_schema,
            predict_state_config=predict_state_config,
            use_service_thread=use_service_thread,
            require_confirmation=require_confirmation,
        )

    async def run_agent(
        self,
        input_data: dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """Run the agent and yield AG-UI events.

        Args:
            input_data: The AG-UI run input containing messages, state, etc.

        Yields:
            AG-UI events
        """
        async for event in run_agent_stream(input_data, self.agent, self.config):
            yield event
