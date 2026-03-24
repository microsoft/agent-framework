# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any

from agent_framework import (
    GROUP_ANNOTATION_KEY,
    GROUP_TOKEN_COUNT_KEY,
    Agent,
    BaseChatClient,
    ChatResponse,
    Message,
    SlidingWindowStrategy,
    TruncationStrategy,
)

"""This sample demonstrates client defaults, agent overrides, and run-level overrides for in-run compaction.

Key components:
- A shared client with default `compaction_strategy` and `tokenizer`
- An agent-level override that takes precedence over the shared client defaults
- A run-level override passed through `agent.run(...)`
"""


class FixedTokenizer:
    """Simple tokenizer used to make token annotations easy to inspect."""

    def __init__(self, token_count: int) -> None:
        self._token_count = token_count

    def count_tokens(self, text: str) -> int:
        return self._token_count


class InspectingChatClient(BaseChatClient[Any]):
    """Chat client that records the messages it receives after compaction."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.last_messages: list[Message] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse]:
        if stream:
            raise ValueError("This sample only demonstrates non-streaming responses.")

        self.last_messages = list(messages)

        async def _get_response() -> ChatResponse:
            return ChatResponse(messages=[Message(role="assistant", text="done")])

        return _get_response()


def _build_messages() -> list[Message]:
    return [
        Message(role="user", text="Collect the deployment requirements."),
        Message(role="assistant", text="I will gather the constraints first."),
        Message(role="user", text="Summarize the rollout risks."),
        Message(role="assistant", text="The main risks are drift, downtime, and rollback gaps."),
    ]


def _token_count(message: Message) -> int | None:
    group_annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if not isinstance(group_annotation, dict):
        return None
    value = group_annotation.get(GROUP_TOKEN_COUNT_KEY)
    return value if isinstance(value, int) else None


def _print_model_input(title: str, client: InspectingChatClient) -> None:
    print(f"\n{title}")
    print(f"Model receives {len(client.last_messages)} message(s):")
    for message in client.last_messages:
        print(f"- [{message.role}] {message.text} ({_token_count(message)} tokens)")


async def main() -> None:
    # 1. Create one shared client with default compaction settings.
    shared_client = InspectingChatClient(
        compaction_strategy=TruncationStrategy(max_n=3, compact_to=2),
        tokenizer=FixedTokenizer(7),
    )

    # 2. Create one agent that relies on the client defaults.
    client_default_agent = Agent(client=shared_client, name="ClientDefaultAgent")

    # 3. Create another agent that overrides the shared client's defaults.
    agent_override = Agent(
        client=shared_client,
        name="AgentOverrideAgent",
        compaction_strategy=SlidingWindowStrategy(keep_last_groups=3),
        tokenizer=FixedTokenizer(11),
    )

    # 4. Run the first agent; the client defaults are applied.
    await client_default_agent.run(_build_messages())
    _print_model_input("1. Client default compaction", shared_client)

    # 5. Run the second agent; the agent-level override wins over the client defaults.
    await agent_override.run(_build_messages())
    _print_model_input("2. Agent-level override", shared_client)

    # 6. Override both settings for a single run; the per-run values win over both.
    await agent_override.run(
        _build_messages(),
        compaction_strategy=TruncationStrategy(max_n=2, compact_to=1),
        tokenizer=FixedTokenizer(23),
    )
    _print_model_input("3. Per-run override", shared_client)


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

1. Client default compaction
Model receives 2 message(s):
- [user] Summarize the rollout risks. (7 tokens)
- [assistant] The main risks are drift, downtime, and rollback gaps. (7 tokens)

2. Agent-level override
Model receives 3 message(s):
- [assistant] I will gather the constraints first. (11 tokens)
- [user] Summarize the rollout risks. (11 tokens)
- [assistant] The main risks are drift, downtime, and rollback gaps. (11 tokens)

3. Per-run override
Model receives 1 message(s):
- [assistant] The main risks are drift, downtime, and rollback gaps. (23 tokens)
"""
