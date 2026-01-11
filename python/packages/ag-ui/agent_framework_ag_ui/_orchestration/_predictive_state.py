# Copyright (c) Microsoft. All rights reserved.

"""Predictive state handling utilities."""

import json
import logging
import re
from typing import Any

from ag_ui.core import StateDeltaEvent

from .._utils import safe_json_parse

logger = logging.getLogger(__name__)


class PredictiveStateHandler:
    """Handles predictive state updates from streaming tool calls."""

    def __init__(
        self,
        predict_state_config: dict[str, dict[str, str]] | None = None,
        current_state: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the handler.

        Args:
            predict_state_config: Configuration mapping state keys to tool/argument pairs
            current_state: Reference to current state dict
        """
        self.predict_state_config = predict_state_config or {}
        self.current_state = current_state or {}
        self.streaming_tool_args: str = ""
        self.last_emitted_state: dict[str, Any] = {}
        self.state_delta_count: int = 0
        self.pending_state_updates: dict[str, Any] = {}

    def reset_streaming(self) -> None:
        """Reset streaming state for a new tool call."""
        self.streaming_tool_args = ""
        self.state_delta_count = 0

    def extract_state_value(
        self,
        tool_name: str,
        args: dict[str, Any] | str | None,
    ) -> tuple[str, Any] | None:
        """Extract state value from tool arguments based on config.

        Args:
            tool_name: Name of the tool being called
            args: Tool arguments (dict or JSON string)

        Returns:
            Tuple of (state_key, state_value) or None if no match
        """
        if not self.predict_state_config:
            return None

        parsed_args = safe_json_parse(args) if isinstance(args, str) else args
        if not parsed_args:
            return None

        for state_key, config in self.predict_state_config.items():
            if config["tool"] != tool_name:
                continue
            tool_arg_name = config["tool_argument"]
            if tool_arg_name == "*":
                return (state_key, parsed_args)
            if tool_arg_name in parsed_args:
                return (state_key, parsed_args[tool_arg_name])

        return None

    def is_predictive_tool(self, tool_name: str | None) -> bool:
        """Check if a tool is configured for predictive state.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is in predictive state config
        """
        if not tool_name or not self.predict_state_config:
            return False
        for config in self.predict_state_config.values():
            if config["tool"] == tool_name:
                return True
        return False

    def emit_streaming_deltas(
        self,
        tool_name: str | None,
        argument_chunk: str,
    ) -> list[StateDeltaEvent]:
        """Process streaming argument chunk and emit state deltas.

        Args:
            tool_name: Name of the current tool
            argument_chunk: New chunk of JSON arguments

        Returns:
            List of state delta events to emit
        """
        events: list[StateDeltaEvent] = []
        if not tool_name or not self.predict_state_config:
            return events

        self.streaming_tool_args += argument_chunk
        logger.debug(
            "Predictive state: accumulated %s chars for tool '%s'",
            len(self.streaming_tool_args),
            tool_name,
        )

        # Try to parse complete JSON first
        parsed_args = None
        try:
            parsed_args = json.loads(self.streaming_tool_args)
        except json.JSONDecodeError:
            # Fall back to regex matching for partial JSON
            events.extend(self._emit_partial_deltas(tool_name))

        if parsed_args:
            events.extend(self._emit_complete_deltas(tool_name, parsed_args))

        return events

    def _emit_partial_deltas(self, tool_name: str) -> list[StateDeltaEvent]:
        """Emit deltas from partial JSON using regex matching.

        Args:
            tool_name: Name of the current tool

        Returns:
            List of state delta events
        """
        events: list[StateDeltaEvent] = []

        for state_key, config in self.predict_state_config.items():
            if config["tool"] != tool_name:
                continue
            tool_arg_name = config["tool_argument"]
            pattern = rf'"{re.escape(tool_arg_name)}":\s*"([^"]*)'
            match = re.search(pattern, self.streaming_tool_args)

            if match:
                partial_value = match.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

                if state_key not in self.last_emitted_state or self.last_emitted_state[state_key] != partial_value:
                    event = self._create_delta_event(state_key, partial_value)
                    events.append(event)
                    self.last_emitted_state[state_key] = partial_value
                    self.pending_state_updates[state_key] = partial_value

        return events

    def _emit_complete_deltas(
        self,
        tool_name: str,
        parsed_args: dict[str, Any],
    ) -> list[StateDeltaEvent]:
        """Emit deltas from complete parsed JSON.

        Args:
            tool_name: Name of the current tool
            parsed_args: Fully parsed arguments dict

        Returns:
            List of state delta events
        """
        events: list[StateDeltaEvent] = []

        for state_key, config in self.predict_state_config.items():
            if config["tool"] != tool_name:
                continue
            tool_arg_name = config["tool_argument"]

            if tool_arg_name == "*":
                state_value = parsed_args
            elif tool_arg_name in parsed_args:
                state_value = parsed_args[tool_arg_name]
            else:
                continue

            if state_key not in self.last_emitted_state or self.last_emitted_state[state_key] != state_value:
                event = self._create_delta_event(state_key, state_value)
                events.append(event)
                self.last_emitted_state[state_key] = state_value
                self.pending_state_updates[state_key] = state_value

        return events

    def _create_delta_event(self, state_key: str, value: Any) -> StateDeltaEvent:
        """Create a state delta event with logging.

        Args:
            state_key: The state key being updated
            value: The new value

        Returns:
            StateDeltaEvent instance
        """
        self.state_delta_count += 1
        if self.state_delta_count % 10 == 1:
            logger.info(
                "StateDeltaEvent #%s for '%s': op=replace, path=/%s, value_length=%s",
                self.state_delta_count,
                state_key,
                state_key,
                len(str(value)),
            )
        elif self.state_delta_count % 100 == 0:
            logger.info(f"StateDeltaEvent #{self.state_delta_count} emitted")

        return StateDeltaEvent(
            delta=[
                {
                    "op": "replace",
                    "path": f"/{state_key}",
                    "value": value,
                }
            ],
        )

    def apply_pending_updates(self) -> None:
        """Apply pending updates to current state and clear them."""
        for key, value in self.pending_state_updates.items():
            self.current_state[key] = value
        self.pending_state_updates.clear()
