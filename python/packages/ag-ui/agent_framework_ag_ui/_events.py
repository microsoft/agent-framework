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
    AgentResponseUpdate,
    FunctionApprovalRequestContent,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
    prepare_function_call_results,
)

from ._utils import extract_state_from_tool_args, generate_event_id, safe_json_parse

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
        require_confirmation: bool = True,
        approval_tool_name: str | None = None,
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
        self.approval_tool_name = approval_tool_name

        # For predictive state updates: accumulate streaming arguments
        self.streaming_tool_args: str = ""  # Accumulated JSON string
        self.last_emitted_state: dict[str, Any] = {}  # Track last emitted state to avoid duplicates
        self.state_delta_count: int = 0  # Counter for sampling log output
        self.should_stop_after_confirm: bool = False  # Flag to stop run after confirm_changes
        self.suppressed_summary: str = ""  # Store LLM summary to show after confirmation

    async def from_agent_run_update(self, update: AgentResponseUpdate) -> list[BaseEvent]:
        """
        Convert an AgentResponseUpdate to AG-UI events.

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
        # Only emit ToolCallStartEvent once per tool call (when it's a new tool call)
        if content.name and tool_call_id != self.current_tool_call_id:
            self.streaming_tool_args = ""
            self.state_delta_count = 0
            self.current_tool_call_id = tool_call_id
            self.current_tool_call_name = content.name

            tool_start_event = ToolCallStartEvent(
                tool_call_id=tool_call_id,
                tool_call_name=content.name,
                parent_message_id=self.current_message_id,
            )
            logger.info(f"Emitting ToolCallStartEvent with name='{content.name}', id='{tool_call_id}'")
            events.append(tool_start_event)
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

            events.extend(self._emit_predictive_state_deltas(delta_str))

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

        parsed_args = safe_json_parse(self.streaming_tool_args)
        if parsed_args is None:
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

                state_value = extract_state_from_tool_args(parsed_args, tool_arg_name)
                if state_value is None:
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

    def _handle_function_result_content(self, content: FunctionResultContent) -> list[BaseEvent]:
        events: list[BaseEvent] = []
        if content.call_id:
            end_event = ToolCallEndEvent(
                tool_call_id=content.call_id,
            )
            logger.info(f"Emitting ToolCallEndEvent for completed tool call '{content.call_id}'")
            events.append(end_event)

            if self.state_delta_count > 0:
                logger.info(
                    "Tool call '%s' complete: emitted %s StateDeltaEvents total",
                    content.call_id,
                    self.state_delta_count,
                )

            self.streaming_tool_args = ""
            self.state_delta_count = 0

        result_message_id = generate_event_id()
        result_content = prepare_function_call_results(content.result)

        result_event = ToolCallResultEvent(
            message_id=result_message_id,
            tool_call_id=content.call_id,
            content=result_content,
            role="tool",
        )
        events.append(result_event)
        events.extend(self._emit_state_snapshot_and_confirmation())

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

    def _emit_confirm_changes_tool_call(self, function_call: FunctionCallContent | None = None) -> list[BaseEvent]:
        """Emit a confirm_changes tool call for Dojo UI compatibility.

        Args:
            function_call: Optional function call that needs confirmation.
                If provided, includes function info in the confirm_changes args
                so Dojo UI can display what's being confirmed.
        """
        events: list[BaseEvent] = []
        confirm_call_id = generate_event_id()
        logger.info("Emitting confirm_changes tool call for predictive update")

        confirm_start = ToolCallStartEvent(
            tool_call_id=confirm_call_id,
            tool_call_name="confirm_changes",
            parent_message_id=self.current_message_id,
        )
        events.append(confirm_start)

        # Include function info if this is for a function approval
        # This helps Dojo UI display meaningful confirmation info
        if function_call:
            args_dict = {
                "function_name": function_call.name,
                "function_call_id": function_call.call_id,
                "function_arguments": function_call.parse_arguments() or {},
                "steps": [
                    {
                        "description": f"Execute {function_call.name}",
                        "status": "enabled",
                    }
                ],
            }
            args_json = json.dumps(args_dict)
        else:
            args_json = "{}"

        confirm_args = ToolCallArgsEvent(
            tool_call_id=confirm_call_id,
            delta=args_json,
        )
        events.append(confirm_args)

        confirm_end = ToolCallEndEvent(
            tool_call_id=confirm_call_id,
        )
        events.append(confirm_end)

        self.should_stop_after_confirm = True
        logger.info("Set flag to stop run after confirm_changes")
        return events

    def _emit_function_approval_tool_call(self, function_call: FunctionCallContent) -> list[BaseEvent]:
        """Emit a tool call that can drive UI approval for function requests."""
        tool_call_name = "confirm_changes"
        if self.approval_tool_name and self.approval_tool_name != function_call.name:
            tool_call_name = self.approval_tool_name

        tool_call_id = generate_event_id()
        tool_start = ToolCallStartEvent(
            tool_call_id=tool_call_id,
            tool_call_name=tool_call_name,
            parent_message_id=self.current_message_id,
        )
        events: list[BaseEvent] = [tool_start]

        args_dict = {
            "function_name": function_call.name,
            "function_call_id": function_call.call_id,
            "function_arguments": function_call.parse_arguments() or {},
            "steps": [
                {
                    "description": f"Execute {function_call.name}",
                    "status": "enabled",
                }
            ],
        }
        args_json = json.dumps(args_dict)

        events.append(
            ToolCallArgsEvent(
                tool_call_id=tool_call_id,
                delta=args_json,
            )
        )
        events.append(
            ToolCallEndEvent(
                tool_call_id=tool_call_id,
            )
        )

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

                state_value = extract_state_from_tool_args(parsed_args, tool_arg_name)
                if state_value is None:
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

        # Emit the function_approval_request custom event for UI implementations that support it
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

        # Emit a UI-friendly approval tool call for function approvals.
        if self.require_confirmation:
            events.extend(self._emit_function_approval_tool_call(content.function_call))

        # Signal orchestrator to stop the run and wait for user approval response
        self.should_stop_after_confirm = True
        logger.info("Set flag to stop run - waiting for function approval response")
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
