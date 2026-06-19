# Copyright (c) Microsoft. All rights reserved.

"""Web search display observer for showing search activity in the console.

Displays web search activity as it streams in from the API, showing search
queries, page opens, and find-in-page actions with 🌐 prefix.

The actual details (queries, URLs, sources) come from the ``search_tool_result``
content emitted when the search completes (``response.output_item.done``).
The initial ``search_tool_call`` is emitted when the item is first added and
typically has an empty or incomplete action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape

from .base import ConsoleObserver

if TYPE_CHECKING:
    from agent_framework import Agent, Content

    from ..state_driver import IUXStateDriver

_MAX_QUERY_DISPLAY_LENGTH = 120


class WebSearchDisplayObserver(ConsoleObserver):
    """Displays web search activity in the scroll area.

    Shows search queries, page opens, and find-in-page actions. Details are
    extracted from ``search_tool_result`` content (the completed action), which
    contains the full action type, queries, URLs, and sources.
    """

    async def on_content(
        self,
        ux: IUXStateDriver,
        content: Content,
        agent: Agent,
        session: Any,
    ) -> None:
        """Display web search activity from search content items.

        Args:
            ux: The UX state driver for UI updates.
            content: The content item to check for search activity.
            agent: The AI agent.
            session: The agent session.
        """
        if content.type == "search_tool_result":
            self._display_search_result(ux, content)

    def _display_search_result(self, ux: IUXStateDriver, content: Content) -> None:
        """Display a completed search tool result with action details."""
        tool_name = getattr(content, "tool_name", None) or "web_search"
        if tool_name != "web_search":
            return

        result = getattr(content, "result", None)
        if not isinstance(result, dict):
            ux.append_info_line("🌐 Web Search", "cyan")
            return

        action = result.get("action")
        if not isinstance(action, dict):
            ux.append_info_line("🌐 Web Search", "cyan")
            return

        action_type = action.get("type")

        if action_type == "search":
            self._display_search_action(ux, action)
        elif action_type == "open_page":
            self._display_open_page_action(ux, action)
        elif action_type == "find_in_page":
            self._display_find_in_page_action(ux, action)
        else:
            ux.append_info_line("🌐 Web Search", "cyan")

    def _display_search_action(self, ux: IUXStateDriver, action: dict) -> None:
        """Display a search action with queries and optional sources."""
        queries = action.get("queries") or []
        if not queries:
            # Fall back to the single "query" field
            query = action.get("query")
            if query:
                queries = [query]

        if not queries:
            ux.append_info_line("🌐 Web Search: search", "cyan")
            return

        sources = action.get("sources") or []
        has_sources = len(sources) > 0

        lines = ["🌐 Web Search: search"]
        for i, query in enumerate(queries):
            connector = "├─" if (i < len(queries) - 1 or has_sources) else "└─"
            query_text = escape(_truncate(str(query), _MAX_QUERY_DISPLAY_LENGTH))
            lines.append(f'\n   {connector} "{query_text}"')

        if has_sources:
            lines.append("\n   │")
            for i, source in enumerate(sources):
                connector = "├─" if i < len(sources) - 1 else "└─"
                line = _format_source(source)
                lines.append(f"\n   {connector} {line}")

        ux.append_info_line("".join(lines), "cyan")

    def _display_open_page_action(self, ux: IUXStateDriver, action: dict) -> None:
        """Display an open page action."""
        url = escape(str(action.get("url") or "(unknown)"))
        ux.append_info_line(
            f"🌐 Web Search: open page\n   └─ {url}",
            "cyan",
        )

    def _display_find_in_page_action(self, ux: IUXStateDriver, action: dict) -> None:
        """Display a find-in-page action."""
        url = escape(str(action.get("url") or "(unknown)"))
        pattern = escape(_truncate(str(action.get("pattern") or "(unknown)"), _MAX_QUERY_DISPLAY_LENGTH))
        ux.append_info_line(
            f'🌐 Web Search: find in page\n   ├─ "{pattern}"\n   └─ {url}',
            "cyan",
        )


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    return text if len(text) <= max_length else text[: max_length - 1] + "…"


def _format_source(source: Any) -> str:
    """Format a source entry for display."""
    if isinstance(source, dict):
        url = escape(str(source.get("url") or source.get("uri") or "(unknown)"))
        title = source.get("title")
        if title:
            return f"{escape(_truncate(str(title), _MAX_QUERY_DISPLAY_LENGTH))} — {url}"
        return url
    return escape(str(source))
