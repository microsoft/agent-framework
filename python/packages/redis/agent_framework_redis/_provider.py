# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import MutableSequence, Sequence
from typing import Any, Final, Literal

from agent_framework import ChatMessage, Context, ContextProvider

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


import re

from redisvl.index import AsyncSearchIndex
from redisvl.query import FilterQuery
from redisvl.query.filter import FilterExpression

"""
Partitioning necessary
"""


def _escape_q(s: str) -> str:
    # escape RediSearch special chars: - @ { } [ ] ( ) | ~ * ? " : ^ < >
    return re.sub(r'([\-@\{\}\[\]\(\)\|\~\*\?":\^<>\\])', r"\\\1", s)


DEFAULT_CONTEXT_PROMPT: Final[str] = "## Memories\nConsider the following memories when answering user questions:"


class RedisProvider(ContextProvider):
    redis_url: str = "redis://localhost:6379"
    context_prompt: str = DEFAULT_CONTEXT_PROMPT
    redis_index: Any = None
    overwrite_redis_index: bool = True
    drop_redis_index: bool = True

    def __init__(
        self,
        *,
        redis_url: str = "redis://localhost:6379",
        context_prompt: str = DEFAULT_CONTEXT_PROMPT,
        overwrite_redis_index: bool = True,
        drop_redis_index: bool = True,
    ):
        schema_dict = {
            "index": {
                "name": "user-index",
                "prefix": "user",
                "key_separator": ":",
                "storage_type": "json",
            },
            "fields": [
                {"name": "role", "type": "tag"},
                {"name": "content", "type": "text"},
                {
                    "name": "embedding",
                    "type": "vector",
                    "attrs": {"algorithm": "flat", "dims": 3, "distance_metric": "cosine", "datatype": "float32"},
                },
            ],
        }
        redis_index = AsyncSearchIndex.from_dict(schema_dict, redis_url=redis_url, validate_on_load=True)

        super().__init__(
            redis_url=redis_url,  # type: ignore[reportCallIssue]
            context_prompt=context_prompt,  # type: ignore[reportCallIssue]
            redis_index=redis_index,  # type: ignore[reportCallIssue]
            overwrite_redis_index=overwrite_redis_index,  # type: ignore[reportCallIssue]
            drop_redis_index=drop_redis_index,  # type: ignore[reportCallIssue]
        )

    async def create_redis_index(self) -> None:
        await self.redis_index.create(overwrite=self.overwrite_redis_index, drop=self.drop_redis_index)
        return

    async def add(self, *, data: dict, metadata: dict[str, Any] | None = None) -> None:
        await self.redis_index.load(data)
        # NEED VERIFICATION CHECK HERE TO MAKE SURE THING WAS ADDED
        return

    async def text_search(
        self,
        q: str,
        *,
        k: int = 10,
        mode: Literal["phrase", "any", "prefix"] = "phrase",
        dialect: int = 2,
    ) -> list[dict]:
        """Basic full-text search against the 'content' field.

        mode='phrase' → exact phrase match
        mode='any'    → OR across terms
        mode='prefix' → token* prefix search
        """
        if mode == "phrase":
            expr = f'@content:"{_escape_q(q)}"'
        elif mode == "any":
            terms = " | ".join(_escape_q(t) for t in q.split())
            expr = f"@content:({terms})"
        elif mode == "prefix":
            terms = " ".join(_escape_q(t) + "*" for t in q.split())
            expr = f"@content:({terms})"
        else:
            expr = f'@content:"{_escape_q(q)}"'

        query = FilterQuery(
            FilterExpression(expr),
            num_results=k,
            return_fields=[],  # <-- empty + JSON storage => nice unpacked dicts
            dialect=dialect,
        )
        return await self.redis_index.query(query)

    async def search_all(self, page_size: int = 200) -> list[dict]:
        """Return all docs in the index (paginated under the hood)."""
        out: list[dict] = []
        async for batch in self.redis_index.paginate(
            FilterQuery(FilterExpression("*"), return_fields=[], num_results=page_size),
            page_size=page_size,
        ):
            out.extend(batch)
        return out

    async def thread_created(self, thread_id: str | None) -> None:
        """Called just after a new thread is created.

        Implementers can use this method to do any operations required at the creation of a new thread.
        For example, checking long term storage for any data that is relevant
        to the current session based on the input text.

        Args:
            thread_id: The ID of the new thread.
        """
        pass

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        """Called just before messages are added to the chat by any participant.

        Inheritors can use this method to update their context based on new messages.

        Args:
            thread_id: The ID of the thread for the new message.
            new_messages: New messages to add.
        """
        pass

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        """Called just before the Model/Agent/etc. is invoked.

        Implementers can load any additional context required at this time,
        and they should return any context that should be passed to the agent.

        Args:
            messages: The most recent messages that the agent is being invoked with.
        """
        return Context()

    async def __aenter__(self) -> Self:
        # Nothing special to do for Redis client; keep for symmetry with Mem0Provider
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        # No-op; indexes/keys remain unless `close()` is called explicitly.
        return None
