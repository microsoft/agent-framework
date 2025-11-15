# Copyright (c) Microsoft. All rights reserved.

"""Callback interfaces for Durable Agent executions.

This module enables callers of AgentFunctionApp to supply streaming and final-response callbacks that are
invoked during durable entity execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_framework import AgentRunResponse, AgentRunResponseUpdate


@dataclass(frozen=True)
class AgentCallbackContext:
    """Context supplied to callback invocations."""

    agent_name: str
    correlation_id: str
    thread_id: str | None = None
    request_message: str | None = None


class AgentResponseCallbackProtocol(Protocol):
    """Protocol describing the callbacks invoked during agent execution."""

    async def on_streaming_response_update(
        self,
        update: AgentRunResponseUpdate,
        context: AgentCallbackContext,
    ) -> None:
        """Handle a streaming response update emitted by the agent."""

    async def on_agent_response(
        self,
        response: AgentRunResponse,
        context: AgentCallbackContext,
    ) -> None:
        """Handle the final agent response."""
