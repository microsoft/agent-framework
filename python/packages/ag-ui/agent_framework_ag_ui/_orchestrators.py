# Copyright (c) Microsoft. All rights reserved.

"""Orchestrators for multi-turn agent flows."""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Sequence
from typing import TYPE_CHECKING, Any

from ag_ui.core import (
    BaseEvent,
    MessagesSnapshotEvent,
    RunErrorEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import (
    AgentProtocol,
    AgentThread,
    ChatAgent,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)
from agent_framework._middleware import extract_and_merge_function_middleware
from agent_framework._tools import (
    FunctionInvocationConfiguration,
    _collect_approval_responses,  # type: ignore
    _replace_approval_contents_with_results,  # type: ignore
    _try_execute_function_calls,  # type: ignore
)

from ._orchestration._helpers import (
    approval_steps,
    build_safe_metadata,
    collect_approved_state_snapshots,
    ensure_tool_call_entry,
    is_step_based_approval,
    latest_approval_response,
    select_approval_tool_name,
    select_messages_to_run,
    tool_name_for_call_id,
)
from ._orchestration._tooling import (
    collect_server_tools,
    merge_tools,
    register_additional_client_tools,
)
from ._utils import (
    convert_agui_tools_to_agent_framework,
    generate_event_id,
    get_conversation_id_from_update,
    get_role_value,
)

if TYPE_CHECKING:
    from ._agent import AgentConfig
    from ._confirmation_strategies import ConfirmationStrategy
    from ._events import AgentFrameworkEventBridge
    from ._orchestration._state_manager import StateManager


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
        self._snapshot_messages = None
        self._last_message = None
        self._run_id: str | None = None
        self._thread_id: str | None = None
        self._supplied_run_id: str | None = None
        self._supplied_thread_id: str | None = None

    @property
    def messages(self):
        """Get converted Agent Framework messages (lazy loaded)."""
        if self._messages is None:
            from ._message_adapters import normalize_agui_input_messages

            raw = self.input_data.get("messages", [])
            if not isinstance(raw, list):
                raw = []
            self._messages, self._snapshot_messages = normalize_agui_input_messages(raw)
        return self._messages

    @property
    def snapshot_messages(self) -> list[dict[str, Any]]:
        """Get normalized AG-UI snapshot messages (lazy loaded)."""
        if self._snapshot_messages is None:
            if self._messages is None:
                _ = self.messages
            else:
                from ._message_adapters import agent_framework_messages_to_agui, agui_messages_to_snapshot_format

                raw_snapshot = agent_framework_messages_to_agui(self._messages)
                self._snapshot_messages = agui_messages_to_snapshot_format(raw_snapshot)
        return self._snapshot_messages or []

    @property
    def last_message(self):
        """Get the last message in the conversation (lazy loaded)."""
        if self._last_message is None and self.messages:
            self._last_message = self.messages[-1]
        return self._last_message

    @property
    def supplied_run_id(self) -> str | None:
        """Get the supplied run ID, if any."""
        if self._supplied_run_id is None:
            self._supplied_run_id = self.input_data.get("run_id") or self.input_data.get("runId")
        return self._supplied_run_id

    @property
    def run_id(self) -> str:
        """Get supplied run ID or generate a new run ID."""
        if self._run_id:
            return self._run_id

        if self.supplied_run_id:
            self._run_id = self.supplied_run_id

        if self._run_id is None:
            self._run_id = str(uuid.uuid4())

        return self._run_id

    @property
    def supplied_thread_id(self) -> str | None:
        """Get the supplied thread ID, if any."""
        if self._supplied_thread_id is None:
            self._supplied_thread_id = self.input_data.get("thread_id") or self.input_data.get("threadId")
        return self._supplied_thread_id

    @property
    def thread_id(self) -> str:
        """Get supplied thread ID or generate a new thread ID."""
        if self._thread_id:
            return self._thread_id

        if self.supplied_thread_id:
            self._thread_id = self.supplied_thread_id

        if self._thread_id is None:
            self._thread_id = str(uuid.uuid4())

        return self._thread_id

    def update_run_id(self, new_run_id: str) -> None:
        """Update the run ID in the context.

        Args:
            new_run_id: The new run ID to set
        """
        self._supplied_run_id = new_run_id
        self._run_id = new_run_id

    def update_thread_id(self, new_thread_id: str) -> None:
        """Update the thread ID in the context.

        Args:
            new_thread_id: The new thread ID to set
        """
        self._supplied_thread_id = new_thread_id
        self._thread_id = new_thread_id


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

    def _create_initial_events(
        self, event_bridge: "AgentFrameworkEventBridge", state_manager: "StateManager"
    ) -> Sequence[BaseEvent]:
        """Generate initial events for the run.

        Args:
            event_bridge: Event bridge for creating events
        Returns:
            Initial AG-UI events
        """
        events: list[BaseEvent] = [event_bridge.create_run_started_event()]

        predict_event = state_manager.predict_state_event()
        if predict_event:
            events.append(predict_event)

        snapshot_event = state_manager.initial_snapshot_event(event_bridge)
        if snapshot_event:
            events.append(snapshot_event)

        return events

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
        from ._orchestration._state_manager import StateManager

        logger.info(f"Starting default agent run for thread_id={context.thread_id}, run_id={context.run_id}")

        response_format = None
        if isinstance(context.agent, ChatAgent):
            response_format = context.agent.default_options.get("response_format")
        skip_text_content = response_format is not None

        client_tools = convert_agui_tools_to_agent_framework(context.input_data.get("tools"))
        approval_tool_name = select_approval_tool_name(client_tools)

        state_manager = StateManager(
            state_schema=context.config.state_schema,
            predict_state_config=context.config.predict_state_config,
            require_confirmation=context.config.require_confirmation,
        )
        current_state = state_manager.initialize(context.input_data.get("state"))

        event_bridge = AgentFrameworkEventBridge(
            run_id=context.run_id,
            thread_id=context.thread_id,
            predict_state_config=context.config.predict_state_config,
            current_state=current_state,
            skip_text_content=skip_text_content,
            require_confirmation=context.config.require_confirmation,
            approval_tool_name=approval_tool_name,
        )

        if context.config.use_service_thread:
            thread = AgentThread(service_thread_id=context.supplied_thread_id)
        else:
            thread = AgentThread()

        thread.metadata = {  # type: ignore[attr-defined]
            "ag_ui_thread_id": context.thread_id,
            "ag_ui_run_id": context.run_id,
        }
        if current_state:
            thread.metadata["current_state"] = current_state  # type: ignore[attr-defined]

        provider_messages = context.messages or []
        snapshot_messages = context.snapshot_messages
        if not provider_messages:
            for event in self._create_initial_events(event_bridge, state_manager):
                yield event
            logger.warning("No messages provided in AG-UI input")
            yield event_bridge.create_run_finished_event()
            return

        logger.info(f"Received {len(provider_messages)} provider messages from client")
        for i, msg in enumerate(provider_messages):
            role = get_role_value(msg)
            msg_id = getattr(msg, "message_id", None)
            logger.info(f"  Message {i}: role={role}, id={msg_id}")
            if hasattr(msg, "contents") and msg.contents:
                for j, content in enumerate(msg.contents):
                    content_type = type(content).__name__
                    if isinstance(content, TextContent):
                        logger.debug("    Content %s: %s - text_length=%s", j, content_type, len(content.text))
                    elif isinstance(content, FunctionCallContent):
                        arg_length = len(str(content.arguments)) if content.arguments else 0
                        logger.debug(
                            "    Content %s: %s - %s args_length=%s", j, content_type, content.name, arg_length
                        )
                    elif isinstance(content, FunctionResultContent):
                        result_preview = type(content.result).__name__ if content.result is not None else "None"
                        logger.debug(
                            "    Content %s: %s - call_id=%s, result_type=%s",
                            j,
                            content_type,
                            content.call_id,
                            result_preview,
                        )
                    else:
                        logger.debug(f"    Content {j}: {content_type}")

        pending_tool_calls: list[dict[str, Any]] = []
        tool_calls_by_id: dict[str, dict[str, Any]] = {}
        tool_results: list[dict[str, Any]] = []
        tool_calls_ended: set[str] = set()
        messages_snapshot_emitted = False
        accumulated_text_content = ""
        active_message_id: str | None = None

        # Check for FunctionApprovalResponseContent and emit updated state snapshot
        # This ensures the UI shows the approved state (e.g., 2 steps) not the original (3 steps)
        for snapshot_evt in collect_approved_state_snapshots(
            provider_messages,
            context.config.predict_state_config,
            current_state,
            event_bridge,
        ):
            yield snapshot_evt

        messages_to_run = select_messages_to_run(provider_messages, state_manager)

        logger.info(f"[TOOLS] Client sent {len(client_tools) if client_tools else 0} tools")
        if client_tools:
            for tool in client_tools:
                tool_name = getattr(tool, "name", "unknown")
                declaration_only = getattr(tool, "declaration_only", None)
                logger.info(f"[TOOLS]   - Client tool: {tool_name}, declaration_only={declaration_only}")

        server_tools = collect_server_tools(context.agent)
        register_additional_client_tools(context.agent, client_tools)
        tools_param = merge_tools(server_tools, client_tools)

        collect_updates = response_format is not None
        all_updates: list[Any] | None = [] if collect_updates else None
        update_count = 0
        # Prepare metadata for chat client (Azure requires string values)
        safe_metadata = build_safe_metadata(getattr(thread, "metadata", None))

        run_kwargs: dict[str, Any] = {
            "thread": thread,
            "tools": tools_param,
            "options": {"metadata": safe_metadata},
        }
        if safe_metadata:
            run_kwargs["options"]["store"] = True

        async def _resolve_approval_responses(
            messages: list[Any],
            tools_for_execution: list[Any],
        ) -> None:
            fcc_todo = _collect_approval_responses(messages)
            if not fcc_todo:
                return

            approved_responses = [resp for resp in fcc_todo.values() if resp.approved]
            approved_function_results: list[Any] = []
            if approved_responses and tools_for_execution:
                chat_client = getattr(context.agent, "chat_client", None)
                config = (
                    getattr(chat_client, "function_invocation_configuration", None) or FunctionInvocationConfiguration()
                )
                middleware_pipeline = extract_and_merge_function_middleware(chat_client, run_kwargs)
                try:
                    results, _ = await _try_execute_function_calls(
                        custom_args=run_kwargs,
                        attempt_idx=0,
                        function_calls=approved_responses,
                        tools=tools_for_execution,
                        middleware_pipeline=middleware_pipeline,
                        config=config,
                    )
                    approved_function_results = list(results)
                except Exception:
                    logger.error("Failed to execute approved tool calls; injecting error results.")
                    approved_function_results = []

            normalized_results: list[FunctionResultContent] = []
            for idx, approval in enumerate(approved_responses):
                if idx < len(approved_function_results) and isinstance(
                    approved_function_results[idx], FunctionResultContent
                ):
                    normalized_results.append(approved_function_results[idx])
                    continue
                call_id = approval.function_call.call_id or approval.id
                normalized_results.append(
                    FunctionResultContent(call_id=call_id, result="Error: Tool call invocation failed.")
                )

            _replace_approval_contents_with_results(messages, fcc_todo, normalized_results)  # type: ignore

        def _should_emit_tool_snapshot(tool_name: str | None) -> bool:
            if not pending_tool_calls or not tool_results:
                return False
            if tool_name and context.config.predict_state_config and not context.config.require_confirmation:
                for config in context.config.predict_state_config.values():
                    if config["tool"] == tool_name:
                        logger.info(
                            f"Skipping intermediate MessagesSnapshotEvent for predictive tool '{tool_name}' "
                            " - delaying until summary"
                        )
                        return False
            return True

        def _build_messages_snapshot(tool_message_id: str | None = None) -> MessagesSnapshotEvent:
            has_text_content = bool(accumulated_text_content)
            all_messages = snapshot_messages.copy()

            if pending_tool_calls:
                if tool_message_id and not has_text_content:
                    tool_call_message_id = tool_message_id
                else:
                    tool_call_message_id = (
                        active_message_id if not has_text_content and active_message_id else generate_event_id()
                    )
                tool_call_message = {
                    "id": tool_call_message_id,
                    "role": "assistant",
                    "tool_calls": pending_tool_calls.copy(),
                }
                all_messages.append(tool_call_message)

            all_messages.extend(tool_results)

            if has_text_content and active_message_id:
                assistant_text_message = {
                    "id": active_message_id,
                    "role": "assistant",
                    "content": accumulated_text_content,
                }
                all_messages.append(assistant_text_message)

            return MessagesSnapshotEvent(
                messages=all_messages,  # type: ignore[arg-type]
            )

        # Use tools_param if available (includes client tools), otherwise fall back to server_tools
        # This ensures both server tools AND client tools can be executed after approval
        tools_for_approval = tools_param if tools_param is not None else server_tools
        latest_approval = latest_approval_response(messages_to_run)
        await _resolve_approval_responses(messages_to_run, tools_for_approval)

        if latest_approval and is_step_based_approval(latest_approval, context.config.predict_state_config):
            from ._confirmation_strategies import DefaultConfirmationStrategy

            strategy = context.confirmation_strategy
            if strategy is None:
                strategy = DefaultConfirmationStrategy()

            steps = approval_steps(latest_approval)
            if steps:
                if latest_approval.approved:
                    confirmation_message = strategy.on_approval_accepted(steps)
                else:
                    confirmation_message = strategy.on_approval_rejected(steps)
            else:
                if latest_approval.approved:
                    confirmation_message = strategy.on_state_confirmed()
                else:
                    confirmation_message = strategy.on_state_rejected()

            message_id = generate_event_id()
            for event in self._create_initial_events(event_bridge, state_manager):
                yield event
            yield TextMessageStartEvent(message_id=message_id, role="assistant")
            yield TextMessageContentEvent(message_id=message_id, delta=confirmation_message)
            yield TextMessageEndEvent(message_id=message_id)
            yield event_bridge.create_run_finished_event()
            return

        should_recreate_event_bridge = False
        async for update in context.agent.run_stream(messages_to_run, **run_kwargs):
            conv_id = get_conversation_id_from_update(update)
            if conv_id and conv_id != context.thread_id:
                context.update_thread_id(conv_id)
                should_recreate_event_bridge = True

            if update.response_id and update.response_id != context.run_id:
                context.update_run_id(update.response_id)
                should_recreate_event_bridge = True

            if should_recreate_event_bridge:
                event_bridge = AgentFrameworkEventBridge(
                    run_id=context.run_id,
                    thread_id=context.thread_id,
                    predict_state_config=context.config.predict_state_config,
                    current_state=current_state,
                    skip_text_content=skip_text_content,
                    require_confirmation=context.config.require_confirmation,
                    approval_tool_name=approval_tool_name,
                )
                should_recreate_event_bridge = False

            if update_count == 0:
                for event in self._create_initial_events(event_bridge, state_manager):
                    yield event

            update_count += 1
            logger.info(f"[STREAM] Received update #{update_count} from agent")
            if all_updates is not None:
                all_updates.append(update)
            if event_bridge.current_message_id is None and update.contents:
                has_tool_call = any(isinstance(content, FunctionCallContent) for content in update.contents)
                has_text = any(isinstance(content, TextContent) for content in update.contents)
                if has_tool_call and not has_text:
                    tool_message_id = generate_event_id()
                    event_bridge.current_message_id = tool_message_id
                    active_message_id = tool_message_id
                    accumulated_text_content = ""
                    logger.info(
                        "[STREAM] Emitting TextMessageStartEvent for tool-only response message_id=%s",
                        tool_message_id,
                    )
                    yield TextMessageStartEvent(message_id=tool_message_id, role="assistant")
            events = await event_bridge.from_agent_run_update(update)
            logger.info(f"[STREAM] Update #{update_count} produced {len(events)} events")
            for event in events:
                if isinstance(event, TextMessageStartEvent):
                    active_message_id = event.message_id
                    accumulated_text_content = ""
                elif isinstance(event, TextMessageContentEvent):
                    accumulated_text_content += event.delta
                elif isinstance(event, ToolCallStartEvent):
                    tool_call_entry = ensure_tool_call_entry(event.tool_call_id, tool_calls_by_id, pending_tool_calls)
                    tool_call_entry["function"]["name"] = event.tool_call_name
                elif isinstance(event, ToolCallArgsEvent):
                    tool_call_entry = ensure_tool_call_entry(event.tool_call_id, tool_calls_by_id, pending_tool_calls)
                    tool_call_entry["function"]["arguments"] += event.delta
                elif isinstance(event, ToolCallEndEvent):
                    tool_calls_ended.add(event.tool_call_id)
                elif isinstance(event, ToolCallResultEvent):
                    tool_results.append(
                        {
                            "id": event.message_id,
                            "role": "tool",
                            "toolCallId": event.tool_call_id,
                            "content": event.content,
                        }
                    )
                logger.info(f"[STREAM] Yielding event: {type(event).__name__}")
                yield event
                if isinstance(event, ToolCallResultEvent):
                    tool_name = tool_name_for_call_id(tool_calls_by_id, event.tool_call_id)
                    if _should_emit_tool_snapshot(tool_name):
                        messages_snapshot_emitted = True
                        messages_snapshot = _build_messages_snapshot()
                        logger.info(f"[STREAM] Yielding event: {type(messages_snapshot).__name__}")
                        yield messages_snapshot
                elif isinstance(event, ToolCallEndEvent):
                    tool_name = tool_name_for_call_id(tool_calls_by_id, event.tool_call_id)
                    if tool_name == "confirm_changes":
                        messages_snapshot_emitted = True
                        messages_snapshot = _build_messages_snapshot()
                        logger.info(f"[STREAM] Yielding event: {type(messages_snapshot).__name__}")
                        yield messages_snapshot

        logger.info(f"[STREAM] Agent stream completed. Total updates: {update_count}")

        if event_bridge.should_stop_after_confirm:
            logger.info("Stopping run - waiting for user approval/confirmation response")
            if event_bridge.current_message_id:
                logger.info(f"[CONFIRM] Emitting TextMessageEndEvent for message_id={event_bridge.current_message_id}")
                yield event_bridge.create_message_end_event(event_bridge.current_message_id)
                event_bridge.current_message_id = None
            yield event_bridge.create_run_finished_event()
            return

        if pending_tool_calls:
            pending_without_end = [tc for tc in pending_tool_calls if tc.get("id") not in tool_calls_ended]
            if pending_without_end:
                logger.info(
                    "Found %s pending tool calls without end event - emitting ToolCallEndEvent",
                    len(pending_without_end),
                )
                for tool_call in pending_without_end:
                    tool_call_id = tool_call.get("id")
                    if tool_call_id:
                        end_event = ToolCallEndEvent(tool_call_id=tool_call_id)
                        logger.info(f"Emitting ToolCallEndEvent for declaration-only tool call '{tool_call_id}'")
                        yield end_event

        if response_format and all_updates:
            from agent_framework import AgentResponse
            from pydantic import BaseModel

            logger.info(f"Processing structured output, update count: {len(all_updates)}")
            final_response = AgentResponse.from_agent_run_response_updates(
                all_updates, output_format_type=response_format
            )

            if final_response.value and isinstance(final_response.value, BaseModel):
                response_dict = final_response.value.model_dump(mode="json", exclude_none=True)
                logger.info(f"Received structured output keys: {list(response_dict.keys())}")

                state_updates = state_manager.extract_state_updates(response_dict)
                if state_updates:
                    state_manager.apply_state_updates(state_updates)
                    state_snapshot = event_bridge.create_state_snapshot_event(current_state)
                    yield state_snapshot
                    logger.info(f"Emitted StateSnapshotEvent with updates: {list(state_updates.keys())}")

                if "message" in response_dict and response_dict["message"]:
                    message_id = generate_event_id()
                    yield TextMessageStartEvent(message_id=message_id, role="assistant")
                    yield TextMessageContentEvent(message_id=message_id, delta=response_dict["message"])
                    yield TextMessageEndEvent(message_id=message_id)
                    logger.info(f"Emitted conversational message with length={len(response_dict['message'])}")

        if all_updates is not None and len(all_updates) == 0:
            logger.info("No updates received from agent - emitting initial events")
            for event in self._create_initial_events(event_bridge, state_manager):
                yield event

        logger.info(f"[FINALIZE] Checking for unclosed message. current_message_id={event_bridge.current_message_id}")
        if event_bridge.current_message_id:
            logger.info(f"[FINALIZE] Emitting TextMessageEndEvent for message_id={event_bridge.current_message_id}")
            yield event_bridge.create_message_end_event(event_bridge.current_message_id)

            messages_snapshot = _build_messages_snapshot(tool_message_id=event_bridge.current_message_id)
            messages_snapshot_emitted = True
            logger.info(
                f"[FINALIZE] Emitting MessagesSnapshotEvent with {len(messages_snapshot.messages)} messages "
                f"(text content length: {len(accumulated_text_content)})"
            )
            yield messages_snapshot
        else:
            logger.info("[FINALIZE] No current_message_id - skipping TextMessageEndEvent")
            if not messages_snapshot_emitted and (pending_tool_calls or tool_results):
                messages_snapshot = _build_messages_snapshot()
                messages_snapshot_emitted = True
                logger.info(
                    f"[FINALIZE] Emitting MessagesSnapshotEvent with {len(messages_snapshot.messages)} messages"
                )
                yield messages_snapshot

        logger.info("[FINALIZE] Emitting RUN_FINISHED event")
        yield event_bridge.create_run_finished_event()
        logger.info(f"Completed agent run for thread_id={context.thread_id}, run_id={context.run_id}")


__all__ = [
    "Orchestrator",
    "ExecutionContext",
    "HumanInTheLoopOrchestrator",
    "DefaultOrchestrator",
]
