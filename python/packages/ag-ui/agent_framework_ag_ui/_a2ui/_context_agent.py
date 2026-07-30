# Copyright (c) Microsoft. All rights reserved.

"""AGUIContextAgent — surface forwarded AG-UI context to the model.

Port of the .NET ``AGUIContextAgent``. The AG-UI hosting layer stamps the ag-ui
context slice (component catalog schema + usage guidelines) onto the run options'
``additional_properties`` (see :mod:`._state`), where the model never sees it. This
wrapper renders that slice as a system message via the toolkit's
``build_context_prompt`` and prepends it, so a plain chat agent can render A2UI
surfaces with no further setup.
"""

from __future__ import annotations

from typing import Any

from ag_ui_a2ui_toolkit import build_context_prompt
from agent_framework import Content, Message, normalize_messages

from ._state import read_agent_state


class AGUIContextAgent:
    """Wraps an agent, prepending forwarded AG-UI context as a system message.

    Transparent pass-through: ``run`` returns whatever the inner agent's ``run``
    returns (an awaitable for non-streaming, an async iterable for streaming), so it
    composes with the AG-UI hosting loop and with ``A2UIAgent`` without caring which
    mode is in play.
    """

    def __init__(self, inner_agent: Any) -> None:
        """Initialize the wrapper.

        Args:
            inner_agent: The agent to wrap (any ``SupportsAgentRun``).
        """
        self.inner_agent = inner_agent
        # Mirror identity so the wrapper is indistinguishable to the hosting layer.
        self.id = getattr(inner_agent, "id", None)
        self.name = getattr(inner_agent, "name", None)
        self.description = getattr(inner_agent, "description", None)

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        """Prepend the context system message and delegate to the inner agent."""
        return self.inner_agent.run(
            self._with_context_prompt(messages, kwargs.get("options")),
            stream=stream,
            **kwargs,
        )

    @staticmethod
    def _with_context_prompt(messages: Any, options: Any) -> list[Message]:
        normalized = normalize_messages(messages)
        slice_ = read_agent_state(options)
        if not slice_:
            return normalized
        prompt = build_context_prompt({"ag-ui": slice_})
        if not prompt:
            return normalized
        system = Message(role="system", contents=[Content.from_text(text=prompt)])
        return [system, *normalized]
