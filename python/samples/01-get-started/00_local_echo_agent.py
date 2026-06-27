# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any

from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
)

"""
Local Echo Agent — Run an agent without cloud credentials

This sample shows the smallest local shape of an Agent Framework application:
- a custom chat client that returns deterministic responses
- an Agent that wraps the client
- non-streaming and streaming runs

Because the client is local and deterministic, this sample does not require an API key,
Azure sign-in, or a model deployment.
"""


def build_reply(messages: Sequence[Message]) -> str:
    """Build a deterministic response from the latest input message."""
    user_text = messages[-1].text if messages else ""
    return f"You said: {user_text}\nThis response came from LocalEchoChatClient, so no cloud model or API key was used."


class LocalEchoChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """A minimal chat client that echoes the latest user message."""

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            return self._get_streaming_response(messages=messages, options=options)

        async def get_response() -> ChatResponse:
            await self._validate_options(options)
            return ChatResponse(
                messages=Message(role="assistant", contents=[build_reply(messages)]),
                response_id="local-echo-response",
                model="local-echo",
                finish_reason="stop",
            )

        return get_response()

    def _get_streaming_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def stream_response() -> AsyncIterable[ChatResponseUpdate]:
            await self._validate_options(options)
            words = build_reply(messages).split(" ")
            for index, word in enumerate(words):
                suffix = "" if index == len(words) - 1 else " "
                yield ChatResponseUpdate(contents=[Content.from_text(text=f"{word}{suffix}")], role="assistant")
                await asyncio.sleep(0)
            yield ChatResponseUpdate(role="assistant", finish_reason="stop")

        return ResponseStream(
            stream_response(),
            finalizer=lambda updates: ChatResponse.from_updates(
                updates,
                output_format_type=options.get("response_format"),
            ),
        )


async def main() -> None:
    # 1. Create a local chat client.
    client = LocalEchoChatClient()

    # 2. Wrap the client in an Agent.
    agent = Agent(
        client=client,
        name="LocalEchoAgent",
        instructions="You are a tiny local demo agent.",
    )

    # 3. Run the agent and print the complete response.
    result = await agent.run("Explain Agent Framework in one sentence.")
    print(f"Agent: {result}")

    # 4. Run the same agent in streaming mode.
    print("Agent (streaming): ", end="", flush=True)
    async for chunk in agent.run("Stream a tiny local response.", stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Agent: You said: Explain Agent Framework in one sentence.
This response came from LocalEchoChatClient, so no cloud model or API key was used.
Agent (streaming): You said: Stream a tiny local response.
This response came from LocalEchoChatClient, so no cloud model or API key was used.
"""
