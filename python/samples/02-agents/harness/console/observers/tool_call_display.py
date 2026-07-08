# Copyright (c) Microsoft. All rights reserved.

"""Tool call display observer using formatters."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..formatters import build_default_formatters, format_tool_call
from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent, Content

    from ..app_state import FollowUpAction
    from ..formatters import ToolCallFormatter
    from ..state_driver import IUXStateDriver


class ToolCallDisplayObserver(ConsoleObserver):
    """Displays tool call notifications using formatters.

    Shows tool calls with a 🔧 prefix and uses the formatter system to
    display them in a user-friendly format.

    Streaming clients (e.g. the OpenAI/Foundry Responses API) emit a separate
    ``function_call`` content item for every ``arguments`` delta — each sharing
    the same ``call_id`` and ``name`` but carrying only a partial fragment of the
    JSON arguments. Printing one line per content item therefore repeats a single
    tool call many times (scaling with argument size). To avoid that, this
    observer buffers the argument fragments per ``call_id`` and emits exactly one
    line once the accumulated arguments are complete (i.e. parse as valid JSON,
    or arrive already-coalesced as a mapping). Any call that never reaches a
    complete state is flushed when streaming completes.
    """

    def __init__(self, formatters: list[ToolCallFormatter] | None = None) -> None:
        """Initialize the tool call display observer.

        Args:
            formatters: Optional list of tool formatters. If None, uses
                default formatters from build_default_formatters().
        """
        self._formatters = formatters or build_default_formatters()
        # call_id -> {"name": str, "arguments": str | dict}
        self._pending: dict[str, dict[str, Any]] = {}
        # call_ids already displayed in the current stream (avoid duplicates).
        self._displayed: set[str] = set()

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Buffer streamed function-call fragments and display each call once.

        Args:
            ux: The UX state driver for UI updates.
            content: The content item to check for function calls.
            agent: The AI agent.
            session: The agent session.
        """
        if content.type != "function_call":
            return

        # Streamed fragments are coalesced by call_id. If a provider omits the
        # call_id, fragments cannot be reliably grouped, so fall back to the
        # original behavior — display the item as-is — rather than risk merging
        # (and then dropping) distinct calls under a shared synthetic key.
        call_id = content.call_id
        if not call_id:
            self._display(ux, content)
            return

        if call_id in self._displayed:
            return

        entry = self._pending.setdefault(call_id, {"name": content.name, "arguments": ""})
        if content.name and not entry["name"]:
            entry["name"] = content.name

        args = content.arguments
        if isinstance(args, str):
            # Streaming delta fragment — concatenate.
            entry["arguments"] = (entry["arguments"] or "") + args
        elif args is not None:
            # Already-coalesced arguments (e.g. a mapping) — use directly.
            entry["arguments"] = args

        if self._is_complete(entry["arguments"]):
            self._flush(ux, call_id)

    async def on_stream_complete(
        self,
        ux: IUXStateDriver,
        agent: Agent,
        session: Any,
    ) -> list[FollowUpAction] | None:
        """Flush buffered calls that never reached a complete state, then reset.

        Args:
            ux: The UX state driver for UI updates.
            agent: The AI agent.
            session: The agent session.

        Returns:
            Always None; this observer produces no follow-up actions.
        """
        for call_id in list(self._pending):
            self._flush(ux, call_id)
        self._pending.clear()
        self._displayed.clear()
        return None

    @staticmethod
    def _is_complete(arguments: Any) -> bool:
        """Return True when the accumulated arguments form a complete payload.

        A mapping is already complete. A string is complete once it parses as
        JSON (partial fragments of a streamed JSON object will not parse until
        the closing brace arrives; a no-argument call streams ``"{}"`` which
        parses immediately).
        """
        if isinstance(arguments, str):
            stripped = arguments.strip()
            if not stripped:
                return False
            # Cheap structural gate: a complete JSON object/array opens and
            # closes with matching brackets. This rejects growing partial
            # fragments in O(1) so json.loads only runs on a plausibly-complete
            # payload, avoiding O(n^2) re-parsing across many streamed deltas.
            if not ((stripped[0] == "{" and stripped[-1] == "}") or (stripped[0] == "[" and stripped[-1] == "]")):
                return False
            try:
                json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                return False
            return True
        # Non-string (mapping / None handled by caller) is treated as complete.
        return arguments is not None

    def _flush(self, ux: IUXStateDriver, call_id: str) -> None:
        """Format and display a buffered call exactly once."""
        entry = self._pending.pop(call_id, None)
        if entry is None or call_id in self._displayed:
            return
        self._displayed.add(call_id)

        from agent_framework import Content

        # Preserve an empty mapping ("{}") as-is; only treat an empty *string*
        # (no arguments were ever streamed) as "no arguments".
        arguments = entry["arguments"]
        if arguments == "":
            arguments = None

        call = Content.from_function_call(
            call_id=call_id,
            name=entry["name"] or "Unknown",
            arguments=arguments,
        )
        self._display(ux, call)

    def _display(self, ux: IUXStateDriver, call: Content) -> None:
        """Format and write a single tool-call line."""
        formatted = format_tool_call(self._formatters, call)
        ux.append_info_line(f"🔧 {formatted}", "yellow")
