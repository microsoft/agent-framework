# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Generic, Protocol, Sequence, TypeVar

from agent_framework.model_client import ChatMessage, ChatResponse, ChatResponseUpdate

# These are only skeletons for the guardrail types.
TInputMessages = TypeVar("TInputMessage", bound=Sequence[ChatMessage])
TResponse = TypeVar("TResponse", bound=ChatResponse | Sequence[ChatResponseUpdate])


class InputGuardrail(Protocol, Generic[TInputMessages]):
    """A protocol for input guardrails that can validate and transform input messages."""
    ...


class OutputGuardrail(Protocol, Generic[TResponse]):
    """A protocol for output guardrails that can validate and transform output messages."""
    ...
