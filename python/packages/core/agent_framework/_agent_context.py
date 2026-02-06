# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._middleware import AgentContext

__all__ = [
    "get_current_agent_run_context",
]

_current_agent_run_context: ContextVar[AgentContext | None] = ContextVar("agent_run_context", default=None)


def get_current_agent_run_context() -> AgentContext | None:
    """Get the current agent run context, if any.

    Returns the AgentContext for the currently executing agent run,
    or None if called outside of an agent run. This enables sub-agents
    (invoked as tools) to access their parent agent's run context.

    Returns:
        The current AgentContext, or None if not within an agent run.

    Examples:
        .. code-block:: python

            from agent_framework import get_current_agent_run_context


            @tool
            async def my_tool() -> str:
                parent_ctx = get_current_agent_run_context()
                if parent_ctx and parent_ctx.thread:
                    # Access parent's conversation_id
                    conv_id = parent_ctx.thread.service_thread_id
                return "done"
    """
    return _current_agent_run_context.get()


@contextmanager
def agent_run_scope(context: AgentContext) -> Iterator[None]:
    """Context manager to set the agent run context for the duration of a block.

    This is used internally by the agent framework to establish the current
    run context. The context is automatically restored when the block exits.

    Args:
        context: The AgentContext to set as current.
    """
    token = _current_agent_run_context.set(context)
    try:
        yield
    finally:
        _current_agent_run_context.reset(token)
