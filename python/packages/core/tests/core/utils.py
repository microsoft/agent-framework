# Copyright (c) Microsoft. All rights reserved.


from collections.abc import AsyncIterable
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
)

TERMINATION_TEXT = "Sorry, blocked."


def termination_result(kind: str, stream: bool) -> Any:
    """The response a middleware hands to ``MiddlewareTermination(result=...)``."""
    if kind == "agent":
        if not stream:
            return AgentResponse(messages=[Message(role="assistant", contents=[TERMINATION_TEXT])])

        async def _agent_updates() -> AsyncIterable[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text(TERMINATION_TEXT)], role="assistant")

        return ResponseStream(_agent_updates(), finalizer=AgentResponse.from_updates)
    if not stream:
        return ChatResponse(messages=[Message(role="assistant", contents=[TERMINATION_TEXT])])

    async def _chat_updates() -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(contents=[Content.from_text(TERMINATION_TEXT)], role="assistant")

    return ResponseStream(_chat_updates(), finalizer=ChatResponse.from_updates)


class CopyingMock(MagicMock):
    def __call__(self, *args, **kwargs):
        args = deepcopy(args)
        kwargs = deepcopy(kwargs)
        return super().__call__(*args, **kwargs)
