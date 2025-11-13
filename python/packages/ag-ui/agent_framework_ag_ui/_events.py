# Copyright (c) Microsoft. All rights reserved.

"""Event bridge for converting Agent Framework events to AG-UI protocol."""

import json
import logging
import re
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

    async def from_agent_run_update(self, update: AgentRunResponseUpdate) -> list[BaseEvent]:
        """
        Convert an AgentRunResponseUpdate to AG-UI events.

        Args:
            update: The agent run update to convert.

        Returns:
            List of AG-UI events.
        """
        events: list[BaseEvent] = []

        for content in update.contents:
            if isinstance(content, TextContent):
                # Skip text content if using structured outputs (it's just the JSON)
                if self.skip_text_content:
                    continue

                # Skip text content if we're about to emit confirm_changes
                # The summary should only appear after user confirms
                if self.should_stop_after_confirm:
                    logger.debug("Skipping text content - waiting for confirm_changes response")
                    # Save the summary text to show after confirmation
                    self.suppressed_summary += content.text
                    continue

                if not self.current_message_id:
                    self.current_message_id = generate_event_id()
                    start_event = TextMessageStartEvent(
                        message_id=self.current_message_id,
                        role="assistant",
                    )
                    logger.debug(f"Emitting TextMessageStartEvent with message_id={self.current_message_id}")
                    events.append(start_event)

                event = TextMessageContentEvent(
                    message_id=self.current_message_id,
                    delta=content.text,
                )
                logger.debug(f"Emitting TextMessageContentEvent with delta: {content.text}")
                events.append(event)

            elif isinstance(content, FunctionCallContent):
                # Log tool calls for debugging
                if content.name:
                    logger.debug(f"Tool call: {content.name} (call_id: {content.call_id})")

                if not content.name and not content.call_id and not self.current_tool_call_name:
                    args_preview = str(content.arguments)[:50] if content.arguments else "None"
                    logger.warning(f"FunctionCallContent missing name and call_id. Args: {args_preview}")

                # Get or use existing tool call ID - all chunks of same tool call share the same call_id
                # Important: the first chunk might have name but no call_id yet
                if content.call_id:
                    tool_call_id = content.call_id
                elif self.current_tool_call_id:
                    tool_call_id = self.current_tool_call_id
                else:
                    # Generate a new ID for this tool call
                    tool_call_id = (
                        generate_event_id()
                    )  # Handle streaming tool calls - name comes in first chunk, arguments in subsequent chunks
                if content.name:
                    # This is a new tool call or the first chunk with the name
                    self.current_tool_call_id = tool_call_id
                    self.current_tool_call_name = content.name

                    tool_start_event = ToolCallStartEvent(
                        tool_call_id=tool_call_id,
                        tool_call_name=content.name,
                        parent_message_id=self.current_message_id,
                    )
                    logger.info(f"Emitting ToolCallStartEvent with name='{content.name}', id='{tool_call_id}'")
                    events.append(tool_start_event)

                    # Track tool call for MessagesSnapshotEvent
                    # Initialize a new tool call entry
                    self.pending_tool_calls.append(
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": content.name,
                                "arguments": "",  # Will accumulate as we get argument chunks
                            },
                        }
                    )
                else:
                    # Subsequent chunk without name - update our tracked ID if needed
                    if tool_call_id:
                        self.current_tool_call_id = tool_call_id

                # Emit arguments if present
                if content.arguments:
                    # content.arguments is already a JSON string from the LLM for streaming calls
                    # For non-streaming it could be a dict, so we need to handle both
                    if isinstance(content.arguments, str):
                        delta_str = content.arguments
                    else:
                        # If it's a dict, convert to JSON
                        delta_str = json.dumps(content.arguments)

                    logger.info(f"Emitting ToolCallArgsEvent with delta: {delta_str!r}..., id='{tool_call_id}'")
                    args_event = ToolCallArgsEvent(
                        tool_call_id=tool_call_id,
                        delta=delta_str,
                    )
                    events.append(args_event)

                    # Accumulate arguments for MessagesSnapshotEvent
                    if self.pending_tool_calls:
                        # Find the matching tool call and append the delta
                        for tool_call in self.pending_tool_calls:
                            if tool_call["id"] == tool_call_id:
                                tool_call["function"]["arguments"] += delta_str
                                break

                    # Predictive state updates - accumulate streaming arguments and emit deltas
                    # Use current_tool_call_name since content.name is only present on first chunk
                    if self.current_tool_call_name and self.predict_state_config:
                        # Accumulate the argument string
                        if isinstance(content.arguments, str):
                            self.streaming_tool_args += content.arguments
                        else:
                            self.streaming_tool_args += json.dumps(content.arguments)

                        logger.debug(
                            f"Predictive state: accumulated {len(self.streaming_tool_args)} chars for tool '{self.current_tool_call_name}'"
                        )

                        # Try to parse accumulated arguments (may be incomplete JSON)
                        # We use a lenient approach: try standard parsing first, then try to extract partial values
                        parsed_args = None
                        try:
                            parsed_args = json.loads(self.streaming_tool_args)
                        except json.JSONDecodeError:
                            # JSON is incomplete - try to extract partial string values
                            # For streaming "document" field, we can extract: {"document": "text...
                            # Look for pattern: {"field": "value (incomplete)
                            for state_key, config in self.predict_state_config.items():
                                if config["tool"] == self.current_tool_call_name:
                                    tool_arg_name = config["tool_argument"]

                                    # Try to extract partial string value for this argument
                                    # Pattern: "argument_name": "partial text
                                    pattern = rf'"{re.escape(tool_arg_name)}":\s*"([^"]*)'
                                    match = re.search(pattern, self.streaming_tool_args)

                                    if match:
                                        partial_value = match.group(1)
                                        # Unescape common sequences
                                        partial_value = (
                                            partial_value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                                        )

                                        # Emit delta if we have new content
                                        if (
                                            state_key not in self.last_emitted_state
                                            or self.last_emitted_state[state_key] != partial_value
                                        ):
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
                                                value_preview = (
                                                    str(partial_value)[:100] + "..."
                                                    if len(str(partial_value)) > 100
                                                    else str(partial_value)
                                                )
                                                logger.info(
                                                    f"StateDeltaEvent #{self.state_delta_count} for '{state_key}': "
                                                    f"op=replace, path=/{state_key}, value={value_preview}"
                                                )
                                            elif self.state_delta_count % 100 == 0:
                                                logger.info(f"StateDeltaEvent #{self.state_delta_count} emitted")

                                            events.append(state_delta_event)
                                            self.last_emitted_state[state_key] = partial_value
                                            self.pending_state_updates[state_key] = partial_value

                        # If we successfully parsed complete JSON, process it
                        if parsed_args:
                            # Check if this tool matches any predictive state config
                            for state_key, config in self.predict_state_config.items():
                                if config["tool"] == self.current_tool_call_name:
                                    tool_arg_name = config["tool_argument"]

                                    # Extract the state value
                                    if tool_arg_name == "*":
                                        state_value = parsed_args
                                    elif tool_arg_name in parsed_args:
                                        state_value = parsed_args[tool_arg_name]
                                    else:
                                        continue

                                    # Only emit if state has changed from last emission
                                    if (
                                        state_key not in self.last_emitted_state
                                        or self.last_emitted_state[state_key] != state_value
                                    ):
                                        # Emit StateDeltaEvent for real-time UI updates (JSON Patch format)
                                        state_delta_event = StateDeltaEvent(
                                            delta=[
                                                {
                                                    "op": "replace",  # Use replace since field exists in schema
                                                    "path": f"/{state_key}",  # JSON Pointer path with leading slash
                                                    "value": state_value,
                                                }
                                            ],
                                        )

                                        # Increment counter and log every 10th emission with sample data
                                        self.state_delta_count += 1
                                        if self.state_delta_count % 10 == 1:  # Log 1st, 11th, 21st, etc.
                                            value_preview = (
                                                str(state_value)[:100] + "..."
                                                if len(str(state_value)) > 100
                                                else str(state_value)
                                            )
                                            logger.info(
                                                f"StateDeltaEvent #{self.state_delta_count} for '{state_key}': "
                                                f"op=replace, path=/{state_key}, value={value_preview}"
                                            )
                                        elif self.state_delta_count % 100 == 0:  # Also log every 100th
                                            logger.info(f"StateDeltaEvent #{self.state_delta_count} emitted")

                                        events.append(state_delta_event)

                                        # Track what we emitted
                                        self.last_emitted_state[state_key] = state_value
                                        self.pending_state_updates[state_key] = state_value

                    # Legacy predictive state check (for when arguments are complete)
                    if content.name and content.arguments:
                        parsed_args = content.parse_arguments()

                        if parsed_args:
                            logger.info(f"Checking predict_state_config: {self.predict_state_config}")
                            for state_key, config in self.predict_state_config.items():
                                logger.info(f"Checking state_key='{state_key}', config={config}")
                                if config["tool"] == content.name:
                                    tool_arg_name = config["tool_argument"]
                                    logger.info(
                                        f"MATCHED tool '{content.name}' for state key '{state_key}', arg='{tool_arg_name}'"
                                    )

                                    # If tool_argument is "*", use all arguments as the state value
                                    if tool_arg_name == "*":
                                        state_value = parsed_args
                                        logger.info(f"Using all args as state value, keys: {list(state_value.keys())}")
                                    elif tool_arg_name in parsed_args:
                                        state_value = parsed_args[tool_arg_name]
                                        logger.info(f"Using specific arg '{tool_arg_name}' as state value")
                                    else:
                                        logger.warning(f"Tool argument '{tool_arg_name}' not found in parsed args")
                                        continue

                                    # Emit predictive delta (JSON Patch format)
                                    state_delta_event = StateDeltaEvent(
                                        delta=[
                                            {
                                                "op": "replace",  # Use replace since field exists in schema
                                                "path": f"/{state_key}",  # JSON Pointer path with leading slash
                                                "value": state_value,
                                            }
                                        ],
                                    )
                                    logger.info(
                                        f"Emitting StateDeltaEvent for key '{state_key}', value type: {type(state_value)}"
                                    )
                                    events.append(state_delta_event)

                                    # Track pending update for later snapshot
                                    self.pending_state_updates[state_key] = state_value

                # Note: ToolCallEndEvent is emitted when we receive FunctionResultContent,
                # not here during streaming, since we don't know when the stream is complete

            elif isinstance(content, FunctionResultContent):
                # First emit ToolCallEndEvent to close the tool call
                if content.call_id:
                    end_event = ToolCallEndEvent(
                        tool_call_id=content.call_id,
                    )
                    logger.info(f"Emitting ToolCallEndEvent for completed tool call '{content.call_id}'")
                    events.append(end_event)
                    self.tool_calls_ended.add(content.call_id)  # Track that we emitted end event

                    # Log total StateDeltaEvent count for this tool call
                    if self.state_delta_count > 0:
                        logger.info(
                            f"Tool call '{content.call_id}' complete: emitted {self.state_delta_count} StateDeltaEvents total"
                        )

                    # Reset streaming accumulator and counter for next tool call
                    self.streaming_tool_args = ""
                    self.state_delta_count = 0

                # Tool result - emit ToolCallResultEvent
                result_message_id = generate_event_id()

                # Preserve structured data for backend tool rendering
                # Serialize dicts to JSON string, otherwise convert to string
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

                # Track tool result for MessagesSnapshotEvent
                # AG-UI protocol expects: { role: "tool", toolCallId: ..., content: ... }
                # Use camelCase for Pydantic's alias_generator=to_camel
                self.tool_results.append(
                    {
                        "id": result_message_id,
                        "role": "tool",
                        "toolCallId": content.call_id,
                        "content": result_content,
                    }
                )

                # Emit MessagesSnapshotEvent with the complete conversation including tool calls and results
                # This is required for CopilotKit's useCopilotAction to detect tool result
                if self.pending_tool_calls and self.tool_results:
                    # Import message adapter
                    from ._message_adapters import agent_framework_messages_to_agui

                    # Build assistant message with tool_calls
                    assistant_message = {
                        "id": generate_event_id(),
                        "role": "assistant",
                        "tool_calls": self.pending_tool_calls.copy(),  # Copy the accumulated tool calls
                    }

                    # Convert Agent Framework messages to AG-UI format (adds required 'id' field)
                    converted_input_messages = agent_framework_messages_to_agui(self.input_messages)

                    # Build complete messages array: input messages + assistant message + tool results
                    all_messages = converted_input_messages + [assistant_message] + self.tool_results.copy()

                    # Emit MessagesSnapshotEvent using the proper event type
                    # Note: messages are dict[str, Any] but Pydantic will validate them as Message types
                    messages_snapshot_event = MessagesSnapshotEvent(
                        type=EventType.MESSAGES_SNAPSHOT,
                        messages=all_messages,  # type: ignore[arg-type]
                    )
                    logger.info(f"Emitting MessagesSnapshotEvent with {len(all_messages)} messages")
                    events.append(messages_snapshot_event)

                # After tool execution, emit StateSnapshotEvent if we have pending state updates
                if self.pending_state_updates:
                    # Update the current state with pending updates
                    for key, value in self.pending_state_updates.items():
                        self.current_state[key] = value

                    # Log the state structure for debugging
                    logger.info(f"Emitting StateSnapshotEvent with keys: {list(self.current_state.keys())}")
                    if "recipe" in self.current_state:
                        recipe = self.current_state["recipe"]
                        logger.info(
                            f"Recipe fields: title={recipe.get('title')}, "
                            f"skill_level={recipe.get('skill_level')}, "
                            f"ingredients_count={len(recipe.get('ingredients', []))}, "
                            f"instructions_count={len(recipe.get('instructions', []))}"
                        )

                    # Emit complete state snapshot
                    state_snapshot_event = StateSnapshotEvent(
                        snapshot=self.current_state,
                    )
                    events.append(state_snapshot_event)

                    # Check if this was a predictive state update tool (e.g., write_document_local)
                    # If so, emit a confirm_changes tool call for the UI modal
                    tool_was_predictive = False
                    logger.debug(
                        f"Checking predictive state: current_tool='{self.current_tool_call_name}', "
                        f"predict_config={list(self.predict_state_config.keys()) if self.predict_state_config else 'None'}"
                    )
                    for state_key, config in self.predict_state_config.items():
                        # Check if this tool call matches a predictive config
                        # We need to match against self.current_tool_call_name
                        if self.current_tool_call_name and config["tool"] == self.current_tool_call_name:
                            logger.info(
                                f"Tool '{self.current_tool_call_name}' matches predictive config for state key '{state_key}'"
                            )
                            tool_was_predictive = True
                            break

                    if tool_was_predictive and self.require_confirmation:
                        # Emit confirm_changes tool call sequence
                        confirm_call_id = generate_event_id()

                        logger.info("Emitting confirm_changes tool call for predictive update")

                        # Track confirm_changes tool call for MessagesSnapshotEvent (so it persists after RUN_FINISHED)
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

                        # Start the confirm_changes tool call
                        confirm_start = ToolCallStartEvent(
                            tool_call_id=confirm_call_id,
                            tool_call_name="confirm_changes",
                        )
                        events.append(confirm_start)

                        # Empty args for confirm_changes
                        confirm_args = ToolCallArgsEvent(
                            tool_call_id=confirm_call_id,
                            delta="{}",
                        )
                        events.append(confirm_args)

                        # End the confirm_changes tool call
                        confirm_end = ToolCallEndEvent(
                            tool_call_id=confirm_call_id,
                        )
                        events.append(confirm_end)

                        # Emit MessagesSnapshotEvent so confirm_changes persists after RUN_FINISHED
                        # Import message adapter
                        from ._message_adapters import agent_framework_messages_to_agui

                        # Build assistant message with pending confirm_changes tool call
                        assistant_message = {
                            "id": generate_event_id(),
                            "role": "assistant",
                            "tool_calls": self.pending_tool_calls.copy(),  # Includes confirm_changes
                        }

                        # Convert Agent Framework messages to AG-UI format (adds required 'id' field)
                        converted_input_messages = agent_framework_messages_to_agui(self.input_messages)

                        # Build complete messages array: input messages + assistant message + any tool results
                        all_messages = converted_input_messages + [assistant_message] + self.tool_results.copy()

                        # Emit MessagesSnapshotEvent
                        # Note: messages are dict[str, Any] but Pydantic will validate them as Message types
                        messages_snapshot_event = MessagesSnapshotEvent(
                            type=EventType.MESSAGES_SNAPSHOT,
                            messages=all_messages,  # type: ignore[arg-type]
                        )
                        logger.info(
                            f"Emitting MessagesSnapshotEvent for confirm_changes with {len(all_messages)} messages"
                        )
                        events.append(messages_snapshot_event)

                        # Set flag to stop the run after this - we're waiting for user response
                        self.should_stop_after_confirm = True
                        logger.info("Set flag to stop run after confirm_changes")
                    elif tool_was_predictive:
                        logger.info("Skipping confirm_changes - require_confirmation is False")

                    # Clear pending updates and reset tool name tracker
                    self.pending_state_updates.clear()
                    self.last_emitted_state.clear()
                    self.current_tool_call_name = None  # Reset for next tool call

            elif isinstance(content, FunctionApprovalRequestContent):
                # Human in the loop - function approval request
                logger.info("=== FUNCTION APPROVAL REQUEST ===")
                logger.info(f"  Function: {content.function_call.name}")
                logger.info(f"  Call ID: {content.function_call.call_id}")

                # Parse the arguments to extract state for predictive UI updates
                parsed_args = content.function_call.parse_arguments()
                logger.info(f"  Parsed args keys: {list(parsed_args.keys()) if parsed_args else 'None'}")

                # Check if this matches our predict_state_config and emit state
                if parsed_args and self.predict_state_config:
                    logger.info(f"  Checking predict_state_config: {self.predict_state_config}")
                    for state_key, config in self.predict_state_config.items():
                        if config["tool"] == content.function_call.name:
                            tool_arg_name = config["tool_argument"]
                            logger.info(
                                f"  MATCHED tool '{content.function_call.name}' for state key '{state_key}', arg='{tool_arg_name}'"
                            )

                            # Extract the state value
                            if tool_arg_name == "*":
                                state_value = parsed_args
                            elif tool_arg_name in parsed_args:
                                state_value = parsed_args[tool_arg_name]
                            else:
                                logger.warning(f"  Tool argument '{tool_arg_name}' not found in parsed args")
                                continue

                            # Update current state
                            self.current_state[state_key] = state_value
                            logger.info(
                                f"Emitting StateSnapshotEvent for key '{state_key}', value type: {type(state_value)}"
                            )

                            # Emit state snapshot
                            state_snapshot = StateSnapshotEvent(
                                snapshot=self.current_state,
                            )
                            events.append(state_snapshot)

                # The tool call has been streamed already (Start/Args events)
                # Now we need to close it with an End event before the agent waits for approval
                if content.function_call.call_id:
                    end_event = ToolCallEndEvent(
                        tool_call_id=content.function_call.call_id,
                    )
                    logger.info(
                        f"Emitting ToolCallEndEvent for approval-required tool '{content.function_call.call_id}'"
                    )
                    events.append(end_event)
                    self.tool_calls_ended.add(content.function_call.call_id)  # Track that we emitted end event

                # Emit custom event for approval request
                # Note: In AG-UI protocol, the frontend handles interrupts automatically
                # when it sees a tool call with the configured name (via predict_state_config)
                # This custom event is for additional metadata if needed
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
