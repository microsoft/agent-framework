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
from agent_framework import (
    AgentProtocol,
    AgentThread,
    ChatAgent,
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)

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

        # Sanitizer: ensure tool results only follow assistant tool calls
        # Also inject synthetic tool results for confirm_changes
        def sanitize_tool_history(messages: list[ChatMessage]) -> list[ChatMessage]:
            sanitized: list[ChatMessage] = []
            pending_tool_call_ids: set[str] | None = None
            pending_confirm_changes_id: str | None = None

            for msg in messages:
                role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)

                if role_value == "assistant":
                    tool_ids = {
                        str(content.call_id)
                        for content in msg.contents or []
                        if isinstance(content, FunctionCallContent) and content.call_id
                    }
                    # Check for confirm_changes tool call
                    confirm_changes_call = None
                    for content in msg.contents or []:
                        if isinstance(content, FunctionCallContent) and content.name == "confirm_changes":
                            confirm_changes_call = content
                            break

                    sanitized.append(msg)
                    pending_tool_call_ids = tool_ids if tool_ids else None
                    pending_confirm_changes_id = (
                        str(confirm_changes_call.call_id)
                        if confirm_changes_call and confirm_changes_call.call_id
                        else None
                    )
                    continue

                if role_value == "user":
                    # Check if this user message is a confirm_changes response (JSON with "accepted" field)
                    # This must be checked BEFORE injecting synthetic results for pending tool calls
                    if pending_confirm_changes_id:
                        user_text = ""
                        for content in msg.contents or []:
                            if isinstance(content, TextContent):
                                user_text = content.text
                                break

                        try:
                            parsed = json.loads(user_text)
                            if "accepted" in parsed:
                                # This is a confirm_changes response - inject synthetic tool result
                                logger.info(
                                    f"Injecting synthetic tool result for confirm_changes call_id={pending_confirm_changes_id}"
                                )
                                synthetic_result = ChatMessage(
                                    role="tool",
                                    contents=[
                                        FunctionResultContent(
                                            call_id=pending_confirm_changes_id,
                                            result="Confirmed" if parsed.get("accepted") else "Rejected",
                                        )
                                    ],
                                )
                                sanitized.append(synthetic_result)
                                if pending_tool_call_ids:
                                    pending_tool_call_ids.discard(pending_confirm_changes_id)
                                pending_confirm_changes_id = None
                                # Don't add the user message to sanitized - it's been converted to tool result
                                continue
                        except (json.JSONDecodeError, KeyError) as e:
                            # Failed to parse user message as confirm_changes response; continue normal processing
                            logger.debug(f"Could not parse user message as confirm_changes response: {e}")

                    # Before processing user message, check if there are pending tool calls without results
                    # This happens when assistant made multiple tool calls but only some got results
                    # This is checked AFTER confirm_changes special handling above
                    if pending_tool_call_ids:
                        logger.info(
                            f"User message arrived with {len(pending_tool_call_ids)} pending tool calls - injecting synthetic results"
                        )
                        for pending_call_id in pending_tool_call_ids:
                            logger.info(f"Injecting synthetic tool result for pending call_id={pending_call_id}")
                            synthetic_result = ChatMessage(
                                role="tool",
                                contents=[
                                    FunctionResultContent(
                                        call_id=pending_call_id,
                                        result="Tool execution skipped - user provided follow-up message",
                                    )
                                ],
                            )
                            sanitized.append(synthetic_result)
                        pending_tool_call_ids = None
                        pending_confirm_changes_id = None

                    # Normal user message processing
                    sanitized.append(msg)
                    pending_confirm_changes_id = None
                    continue

                if role_value == "tool":
                    if not pending_tool_call_ids:
                        continue
                    keep = False
                    for content in msg.contents or []:
                        if isinstance(content, FunctionResultContent):
                            call_id = str(content.call_id)
                            if call_id in pending_tool_call_ids:
                                keep = True
                                # Note: We do NOT remove call_id from pending here.
                                # This allows duplicate tool results to pass through sanitization
                                # so the deduplicator can choose the best one (prefer non-empty results).
                                # We only clear pending_tool_call_ids when a user message arrives.
                                if call_id == pending_confirm_changes_id:
                                    # For confirm_changes specifically, we do want to clear it
                                    # since we only expect one response
                                    pending_confirm_changes_id = None
                                break
                    if keep:
                        sanitized.append(msg)
                    continue

                sanitized.append(msg)
                pending_tool_call_ids = None
                pending_confirm_changes_id = None

            return sanitized

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

        raw_messages = context.messages or []
        if not raw_messages:
            logger.warning("No messages provided in AG-UI input")
            yield event_bridge.create_run_finished_event()
            return

        logger.info(f"Received {len(raw_messages)} raw messages from client")
        for i, msg in enumerate(raw_messages):
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            msg_id = getattr(msg, "message_id", None)
            logger.info(f"  Raw message {i}: role={role}, id={msg_id}")
            if hasattr(msg, "contents") and msg.contents:
                for j, content in enumerate(msg.contents):
                    content_type = type(content).__name__
                    if isinstance(content, TextContent):
                        logger.debug(f"    Content {j}: {content_type} - {content.text}")
                    elif isinstance(content, FunctionCallContent):
                        logger.debug(f"    Content {j}: {content_type} - {content.name}({content.arguments})")
                    elif isinstance(content, FunctionResultContent):
                        logger.debug(
                            f"    Content {j}: {content_type} - call_id={content.call_id}, result={content.result}"
                        )
                    else:
                        logger.debug(f"    Content {j}: {content_type} - {content}")

        # After getting sanitized_messages, deduplicate them
        def deduplicate_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
            """Remove duplicate messages while preserving order.

            For tool results with the same call_id, prefer the one with actual data.
            """
            seen_keys: dict[Any, int] = {}  # key -> index in unique_messages (key can be various tuple types)
            unique_messages: list[ChatMessage] = []

            for idx, msg in enumerate(messages):
                role_value = msg.role.value if hasattr(msg.role, "value") else str(msg.role)

                # For tool messages, use call_id as unique key
                if role_value == "tool" and msg.contents and isinstance(msg.contents[0], FunctionResultContent):
                    call_id = str(msg.contents[0].call_id)
                    key: Any = (role_value, call_id)

                    # Check if we already have this tool result
                    if key in seen_keys:
                        existing_idx = seen_keys[key]
                        existing_msg = unique_messages[existing_idx]

                        # Compare results - prefer non-empty over empty
                        existing_result = None
                        if existing_msg.contents and isinstance(existing_msg.contents[0], FunctionResultContent):
                            existing_result = existing_msg.contents[0].result
                        new_result = msg.contents[0].result

                        # Replace if existing is empty/None and new has data
                        if (not existing_result or existing_result == "") and new_result:
                            logger.info(
                                f"Replacing empty tool result at index {existing_idx} with data from index {idx}"
                            )
                            unique_messages[existing_idx] = msg
                        else:
                            logger.info(f"Skipping duplicate tool result at index {idx}: call_id={call_id}")
                        continue

                    seen_keys[key] = len(unique_messages)
                    unique_messages.append(msg)

                elif (
                    role_value == "assistant"
                    and msg.contents
                    and any(isinstance(c, FunctionCallContent) for c in msg.contents)
                ):
                    # For assistant messages with tool_calls, use the tool call IDs
                    tool_call_ids = tuple(
                        sorted(str(c.call_id) for c in msg.contents if isinstance(c, FunctionCallContent) and c.call_id)
                    )
                    key = (role_value, tool_call_ids)

                    if key in seen_keys:
                        logger.info(f"Skipping duplicate assistant tool call at index {idx}")
                        continue

                    seen_keys[key] = len(unique_messages)
                    unique_messages.append(msg)

                else:
                    # For other messages (system, user, assistant without tools), hash the content
                    content_str = str([str(c) for c in msg.contents]) if msg.contents else ""
                    key = (role_value, hash(content_str))

                    if key in seen_keys:
                        logger.info(f"Skipping duplicate message at index {idx}: role={role_value}")
                        continue

                    seen_keys[key] = len(unique_messages)
                    unique_messages.append(msg)

            return unique_messages

        # Then use it:
        sanitized_messages = sanitize_tool_history(raw_messages)
        provider_messages = deduplicate_messages(sanitized_messages)

        if not provider_messages:
            logger.info("No provider-eligible messages after filtering; finishing run without invoking agent.")
            yield event_bridge.create_run_finished_event()
            return

        logger.info(f"Processing {len(provider_messages)} provider messages after sanitization/deduplication")
        for i, msg in enumerate(provider_messages):
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            logger.info(f"  Message {i}: role={role}")
            if hasattr(msg, "contents") and msg.contents:
                for j, content in enumerate(msg.contents):
                    content_type = type(content).__name__
                    if isinstance(content, TextContent):
                        logger.info(f"    Content {j}: {content_type} - {content.text}")
                    elif isinstance(content, FunctionCallContent):
                        logger.info(f"    Content {j}: {content_type} - {content.name}({content.arguments})")
                    elif isinstance(content, FunctionResultContent):
                        logger.info(
                            f"    Content {j}: {content_type} - call_id={content.call_id}, result={content.result}"
                        )
                    else:
                        logger.info(f"    Content {j}: {content_type} - {content}")

        # NOTE: For AG-UI, the client sends the full conversation history on each request.
        # We should NOT add to thread.on_new_messages() as that would cause duplication.
        # Instead, we pass messages directly to the agent via messages_to_run.

        # Inject current state as system message context if we have state
        messages_to_run: list[Any] = []

        conversation_has_tool_calls = False
        logger.debug(f"Checking {len(provider_messages)} provider messages for tool calls")
        for i, msg in enumerate(provider_messages):
            logger.debug(
                f"  Message {i}: role={msg.role.value}, contents={len(msg.contents) if hasattr(msg, 'contents') and msg.contents else 0}"
            )
        for msg in provider_messages:
            if msg.role.value == "assistant" and hasattr(msg, "contents") and msg.contents:
                if any(isinstance(content, FunctionCallContent) for content in msg.contents):
                    conversation_has_tool_calls = True
                    break
        if current_state and context.config.state_schema and not conversation_has_tool_calls:
            state_json = json.dumps(current_state, indent=2)
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

        # Add all provider messages to messages_to_run
        # AG-UI sends full conversation history on each request, so we pass it directly to the agent
        messages_to_run.extend(provider_messages)

        # Handle client tools for hybrid execution
        # Client sends tool metadata, server merges with its own tools.
        # Client tools have func=None (declaration-only), so @use_function_invocation
        # will return the function call without executing (passes back to client).
        from agent_framework import BaseChatClient

        client_tools = convert_agui_tools_to_agent_framework(context.input_data.get("tools"))
        logger.info(f"[TOOLS] Client sent {len(client_tools) if client_tools else 0} tools")
        if client_tools:
            for tool in client_tools:
                tool_name = getattr(tool, "name", "unknown")
                declaration_only = getattr(tool, "declaration_only", None)
                logger.info(f"[TOOLS]   - Client tool: {tool_name}, declaration_only={declaration_only}")

        # Extract server tools - use type narrowing when possible
        server_tools: list[Any] = []
        if isinstance(context.agent, ChatAgent):
            tools_from_agent = context.agent.chat_options.tools
            server_tools = list(tools_from_agent) if tools_from_agent else []
            logger.info(f"[TOOLS] Agent has {len(server_tools)} configured tools")
            for tool in server_tools:
                tool_name = getattr(tool, "name", "unknown")
                approval_mode = getattr(tool, "approval_mode", None)
                logger.info(f"[TOOLS]   - {tool_name}: approval_mode={approval_mode}")
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

        # For tools parameter: only pass if we have client tools to add
        # If we pass tools=, it overrides the agent's configured tools and loses metadata like approval_mode
        # So only pass tools when we need to add client tools on top of server tools
        # IMPORTANT: Don't include client tools that duplicate server tools (same name)
        tools_param = None
        if client_tools:
            # Get server tool names
            server_tool_names = {getattr(tool, "name", None) for tool in server_tools}

            # Filter out client tools that duplicate server tools
            unique_client_tools = [
                tool for tool in client_tools if getattr(tool, "name", None) not in server_tool_names
            ]

            if unique_client_tools:
                combined_tools: list[Any] = []
                if server_tools:
                    combined_tools.extend(server_tools)
                combined_tools.extend(unique_client_tools)
                tools_param = combined_tools
                logger.info(
                    f"[TOOLS] Passing tools= parameter with {len(combined_tools)} tools ({len(server_tools)} server + {len(unique_client_tools)} unique client)"
                )
            else:
                logger.info("[TOOLS] All client tools duplicate server tools - not passing tools= parameter")
        else:
            logger.info("[TOOLS] No client tools - not passing tools= parameter (using agent's configured tools)")

        # Collect all updates to get the final structured output
        all_updates: list[Any] = []
        async for update in context.agent.run_stream(messages_to_run, thread=thread, tools=tools_param):
            all_updates.append(update)
            events = await event_bridge.from_agent_run_update(update)
            for event in events:
                yield event

        # After agent completes, check if we should stop (waiting for user to confirm changes)
        if event_bridge.should_stop_after_confirm:
            logger.info("Stopping run after confirm_changes - waiting for user response")
            yield event_bridge.create_run_finished_event()
            return

        # Check if there are pending tool calls (declaration-only tools that weren't executed)
        # These need ToolCallEndEvent to signal the client to execute them
        # Only emit for tool calls that haven't already had ToolCallEndEvent emitted
        # (approval-required tools already had their end event emitted)
        if event_bridge.pending_tool_calls:
            pending_without_end = [
                tc for tc in event_bridge.pending_tool_calls if tc.get("id") not in event_bridge.tool_calls_ended
            ]
            if pending_without_end:
                logger.info(
                    f"Found {len(pending_without_end)} pending tool calls without end event - emitting ToolCallEndEvent"
                )
                for tool_call in pending_without_end:
                    tool_call_id = tool_call.get("id")
                    if tool_call_id:
                        from ag_ui.core import ToolCallEndEvent

                        end_event = ToolCallEndEvent(tool_call_id=tool_call_id)
                        logger.info(f"Emitting ToolCallEndEvent for declaration-only tool call '{tool_call_id}'")
                        yield end_event

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
