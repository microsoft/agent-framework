# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar

from agent_framework.model_client import ChatMessage, ChatResponse, ChatResponseUpdate

# These are only skeletons for the guardrail types.
TInputMessage = TypeVar("TInputMessage", bound=ChatMessage, covariant=True)
TResponse = TypeVar("TResponse", bound=ChatResponse | Sequence[ChatResponseUpdate], covariant=True)


class InputGuardrail(Protocol, Generic[TInputMessage]):
    """A protocol for input guardrails that can validate and transform input messages."""

    ...


class OutputGuardrail(Protocol, Generic[TResponse]):
    """A protocol for output guardrails that can validate and transform output messages."""

    ...
