# Copyright (c) Microsoft. All rights reserved.

"""Cua integration for Microsoft Agent Framework.

This package provides seamless integration between Agent Framework and Cua,
enabling AI agents to control desktop applications across Windows, macOS, and Linux.

Key Features:
    - 100+ model support (OpenAI, Anthropic, OpenCUA, InternVL, UI-Tars, etc.)
    - Composite agents (combine grounding + planning models)
    - Cross-platform VM support
    - Human-in-the-loop approval workflows

Examples:
    Basic usage with Anthropic Claude:

    >>> from agent_framework import ChatAgent
    >>> from agent_framework_cua import CuaAgentMiddleware
    >>> from computer import Computer
    >>>
    >>> async with Computer(os_type="linux", provider_type="docker") as computer:
    ...     middleware = CuaAgentMiddleware(
    ...         computer=computer,
    ...         model="anthropic/claude-sonnet-4-5-20250929",
    ...         instructions="You are a desktop automation assistant.",
    ...     )
    ...
    ...     agent = ChatAgent(
    ...         middleware=[middleware],
    ...     )
    ...
    ...     response = await agent.run("Open Firefox")

    Using composite agents:

    >>> middleware = CuaAgentMiddleware(
    ...     computer=computer,
    ...     model="huggingface-local/UI-TARS+openai/gpt-4o",
    ... )
"""

from ._middleware import CuaAgentMiddleware

__all__ = [
    "CuaAgentMiddleware",
]
