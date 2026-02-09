# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import Any

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Content,
    Role,
    normalize_messages,
)

"""
Custom Provider (BaseAgent)

Demonstrates implementing a custom agent by extending BaseAgent.
Use this pattern when you need to integrate a provider not yet supported
by Agent Framework, or when building a fully custom agent implementation.

For more on custom agents:
- Full example: getting_started/agents/custom/custom_agent.py
- Docs: https://learn.microsoft.com/agent-framework/providers/custom
"""


# <custom_agent>
class EchoAgent(BaseAgent):
    """A simple custom agent that echoes user messages with a prefix."""

    echo_prefix: str = "Echo: "

    def __init__(self, *, name: str | None = None, echo_prefix: str = "Echo: ", **kwargs: Any) -> None:
        super().__init__(name=name, echo_prefix=echo_prefix, **kwargs)  # type: ignore

    def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> "AsyncIterable[AgentResponseUpdate] | asyncio.Future[AgentResponse]":
        if stream:
            return self._run_stream(messages=messages, thread=thread, **kwargs)
        return self._run(messages=messages, thread=thread, **kwargs)

    async def _run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        normalized = normalize_messages(messages)
        last_text = normalized[-1].text if normalized and normalized[-1].text else "Hello!"
        echo_text = f"{self.echo_prefix}{last_text}"
        response_message = ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(text=echo_text)])

        if thread is not None:
            await self._notify_thread_of_new_messages(thread, normalized, response_message)

        return AgentResponse(messages=[response_message])

    async def _run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        normalized = normalize_messages(messages)
        last_text = normalized[-1].text if normalized and normalized[-1].text else "Hello!"
        echo_text = f"{self.echo_prefix}{last_text}"

        for i, word in enumerate(echo_text.split()):
            chunk = f" {word}" if i > 0 else word
            yield AgentResponseUpdate(contents=[Content.from_text(text=chunk)], role=Role.ASSISTANT)
            await asyncio.sleep(0.05)

        if thread is not None:
            complete = ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text(text=echo_text)])
            await self._notify_thread_of_new_messages(thread, normalized, complete)
# </custom_agent>


async def main() -> None:
    print("=== Custom Provider (EchoAgent) ===\n")

    # <run_agent>
    agent = EchoAgent(name="EchoBot", echo_prefix="🔊 ")

    # Non-streaming
    query = "Hello, custom agent!"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.messages[0].text}")

    # Streaming
    query = "Streaming test"
    print(f"\nUser: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()
    # </run_agent>


if __name__ == "__main__":
    asyncio.run(main())
