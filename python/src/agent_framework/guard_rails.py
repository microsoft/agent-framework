# Copyright (c) Microsoft. All rights reserved.


from typing import Generic, Protocol, runtime_checkable

from ._types import TInput, TResponse


@runtime_checkable
class InputGuardrail(Protocol, Generic[TInput]):
    """A protocol for input guardrails that can validate and transform input messages."""

    def __call__(self, message: TInput) -> TInput:
        """Validate and possibly transform the input message."""
        ...


@runtime_checkable
class OutputGuardrail(Protocol, Generic[TResponse]):
    """A protocol for output guardrails that can validate and transform output messages."""

    def __call__(self, message: TResponse) -> TResponse:
        """Validate and possibly transform the output message."""
        ...
