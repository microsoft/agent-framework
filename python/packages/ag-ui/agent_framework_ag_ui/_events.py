# Copyright (c) Microsoft. All rights reserved.

"""Event bridge for converting Agent Framework events to AG-UI protocol."""

import json
import logging
import re
from copy import deepcopy
from typing import Any

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    EventType,
    MessagesSnapshotEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import (
    AgentRunResponseUpdate,
    FunctionApprovalRequestContent,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
)

from ._utils import generate_event_id

logger = logging.getLogger(__name__)


class AgentFrameworkEventBridge:
    """Converts Agent Framework responses to AG-UI events."""

    def __init__(
        self,
        run_id: str,
        thread_id: str,
        predict_state_config: dict[str, dict[str, str]] | None = None,
        current_state: dict[str, Any] | None = None,
        skip_text_content: bool = False,
        input_messages: list[Any] | None = None,
        require_confirmation: bool = True,
    ) -> None:
        """
        Initialize the event bridge.

        Args:
            run_id: The run identifier.
            thread_id: The thread identifier.
            predict_state_config: Configuration for predictive state updates.
                Format: {"state_key": {"tool": "tool_name", "tool_argument": "arg_name"}}
            current_state: Reference to the current state dict for tracking updates.
            skip_text_content: If True, skip emitting TextMessageContentEvents (for structured outputs).
            input_messages: The input messages from the conversation history.
            require_confirmation: Whether predictive state updates require user confirmation.
        """
        self.run_id = run_id
        self.thread_id = thread_id
        self.current_message_id: str | None = None
        self.current_tool_call_id: str | None = None
        self.current_tool_call_name: str | None = None  # Track the tool name across streaming chunks
        self.predict_state_config = predict_state_config or {}
        self.current_state = current_state or {}
        self.pending_state_updates: dict[str, Any] = {}  # Track updates from tool calls
        self.skip_text_content = skip_text_content
        self.require_confirmation = require_confirmation

        # For predictive state updates: accumulate streaming arguments
        self.streaming_tool_args: str = ""  # Accumulated JSON string
        self.last_emitted_state: dict[str, Any] = {}  # Track last emitted state to avoid duplicates
        self.state_delta_count: int = 0  # Counter for sampling log output
        self.should_stop_after_confirm: bool = False  # Flag to stop run after confirm_changes
        self.suppressed_summary: str = ""  # Store LLM summary to show after confirmation

        # For MessagesSnapshotEvent: track tool calls and results
        self.input_messages = input_messages or []
        self.pending_tool_calls: list[dict[str, Any]] = []  # Track tool calls for assistant message
        self.tool_results: list[dict[str, Any]] = []  # Track tool results
        self.tool_calls_ended: set[str] = set()  # Track which tool calls have had ToolCallEndEvent emitted
        self.accumulated_text_content: str = ""  # Track accumulated text for final MessagesSnapshotEvent

    async def from_agent_run_update(self, update: AgentRunResponseUpdate) -> list[BaseEvent]:
        """
        Convert an AgentRunResponseUpdate to AG-UI events.

        Args:
            update: The agent run update to convert.

        Returns:
            List of AG-UI events.
        """
        events: list[BaseEvent] = []

        logger.info(f"Processing AgentRunUpdate with {len(update.contents)} content items")
        for idx, content in enumerate(update.contents):
            logger.info(f"  Content {idx}: type={type(content).__name__}")
            if isinstance(content, TextContent):
                events.extend(self._handle_text_content(content))
            elif isinstance(content, FunctionCallContent):
                events.extend(self._handle_function_call_content(content))
            elif isinstance(content, FunctionResultContent):
                events.extend(self._handle_function_result_content(content))
            elif isinstance(content, FunctionApprovalRequestContent):
                events.extend(self._handle_function_approval_request_content(content))

        return events

    def _handle_text_content(self, content: TextContent) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        logger.info(f"  TextContent found: length={len(content.text)}")
        logger.info(
            "  Flags: skip_text_content=%s, should_stop_after_confirm=%s",
            self.skip_text_content,
            self.should_stop_after_confirm,
        )

        if self.skip_text_content:
            logger.info("  SKIPPING TextContent: skip_text_content is True")
            return events

        if self.should_stop_after_confirm:
            logger.info("  SKIPPING TextContent: waiting for confirm_changes response")
            self.suppressed_summary += content.text
            logger.info(f"  Suppressed summary length={len(self.suppressed_summary)}")
            return events

        # Skip empty text chunks to avoid emitting
        # TextMessageContentEvent with an empty `delta` which fails
        # Pydantic validation (AG-UI requires non-empty strings).
        if not content.text:
            logger.info("  SKIPPING TextContent: empty chunk")
            return events

        if not self.current_message_id:
            self.current_message_id = generate_event_id()
            start_event = TextMessageStartEvent(
                message_id=self.current_message_id,
                role="assistant",
            )
            logger.info(f"  EMITTING TextMessageStartEvent with message_id={self.current_message_id}")
            events.append(start_event)

        event = TextMessageContentEvent(
            message_id=self.current_message_id,
            delta=content.text,
        )
        self.accumulated_text_content += content.text
        logger.info(f"  EMITTING TextMessageContentEvent with text_len={len(content.text)}")
        events.append(event)
        return events

    def _handle_function_call_content(self, content: FunctionCallContent) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if content.name:
            logger.debug(f"Tool call: {content.name} (call_id: {content.call_id})")

        if not content.name and not content.call_id and not self.current_tool_call_name:
            args_length = len(str(content.arguments)) if content.arguments else 0
            logger.warning(f"FunctionCallContent missing name and call_id. args_length={args_length}")

        tool_call_id = self._coalesce_tool_call_id(content)
        if content.name and tool_call_id != self.current_tool_call_id:
            self.streaming_tool_args = ""
            self.state_delta_count = 0
        if content.name:
            self.current_tool_call_id = tool_call_id
            self.current_tool_call_name = content.name

            tool_start_event = ToolCallStartEvent(
                tool_call_id=tool_call_id,
                tool_call_name=content.name,
                parent_message_id=self.current_message_id,
            )
            logger.info(f"Emitting ToolCallStartEvent with name='{content.name}', id='{tool_call_id}'")
            events.append(tool_start_event)

            self.pending_tool_calls.append(
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": content.name,
                        "arguments": "",
                    },
                }
            )
        elif tool_call_id:
            self.current_tool_call_id = tool_call_id

        if content.arguments:
            delta_str = content.arguments if isinstance(content.arguments, str) else json.dumps(content.arguments)
            logger.info(f"Emitting ToolCallArgsEvent with delta_length={len(delta_str)}, id='{tool_call_id}'")
            args_event = ToolCallArgsEvent(
                tool_call_id=tool_call_id,
                delta=delta_str,
            )
            events.append(args_event)

            for tool_call in self.pending_tool_calls:
                if tool_call["id"] == tool_call_id:
                    tool_call["function"]["arguments"] += delta_str
                    break

            events.extend(self._emit_predictive_state_deltas(delta_str))
            events.extend(self._legacy_predictive_state(content))

        return events

    def _coalesce_tool_call_id(self, content: FunctionCallContent) -> str:
        if content.call_id:
            return content.call_id
        if self.current_tool_call_id:
            return self.current_tool_call_id
        return generate_event_id()

    def _emit_predictive_state_deltas(self, argument_chunk: str) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if not self.current_tool_call_name or not self.predict_state_config:
            return events

        self.streaming_tool_args += argument_chunk
        logger.debug(
            "Predictive state: accumulated %s chars for tool '%s'",
            len(self.streaming_tool_args),
            self.current_tool_call_name,
        )

        parsed_args = None
        try:
            parsed_args = json.loads(self.streaming_tool_args)
        except json.JSONDecodeError:
            for state_key, config in self.predict_state_config.items():
                if config["tool"] != self.current_tool_call_name:
                    continue
                tool_arg_name = config["tool_argument"]
                pattern = rf'"{re.escape(tool_arg_name)}":\s*"([^"]*)'
                match = re.search(pattern, self.streaming_tool_args)

                if match:
                    partial_value = match.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

                    if state_key not in self.last_emitted_state or self.last_emitted_state[state_key] != partial_value:
                        state_delta_event = StateDeltaEvent(
                            delta=[
                                {
                                    "op": "replace",
                                    "path": f"/{state_key}",
                                    "value": partial_value,
                                }
                            ],
                        )

                        self.state_delta_count += 1
                        if self.state_delta_count % 10 == 1:
                            logger.info(
                                "StateDeltaEvent #%s for '%s': op=replace, path=/%s, value_length=%s",
                                self.state_delta_count,
                                state_key,
                                state_key,
                                len(str(partial_value)),
                            )
                        elif self.state_delta_count % 100 == 0:
                            logger.info(f"StateDeltaEvent #{self.state_delta_count} emitted")

                        events.append(state_delta_event)
                        self.last_emitted_state[state_key] = partial_value
                        self.pending_state_updates[state_key] = partial_value

        if parsed_args:
            for state_key, config in self.predict_state_config.items():
                if config["tool"] != self.current_tool_call_name:
                    continue
                tool_arg_name = config["tool_argument"]

                if tool_arg_name == "*":
                    state_value = parsed_args
                elif tool_arg_name in parsed_args:
                    state_value = parsed_args[tool_arg_name]
                else:
                    continue

                if state_key not in self.last_emitted_state or self.last_emitted_state[state_key] != state_value:
                    state_delta_event = StateDeltaEvent(
                        delta=[
                            {
                                "op": "replace",
                                "path": f"/{state_key}",
                                "value": state_value,
                            }
                        ],
                    )

                    self.state_delta_count += 1
                    if self.state_delta_count % 10 == 1:
                        logger.info(
                            "StateDeltaEvent #%s for '%s': op=replace, path=/%s, value_length=%s",
                            self.state_delta_count,
                            state_key,
                            state_key,
                            len(str(state_value)),
                        )
                    elif self.state_delta_count % 100 == 0:
                        logger.info(f"StateDeltaEvent #{self.state_delta_count} emitted")

                    events.append(state_delta_event)
                    self.last_emitted_state[state_key] = state_value
                    self.pending_state_updates[state_key] = state_value
        return events

    def _legacy_predictive_state(self, content: FunctionCallContent) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if not (content.name and content.arguments):
            return events
        parsed_args = content.parse_arguments()
        if not parsed_args:
            return events

        logger.info(
            "Checking predict_state_config keys: %s",
            list(self.predict_state_config.keys()) if self.predict_state_config else "None",
        )
        for state_key, config in self.predict_state_config.items():
            logger.info(f"Checking state_key='{state_key}'")
            if config["tool"] != content.name:
                continue
            tool_arg_name = config["tool_argument"]
            logger.info(f"MATCHED tool '{content.name}' for state key '{state_key}', arg='{tool_arg_name}'")

            state_value: Any
            if tool_arg_name == "*":
                state_value = parsed_args
                logger.info(f"Using all args as state value, keys: {list(state_value.keys())}")
            elif tool_arg_name in parsed_args:
                state_value = parsed_args[tool_arg_name]
                logger.info(f"Using specific arg '{tool_arg_name}' as state value")
            else:
                logger.warning(f"Tool argument '{tool_arg_name}' not found in parsed args")
                continue

            previous_value = self.last_emitted_state.get(state_key, object())
            if previous_value == state_value:
                logger.info(
                    "Skipping duplicate StateDeltaEvent for key '%s' - value unchanged",
                    state_key,
                )
                continue

            state_delta_event = StateDeltaEvent(
                delta=[
                    {
                        "op": "replace",
                        "path": f"/{state_key}",
                        "value": state_value,
                    }
                ],
            )
            logger.info(f"Emitting StateDeltaEvent for key '{state_key}', value type: {type(state_value)}")  # type: ignore
            events.append(state_delta_event)
            self.pending_state_updates[state_key] = state_value
            self.last_emitted_state[state_key] = state_value
        return events

    def _handle_function_result_content(self, content: FunctionResultContent) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if content.call_id:
            end_event = ToolCallEndEvent(
                tool_call_id=content.call_id,
            )
            logger.info(f"Emitting ToolCallEndEvent for completed tool call '{content.call_id}'")
            events.append(end_event)
            self.tool_calls_ended.add(content.call_id)

            if self.state_delta_count > 0:
                logger.info(
                    "Tool call '%s' complete: emitted %s StateDeltaEvents total",
                    content.call_id,
                    self.state_delta_count,
                )

            self.streaming_tool_args = ""
            self.state_delta_count = 0

        result_message_id = generate_event_id()
        if isinstance(content.result, dict):
            result_content = json.dumps(content.result)  # type: ignore[arg-type]
        elif content.result is not None:
            result_content = str(content.result)
        else:
            result_content = ""

        result_event = ToolCallResultEvent(
            message_id=result_message_id,
            tool_call_id=content.call_id,
            content=result_content,
            role="tool",
        )
        events.append(result_event)

        self.tool_results.append(
            {
                "id": result_message_id,
                "role": "tool",
                "toolCallId": content.call_id,
                "content": result_content,
            }
        )

        events.extend(self._emit_snapshot_for_tool_result())
        events.extend(self._emit_state_snapshot_and_confirmation())

        return events

    def _emit_snapshot_for_tool_result(self) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        should_emit_snapshot = self.pending_tool_calls and self.tool_results

        is_predictive_without_confirmation = False
        if should_emit_snapshot and self.current_tool_call_name and self.predict_state_config:
            for _, config in self.predict_state_config.items():
                if config["tool"] == self.current_tool_call_name and not self.require_confirmation:
                    is_predictive_without_confirmation = True
                    logger.info(
                        "Skipping intermediate MessagesSnapshotEvent for predictive tool '%s' - delaying until summary",
                        self.current_tool_call_name,
                    )
                    break

        if should_emit_snapshot and not is_predictive_without_confirmation:
            from ._message_adapters import agent_framework_messages_to_agui

            assistant_message = {
                "id": generate_event_id(),
                "role": "assistant",
                "tool_calls": self.pending_tool_calls.copy(),
            }
            converted_input_messages = agent_framework_messages_to_agui(self.input_messages)
            all_messages = converted_input_messages + [assistant_message] + self.tool_results.copy()

            messages_snapshot_event = MessagesSnapshotEvent(
                type=EventType.MESSAGES_SNAPSHOT,
                messages=all_messages,  # type: ignore[arg-type]
            )
            logger.info(f"Emitting MessagesSnapshotEvent with {len(all_messages)} messages")
            events.append(messages_snapshot_event)
        return events

    def _emit_state_snapshot_and_confirmation(self) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if self.pending_state_updates:
            for key, value in self.pending_state_updates.items():
                self.current_state[key] = value

            logger.info(f"Emitting StateSnapshotEvent with keys: {list(self.current_state.keys())}")
            if "recipe" in self.current_state:
                recipe = self.current_state["recipe"]
                logger.info(
                    "Recipe fields: title=%s, skill_level=%s, ingredients_count=%s, instructions_count=%s",
                    recipe.get("title"),
                    recipe.get("skill_level"),
                    len(recipe.get("ingredients", [])),
                    len(recipe.get("instructions", [])),
                )

            state_snapshot_event = StateSnapshotEvent(
                snapshot=self.current_state,
            )
            events.append(state_snapshot_event)

            tool_was_predictive = False
            logger.debug(
                "Checking predictive state: current_tool='%s', predict_config=%s",
                self.current_tool_call_name,
                list(self.predict_state_config.keys()) if self.predict_state_config else "None",
            )
            for state_key, config in self.predict_state_config.items():
                if self.current_tool_call_name and config["tool"] == self.current_tool_call_name:
                    logger.info(
                        "Tool '%s' matches predictive config for state key '%s'",
                        self.current_tool_call_name,
                        state_key,
                    )
                    tool_was_predictive = True
                    break

            if tool_was_predictive and self.require_confirmation:
                events.extend(self._emit_confirm_changes_tool_call())
            elif tool_was_predictive:
                logger.info("Skipping confirm_changes - require_confirmation is False")

            self.pending_state_updates.clear()
            self.last_emitted_state = deepcopy(self.current_state)
            self.current_tool_call_name = None
        return events

    def _emit_confirm_changes_tool_call(self) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        confirm_call_id = generate_event_id()
        logger.info("Emitting confirm_changes tool call for predictive update")

        self.pending_tool_calls.append(
            {
                "id": confirm_call_id,
                "type": "function",
                "function": {
                    "name": "confirm_changes",
                    "arguments": "{}",
                },
            }
        )

        confirm_start = ToolCallStartEvent(
            tool_call_id=confirm_call_id,
            tool_call_name="confirm_changes",
        )
        events.append(confirm_start)

        confirm_args = ToolCallArgsEvent(
            tool_call_id=confirm_call_id,
            delta="{}",
        )
        events.append(confirm_args)

        confirm_end = ToolCallEndEvent(
            tool_call_id=confirm_call_id,
        )
        events.append(confirm_end)

        from ._message_adapters import agent_framework_messages_to_agui

        assistant_message = {
            "id": generate_event_id(),
            "role": "assistant",
            "tool_calls": self.pending_tool_calls.copy(),
        }

        converted_input_messages = agent_framework_messages_to_agui(self.input_messages)
        all_messages = converted_input_messages + [assistant_message] + self.tool_results.copy()

        messages_snapshot_event = MessagesSnapshotEvent(
            type=EventType.MESSAGES_SNAPSHOT,
            messages=all_messages,  # type: ignore[arg-type]
        )
        logger.info(f"Emitting MessagesSnapshotEvent for confirm_changes with {len(all_messages)} messages")
        events.append(messages_snapshot_event)

        self.should_stop_after_confirm = True
        logger.info("Set flag to stop run after confirm_changes")
        return events

    def _handle_function_approval_request_content(self, content: FunctionApprovalRequestContent) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        logger.info("=== FUNCTION APPROVAL REQUEST ===")
        logger.info(f"  Function: {content.function_call.name}")
        logger.info(f"  Call ID: {content.function_call.call_id}")

        parsed_args = content.function_call.parse_arguments()
        parsed_arg_keys = list(parsed_args.keys()) if parsed_args else "None"
        logger.info(f"  Parsed args keys: {parsed_arg_keys}")

        if parsed_args and self.predict_state_config:
            logger.info(
                "  Checking predict_state_config keys: %s",
                list(self.predict_state_config.keys()) if self.predict_state_config else "None",
            )
            for state_key, config in self.predict_state_config.items():
                if config["tool"] != content.function_call.name:
                    continue
                tool_arg_name = config["tool_argument"]
                logger.info(
                    "  MATCHED tool '%s' for state key '%s', arg='%s'",
                    content.function_call.name,
                    state_key,
                    tool_arg_name,
                )

                state_value: Any
                if tool_arg_name == "*":
                    state_value = parsed_args
                elif tool_arg_name in parsed_args:
                    state_value = parsed_args[tool_arg_name]
                else:
                    logger.warning(f"  Tool argument '{tool_arg_name}' not found in parsed args")
                    continue

                self.current_state[state_key] = state_value
                logger.info("Emitting StateSnapshotEvent for key '%s', value type: %s", state_key, type(state_value))  # type: ignore
                state_snapshot = StateSnapshotEvent(
                    snapshot=self.current_state,
                )
                events.append(state_snapshot)

        if content.function_call.call_id:
            end_event = ToolCallEndEvent(
                tool_call_id=content.function_call.call_id,
            )
            logger.info(f"Emitting ToolCallEndEvent for approval-required tool '{content.function_call.call_id}'")
            events.append(end_event)
            self.tool_calls_ended.add(content.function_call.call_id)

        approval_event = CustomEvent(
            name="function_approval_request",
            value={
                "id": content.id,
                "function_call": {
                    "call_id": content.function_call.call_id,
                    "name": content.function_call.name,
                    "arguments": content.function_call.parse_arguments(),
                },
            },
        )
        logger.info(f"Emitting function_approval_request custom event for '{content.function_call.name}'")
        events.append(approval_event)
        return events

    def create_run_started_event(self) -> RunStartedEvent:
        """Create a run started event."""
        return RunStartedEvent(
            run_id=self.run_id,
            thread_id=self.thread_id,
        )

    def create_run_finished_event(self, result: Any = None) -> RunFinishedEvent:
        """Create a run finished event."""
        return RunFinishedEvent(
            run_id=self.run_id,
            thread_id=self.thread_id,
            result=result,
        )

    def create_message_start_event(self, message_id: str, role: str = "assistant") -> TextMessageStartEvent:
        """Create a message start event."""
        return TextMessageStartEvent(
            message_id=message_id,
            role=role,  # type: ignore
        )

    def create_message_end_event(self, message_id: str) -> TextMessageEndEvent:
        """Create a message end event."""
        return TextMessageEndEvent(
            message_id=message_id,
        )

    def create_state_snapshot_event(self, state: dict[str, Any]) -> StateSnapshotEvent:
        """Create a state snapshot event.

        Args:
            state: The complete state snapshot.

        Returns:
            StateSnapshotEvent.
        """
        return StateSnapshotEvent(
            snapshot=state,
        )

    def create_state_delta_event(self, delta: list[dict[str, Any]]) -> StateDeltaEvent:
        """Create a state delta event using JSON Patch format (RFC 6902).

        Args:
            delta: List of JSON Patch operations.

        Returns:
            StateDeltaEvent.
        """
        return StateDeltaEvent(
            delta=delta,
        )
