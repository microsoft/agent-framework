# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import copy
import sys
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, ClassVar, Generic

from .._clients import BaseChatClient
from .._middleware import ChatAndFunctionMiddlewareTypes, ChatMiddlewareLayer
from .._tools import FunctionInvocationConfiguration, FunctionInvocationLayer
from .._types import (
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    ResponseStream,
)
from ..exceptions import ChatClientInvalidRequestException
from ..observability import ChatTelemetryLayer
from pydantic import BaseModel

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover


__all__ = ["FakeChatClient", "FakeChatOptions"]

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)

FakeResponseItem = str | Message | ChatResponse


class FakeChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Fake-model options used by FakeChatClient.

    Keys:
        model: Optional model name override for this request.
        response: Optional one-off response that overrides queued responses.
        cycle: Optional per-request override for cycling behavior.
    """

    response: FakeResponseItem
    cycle: bool


class FakeChatClient(
    FunctionInvocationLayer[FakeChatOptions],
    ChatMiddlewareLayer[FakeChatOptions],
    ChatTelemetryLayer[FakeChatOptions],
    BaseChatClient[FakeChatOptions],
):
    """Deterministic fake chat client useful for tests and local demos."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "fake"

    def __init__(
        self,
        *,
        responses: Sequence[FakeResponseItem],
        model: str = "fake-model",
        cycle: bool = False,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        """Initialize a fake chat client.

        Keyword Args:
            responses: Ordered fake responses returned on successive calls.
            model: Default model name used in generated responses.
            cycle: Whether responses should wrap to the beginning when exhausted.
                   When False, an error is always raised once the list is exhausted.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
        """
        super().__init__(
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )
        self.model = model
        self._responses = list(responses)
        self._response_index = 0
        self._cycle = cycle

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del kwargs

        response = self._select_response(messages=messages, options=options)
        if stream:
            return self._to_stream(response)

        async def _get_response() -> ChatResponse:
            return response

        return _get_response()

    def _to_stream(self, response: ChatResponse) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            assistant_messages = [message for message in response.messages if message.role == "assistant"]
            if not assistant_messages:
                return

            for index, message in enumerate(assistant_messages):
                yield ChatResponseUpdate(
                    contents=message.contents,
                    role="assistant",
                    model=response.model,
                    created_at=response.created_at,
                    finish_reason=response.finish_reason if index == len(assistant_messages) - 1 else None,
                )

        def _finalize(_updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            return response

        return ResponseStream(_stream(), finalizer=_finalize)

    def _select_response(self, *, messages: Sequence[Message], options: Mapping[str, Any]) -> ChatResponse:

        if not messages:
            raise ChatClientInvalidRequestException("Messages are required for chat completions")

        if (single_response := options.get("response")) is not None:
            return self._materialize_response(single_response, options)

        if self._response_index >= len(self._responses):
            should_cycle = bool(options.get("cycle", self._cycle))
            if should_cycle:
                self._response_index = 0
            else:
                raise ChatClientInvalidRequestException(
                    "FakeChatClient response list is exhausted. Provide more responses or enable cycle=True."
                )

        item = self._responses[self._response_index]
        self._response_index += 1
        return self._materialize_response(item, options)

    def _materialize_response(self, value: FakeResponseItem, options: Mapping[str, Any]) -> ChatResponse:
        model = str(options.get("model") or self.model)

        if isinstance(value, ChatResponse):
            # Shallow-copy to avoid mutating the original queued item (e.g. under cycle=True).
            cloned = copy.copy(value)
            cloned.model = model
            return cloned
        if isinstance(value, Message):
            return ChatResponse(messages=[value], model=model)
        return ChatResponse(messages=[Message(role="assistant", contents=[value])], model=model)
