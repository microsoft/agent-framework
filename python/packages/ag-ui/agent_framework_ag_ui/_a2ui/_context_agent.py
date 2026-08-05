# Copyright (c) Microsoft. All rights reserved.

"""AGUIContextAgent — surface forwarded AG-UI context to the model.

The AG-UI hosting layer hands the ag-ui context slice (component catalog schema +
usage guidelines) to this wrapper directly at construction. This wrapper renders that
slice as a system message via the toolkit's ``build_context_prompt`` and prepends it,
so a plain chat agent can render A2UI surfaces with no further setup.

The slice is NOT read from run-option ``additional_properties``: stamping it there put
it on the request options, which the provider SDK rejects as an unknown option, and it
leaked to the provider on any run that supplied AG-UI context. Passing the slice in
directly keeps it off the wire.
"""

from __future__ import annotations

from typing import Any

from ag_ui_a2ui_toolkit import build_context_prompt
from agent_framework import Content, Message, normalize_messages


class AGUIContextAgent:
    """Wraps an agent, prepending forwarded AG-UI context as a system message.

    Transparent pass-through: ``run`` returns whatever the inner agent's ``run``
    returns (an awaitable for non-streaming, an async iterable for streaming), so it
    composes with the AG-UI hosting loop and with ``A2UIAgent`` without caring which
    mode is in play.
    """

    def __init__(self, inner_agent: Any, context_slice: dict[str, Any] | None = None) -> None:
        """Initialize the wrapper.

        Args:
            inner_agent: The agent to wrap (any ``SupportsAgentRun``).
            context_slice: The forwarded ``ag-ui`` context slice for this run (catalog +
                guidelines), or ``None`` when there is no context to surface.
        """
        self.inner_agent = inner_agent
        self._context_slice = context_slice or {}
        # Mirror identity so the wrapper is indistinguishable to the hosting layer.
        self.id = getattr(inner_agent, "id", None)
        self.name = getattr(inner_agent, "name", None)
        self.description = getattr(inner_agent, "description", None)

    def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        """Prepend the context system message and delegate to the inner agent."""
        return self.inner_agent.run(
            self._with_context_prompt(messages),
            stream=stream,
            **kwargs,
        )

    def _with_context_prompt(self, messages: Any) -> list[Message]:
        normalized = normalize_messages(messages)
        if not self._context_slice:
            return normalized
        prompt = build_context_prompt({"ag-ui": self._context_slice})
        if not prompt:
            return normalized
        system = Message(role="system", contents=[Content.from_text(text=prompt)])
        return [system, *normalized]
