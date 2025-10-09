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
    >>> async with Computer(os_type="macos", provider_type="lume") as computer:
    ...     middleware = CuaAgentMiddleware(
    ...         computer=computer,
    ...         model="anthropic/claude-3-5-sonnet-20241022",
    ...     )
    ...
    ...     agent = ChatAgent(
    ...         middleware=[middleware],
    ...         instructions="You are a desktop automation assistant.",
    ...     )
    ...
    ...     response = await agent.run("Open Safari")

    Using composite agents:

    >>> middleware = CuaAgentMiddleware(
    ...     computer=computer,
    ...     model="huggingface-local/UI-TARS+openai/gpt-4o",
    ... )
"""

from ._middleware import CuaAgentMiddleware
from ._types import (
    CuaModelId,
    CuaOSType,
    CuaProviderType,
    CuaResult,
    CuaStep,
)

__all__ = [
    "CuaAgentMiddleware",
    "CuaModelId",
    "CuaOSType",
    "CuaProviderType",
    "CuaResult",
    "CuaStep",
]
