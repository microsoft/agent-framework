# Copyright (c) Microsoft. All rights reserved.

"""FakeChatClient for testing and demo usage without model dependency.

Provides a deterministic chat client that returns pre-configured responses,
useful for unit testing, integration testing, and demo scenarios.
"""

from __future__ import annotations

import asyncio
import itertools
import sys
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, ClassVar

from ._clients import BaseChatClient, ResponseStream
from ._types import ChatResponse, ChatResponseUpdate, Content, Message

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore[import-untyped]
else:
    from typing_extensions import override  # type: ignore[import-untyped]


__all__ = ["FakeChatClient"]


class FakeChatClient(BaseChatClient):
    """A deterministic chat client that returns pre-configured responses.

    Useful for testing, demos, and development without requiring a real model.
    Supports both streaming and non-streaming responses.

    The client cycles through the provided responses. When all responses have
    been consumed, it repeats the last response by default. Set ``repeat`` to
    ``"last"`` (default) to repeat the last response, or ``"loop"`` to cycle
    from the beginning.

    Examples:
        Non-streaming usage::

            from agent_framework import FakeChatClient, Message

            client = FakeChatClient(responses=["Hello!", "How can I help?"])
            response = await client.get_response([Message(role="user", contents=["Hi"])])
            assert response.text == "Hello!"

        Streaming usage::

            async for update in client.get_response(
                [Message(role="user", contents=["Hi"])],
                stream=True,
            ):
                print(update.text, end="")

        With an Agent::

            from agent_framework import Agent

            agent = Agent(
                client=client,
                name="TestAgent",
                instructions="You are a test assistant.",
            )
            result = await agent.run("Hello")
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "FakeChatClient"

    def __init__(
        self,
        *,
        responses: Sequence[str | Message | ChatResponse] | None = None,
        repeat: str = "last",
        stream_delay_seconds: float = 0.0,
        **kwargs: Any,
    ) -> None:
        """Initialize the FakeChatClient.

        Args:
            responses: A sequence of pre-configured responses. Each item can be:
                - A string (converted to an assistant Message).
                - A Message object.
                - A ChatResponse object (used as-is).
                Defaults to a single "Hello!" response if not provided.
            repeat: What to do when responses are exhausted.
                - "last": Repeat the last response (default).
                - "loop": Cycle through responses from the beginning.
            stream_delay_seconds: Delay between streaming chunks in seconds.
                Defaults to 0.0 (no delay).
            **kwargs: Additional keyword arguments passed to BaseChatClient.

        Raises:
            ValueError: If repeat is not "last" or "loop", or if responses is empty.
        """
        super().__init__(**kwargs)
        if repeat not in ("last", "loop"):
            raise ValueError(f"repeat must be 'last' or 'loop', got {repeat!r}")
        self._repeat = repeat
        self._stream_delay_seconds = stream_delay_seconds
        self._call_count = 0

        if responses is None:
            responses = ["Hello!"]
        elif len(responses) == 0:
            raise ValueError("responses must not be empty")

        self._responses: list[ChatResponse] = []
        for r in responses:
            if isinstance(r, ChatResponse):
                self._responses.append(r)
            elif isinstance(r, Message):
                self._responses.append(ChatResponse(messages=[r], model="fake-model"))
            else:
                self._responses.append(
                    ChatResponse(
                        messages=[Message(role="assistant", contents=[r])],
                        model="fake-model",
                    )
                )

        self._iterator: itertools.cycle | None = None
        if repeat == "loop":
            self._iterator = itertools.cycle(self._responses)

    @property
    def call_count(self) -> int:
        """The number of times get_response has been called."""
        return self._call_count

    def _get_next_response(self) -> ChatResponse:
        """Get the next response based on the repeat strategy."""
        if self._repeat == "loop" and self._iterator is not None:
            return next(self._iterator)  # type: ignore[arg-type]

        # "last" mode: cycle through then repeat last
        if self._call_count <= len(self._responses):
            return self._responses[self._call_count - 1]
        return self._responses[-1]

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self._call_count += 1
        response = self._get_next_response()

        if not stream:

            async def _get_response() -> ChatResponse:
                return response

            return _get_response()

        # Streaming: split the response text into character-level chunks
        response_text = ""
        if response.messages:
            response_text = response.messages[-1].text or ""

        # Propagate metadata from the configured response
        response_id = response.response_id
        model = response.model or "fake-model"

        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            for char in response_text:
                yield ChatResponseUpdate(
                    contents=[Content.from_text(char)],
                    role="assistant",
                    response_id=response_id,
                    model=model,
                )
                if self._stream_delay_seconds > 0:
                    await asyncio.sleep(self._stream_delay_seconds)

        return ResponseStream(
            _stream(),
            finalizer=lambda updates: response,
        )
