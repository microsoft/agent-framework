# Copyright (c) Microsoft. All rights reserved.

"""Orchestrators for multi-turn agent flows."""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from ag_ui.core import (
    BaseEvent,
    RunErrorEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from agent_framework import AgentProtocol, AgentThread, ChatAgent, TextContent

from ._utils import convert_agui_tools_to_agent_framework, generate_event_id

if TYPE_CHECKING:
    from ._agent import AgentConfig
    from ._confirmation_strategies import ConfirmationStrategy


logger = logging.getLogger(__name__)


class ExecutionContext:
    """Shared context for orchestrators."""

    def __init__(
        self,
        input_data: dict[str, Any],
        agent: AgentProtocol,
        config: "AgentConfig",  # noqa: F821
        confirmation_strategy: "ConfirmationStrategy | None" = None,  # noqa: F821
    ):
        """Initialize execution context.

        Args:
            input_data: AG-UI run input containing messages, state, etc.
            agent: The Agent Framework agent to execute
            config: Agent configuration
            confirmation_strategy: Strategy for generating confirmation messages
        """
        self.input_data = input_data
        self.agent = agent
        self.config = config
        self.confirmation_strategy = confirmation_strategy

        # Lazy-loaded properties
        self._messages = None
        self._last_message = None
        self._run_id: str | None = None
        self._thread_id: str | None = None

    @property
    def messages(self):
        """Get converted Agent Framework messages (lazy loaded)."""
        if self._messages is None:
            from ._message_adapters import agui_messages_to_agent_framework

            raw = self.input_data.get("messages", [])
            self._messages = agui_messages_to_agent_framework(raw)
        return self._messages

    @property
    def last_message(self):
        """Get the last message in the conversation (lazy loaded)."""
        if self._last_message is None and self.messages:
            self._last_message = self.messages[-1]
        return self._last_message

    @property
    def run_id(self) -> str:
        """Get or generate run ID."""
        if self._run_id is None:
            self._run_id = self.input_data.get("run_id") or str(uuid.uuid4())
        # This should never be None after the if block above, but satisfy type checkers
        if self._run_id is None:  # pragma: no cover
            raise RuntimeError("Failed to initialize run_id")
        return self._run_id

    @property
    def thread_id(self) -> str:
        """Get or generate thread ID."""
        if self._thread_id is None:
            self._thread_id = self.input_data.get("thread_id") or str(uuid.uuid4())
        # This should never be None after the if block above, but satisfy type checkers
        if self._thread_id is None:  # pragma: no cover
            raise RuntimeError("Failed to initialize thread_id")
        return self._thread_id


class Orchestrator(ABC):
    """Base orchestrator for agent execution flows."""

    @abstractmethod
    def can_handle(self, context: ExecutionContext) -> bool:
        """Determine if this orchestrator handles the current request.

        Args:
            context: Execution context with input data and agent

        Returns:
            True if this orchestrator should handle the request
        """
        ...

    @abstractmethod
    async def run(
        self,
        context: ExecutionContext,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute the orchestration and yield events.

        Args:
            context: Execution context

        Yields:
            AG-UI events
        """
        # This is never executed - just satisfies mypy's requirement for async generators
        if False:  # pragma: no cover
            yield
        raise NotImplementedError


class HumanInTheLoopOrchestrator(Orchestrator):
    """Handles tool approval responses from user."""

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if last message is a tool approval response.

        Args:
            context: Execution context

        Returns:
            True if last message is a tool result
        """
        msg = context.last_message
        if not msg:
            return False

        return bool(msg.additional_properties.get("is_tool_result", False))

    async def run(
        self,
        context: ExecutionContext,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Process approval response and generate confirmation events.

        This implementation is extracted from the legacy _agent.py lines 144-244.

        Args:
            context: Execution context

        Yields:
            AG-UI events (TextMessage, RunFinished)
        """
        from ._confirmation_strategies import DefaultConfirmationStrategy
        from ._events import AgentFrameworkEventBridge

        logger.info("=== TOOL RESULT DETECTED (HumanInTheLoopOrchestrator) ===")

        # Create event bridge for run events
        event_bridge = AgentFrameworkEventBridge(
            run_id=context.run_id,
            thread_id=context.thread_id,
        )

        # CRITICAL: Every AG-UI run must start with RunStartedEvent
        yield event_bridge.create_run_started_event()

        # Get confirmation strategy (use default if none provided)
        strategy = context.confirmation_strategy
        if strategy is None:
            strategy = DefaultConfirmationStrategy()

        # Parse the tool result content
        tool_content_text = ""
        last_message = context.last_message
        if last_message:
            for content in last_message.contents:
                if isinstance(content, TextContent):
                    tool_content_text = content.text
                    break

        try:
            tool_result = json.loads(tool_content_text)
            accepted = tool_result.get("accepted", False)
            steps = tool_result.get("steps", [])

            logger.info(f"  Accepted: {accepted}")
            logger.info(f"  Steps count: {len(steps)}")

            # Emit a text message confirming execution
            message_id = generate_event_id()

            yield TextMessageStartEvent(message_id=message_id, role="assistant")

            # Check if this is confirm_changes (no steps) or function approval (has steps)
            if not steps:
                # This is confirm_changes for predictive state updates
                if accepted:
                    confirmation_message = strategy.on_state_confirmed()
                else:
                    confirmation_message = strategy.on_state_rejected()
            elif accepted:
                # User approved - execute the enabled steps (function approval flow)
                confirmation_message = strategy.on_approval_accepted(steps)
            else:
                # User rejected
                confirmation_message = strategy.on_approval_rejected(steps)

            yield TextMessageContentEvent(
                message_id=message_id,
                delta=confirmation_message,
            )

            yield TextMessageEndEvent(message_id=message_id)

            # Emit run finished
            yield event_bridge.create_run_finished_event()

        except json.JSONDecodeError:
            logger.error(f"Failed to parse tool result: {tool_content_text}")
            yield RunErrorEvent(message=f"Invalid tool result format: {tool_content_text[:100]}")
            yield event_bridge.create_run_finished_event()


class DefaultOrchestrator(Orchestrator):
    """Standard agent execution (no special handling)."""

    def can_handle(self, context: ExecutionContext) -> bool:
        """Always returns True as this is the fallback orchestrator.

        Args:
            context: Execution context

        Returns:
            Always True
        """
        return True

    async def run(
        self,
        context: ExecutionContext,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Standard agent run with event translation.

        This implements the default agent execution flow using the event bridge
        to translate Agent Framework events to AG-UI events.

        Args:
            context: Execution context

        Yields:
            AG-UI events
        """
        from ._events import AgentFrameworkEventBridge

        logger.info(f"Starting default agent run for thread_id={context.thread_id}, run_id={context.run_id}")

        # Initialize state tracking
        initial_state = context.input_data.get("state", {})
        current_state: dict[str, Any] = initial_state.copy() if initial_state else {}

        # Check if agent uses structured outputs (response_format)
        # Use isinstance to narrow type for proper attribute access
        response_format = None
        if isinstance(context.agent, ChatAgent):
            response_format = context.agent.chat_options.response_format
        skip_text_content = response_format is not None

        # Create event bridge
        event_bridge = AgentFrameworkEventBridge(
            run_id=context.run_id,
            thread_id=context.thread_id,
            predict_state_config=context.config.predict_state_config,
            current_state=current_state,
            skip_text_content=skip_text_content,
            input_messages=context.input_data.get("messages", []),
            require_confirmation=context.config.require_confirmation,
        )

        yield event_bridge.create_run_started_event()

        # Emit PredictState custom event if we have predictive state config
        if context.config.predict_state_config:
            from ag_ui.core import CustomEvent, EventType

            predict_state_value = [
                {
                    "state_key": state_key,
                    "tool": config["tool"],
                    "tool_argument": config["tool_argument"],
                }
                for state_key, config in context.config.predict_state_config.items()
            ]

            yield CustomEvent(
                type=EventType.CUSTOM,
                name="PredictState",
                value=predict_state_value,
            )

        # If we have a state schema, ensure we emit initial state snapshot
        if context.config.state_schema:
            # Initialize missing state fields with appropriate empty values based on schema type
            for key, schema in context.config.state_schema.items():
                if key not in current_state:
                    # Default to empty object; use empty array if schema specifies "array" type
                    current_state[key] = [] if isinstance(schema, dict) and schema.get("type") == "array" else {}  # type: ignore
            yield event_bridge.create_state_snapshot_event(current_state)

        # Create thread for context tracking
        thread = AgentThread()
        thread.metadata = {  # type: ignore[attr-defined]
            "ag_ui_thread_id": context.thread_id,
            "ag_ui_run_id": context.run_id,
        }

        # Inject current state into thread metadata so agent can access it
        if current_state:
            thread.metadata["current_state"] = current_state  # type: ignore[attr-defined]

        # Add incoming AG-UI messages to the thread history
        if context.messages:
            await thread.on_new_messages(context.messages)

        # Use the full incoming message batch to preserve tool-call adjacency
        if not context.messages:
            logger.warning("No messages provided in AG-UI input")
            yield event_bridge.create_run_finished_event()
            return

        # Inject current state as system message context if we have state
        messages_to_run: list[Any] = []
        if current_state and context.config.state_schema:
            state_json = json.dumps(current_state, indent=2)
            from agent_framework import ChatMessage

            state_context_msg = ChatMessage(
                role="system",
                contents=[
                    TextContent(
                        text=f"""Current state of the application:
{state_json}

When modifying state, you MUST include ALL existing data plus your changes.
For example, if adding a new ingredient, include all existing ingredients PLUS the new one.
Never replace existing data - always append or merge."""
                    )
                ],
            )
            messages_to_run.append(state_context_msg)

        # Preserve order from client to satisfy provider constraints (assistant tool_calls must
        # immediately precede tool result messages). Using the full batch avoids reordering.
        messages_to_run.extend(context.messages)

        # Handle client tools for hybrid execution
        # Client sends tool metadata, server merges with its own tools.
        # Client tools have func=None (declaration-only), so @use_function_invocation
        # will return the function call without executing (passes back to client).
        from agent_framework import BaseChatClient

        client_tools = convert_agui_tools_to_agent_framework(context.input_data.get("tools"))

        # Extract server tools - use type narrowing when possible
        server_tools: list[Any] = []
        if isinstance(context.agent, ChatAgent):
            server_tools = context.agent.chat_options.tools or []
        else:
            # AgentProtocol allows duck-typed implementations - fallback to attribute access
            # This supports test mocks and custom agent implementations
            try:
                chat_options_attr = getattr(context.agent, "chat_options", None)
                if chat_options_attr is not None:
                    server_tools = getattr(chat_options_attr, "tools", None) or []
            except AttributeError:
                pass

        # Register client tools as additional (declaration-only) so they are not executed on server
        if client_tools:
            if isinstance(context.agent, ChatAgent):
                # Type-safe path for ChatAgent
                chat_client = context.agent.chat_client
                if (
                    isinstance(chat_client, BaseChatClient)
                    and chat_client.function_invocation_configuration is not None
                ):
                    chat_client.function_invocation_configuration.additional_tools = client_tools
                    logger.debug(
                        f"[TOOLS] Registered {len(client_tools)} client tools as additional_tools (declaration-only)"
                    )
            else:
                # Fallback for AgentProtocol implementations (test mocks, custom agents)
                try:
                    chat_client_attr = getattr(context.agent, "chat_client", None)
                    if chat_client_attr is not None:
                        fic = getattr(chat_client_attr, "function_invocation_configuration", None)
                        if fic is not None:
                            fic.additional_tools = client_tools  # type: ignore[attr-defined]
                            logger.debug(
                                f"[TOOLS] Registered {len(client_tools)} client tools as additional_tools (declaration-only)"
                            )
                except AttributeError:
                    pass

        combined_tools: list[Any] = []
        if server_tools:
            combined_tools.extend(server_tools)
        if client_tools:
            combined_tools.extend(client_tools)

        # Collect all updates to get the final structured output
        all_updates: list[Any] = []
        async for update in context.agent.run_stream(messages_to_run, thread=thread, tools=combined_tools or None):
            all_updates.append(update)
            events = await event_bridge.from_agent_run_update(update)
            for event in events:
                yield event

        # After agent completes, check if we should stop (waiting for user to confirm changes)
        if event_bridge.should_stop_after_confirm:
            logger.info("Stopping run after confirm_changes - waiting for user response")
            yield event_bridge.create_run_finished_event()
            return

        # After streaming completes, check if agent has response_format and extract structured output
        if all_updates and response_format:
            from agent_framework import AgentRunResponse
            from pydantic import BaseModel

            logger.info(f"Processing structured output, update count: {len(all_updates)}")

            # Convert streaming updates to final response to get the structured output
            final_response = AgentRunResponse.from_agent_run_response_updates(
                all_updates, output_format_type=response_format
            )

            if final_response.value and isinstance(final_response.value, BaseModel):
                # Convert Pydantic model to dict
                response_dict = final_response.value.model_dump(mode="json", exclude_none=True)
                logger.info(f"Received structured output: {list(response_dict.keys())}")

                # Extract state fields based on state_schema
                state_updates: dict[str, Any] = {}

                if context.config.state_schema:
                    # Use state_schema to determine which fields are state
                    for state_key in context.config.state_schema.keys():
                        if state_key in response_dict:
                            state_updates[state_key] = response_dict[state_key]
                else:
                    # No schema: treat all non-message fields as state
                    state_updates = {k: v for k, v in response_dict.items() if k != "message"}

                # Apply state updates if any found
                if state_updates:
                    current_state.update(state_updates)

                    # Emit StateSnapshotEvent with the updated state
                    state_snapshot = event_bridge.create_state_snapshot_event(current_state)
                    yield state_snapshot
                    logger.info(f"Emitted StateSnapshotEvent with updates: {list(state_updates.keys())}")

                # If there's a message field, emit it as chat text
                if "message" in response_dict and response_dict["message"]:
                    message_id = generate_event_id()
                    yield TextMessageStartEvent(message_id=message_id, role="assistant")
                    yield TextMessageContentEvent(message_id=message_id, delta=response_dict["message"])
                    yield TextMessageEndEvent(message_id=message_id)
                    logger.info(f"Emitted conversational message: {response_dict['message'][:100]}...")

        if event_bridge.current_message_id:
            yield event_bridge.create_message_end_event(event_bridge.current_message_id)

        yield event_bridge.create_run_finished_event()
        logger.info(f"Completed agent run for thread_id={context.thread_id}, run_id={context.run_id}")


__all__ = [
    "Orchestrator",
    "ExecutionContext",
    "HumanInTheLoopOrchestrator",
    "DefaultOrchestrator",
]
