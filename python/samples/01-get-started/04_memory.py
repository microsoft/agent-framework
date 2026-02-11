# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from collections.abc import MutableSequence
from typing import Any

from agent_framework import Context, ContextProvider, Message
from agent_framework.openai import OpenAIResponsesClient

"""
Agent Memory with Context Providers

Context providers let you inject dynamic instructions and context into each
agent invocation. This sample defines a simple provider that tracks the user's
name and enriches every request with personalization instructions.
"""


# <context_provider>
class UserNameProvider(ContextProvider):
    """A simple context provider that remembers the user's name."""

    def __init__(self) -> None:
        self.user_name: str | None = None

    async def invoking(self, messages: Message | MutableSequence[Message], **kwargs: Any) -> Context:
        """Called before each agent invocation — add extra instructions."""
        if self.user_name:
            return Context(instructions=f"The user's name is {self.user_name}. Always address them by name.")
        return Context(instructions="You don't know the user's name yet. Ask for it politely.")

    async def invoked(
        self,
        request_messages: Message | "list[Message] | Message | None" = None,
        response_messages: "Message | list[Message] | None" = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Called after each agent invocation — extract information."""
        msgs = [request_messages] if isinstance(request_messages, Message) else list(request_messages or [])
        for msg in msgs:
            text = msg.text if hasattr(msg, "text") else ""
            if isinstance(text, str) and "my name is" in text.lower():
                # Simple extraction — production code should use structured extraction
                self.user_name = text.lower().split("my name is")[-1].strip().split()[0].capitalize()
# </context_provider>


async def main() -> None:
    # <create_agent>
    client = OpenAIResponsesClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model_id=os.environ.get("OPENAI_RESPONSES_MODEL_ID", "gpt-4o"),
    )

    memory = UserNameProvider()

    agent = client.as_agent(
        name="MemoryAgent",
        instructions="You are a friendly assistant.",
        context_provider=memory,
    )
    # </create_agent>

    thread = agent.get_new_thread()

    # The provider doesn't know the user yet — it will ask for a name
    result = await agent.run("Hello! What's the square root of 9?", thread=thread)
    print(f"Agent: {result}\n")

    # Now provide the name — the provider extracts and stores it
    result = await agent.run("My name is Alice", thread=thread)
    print(f"Agent: {result}\n")

    # Subsequent calls are personalized
    result = await agent.run("What is 2 + 2?", thread=thread)
    print(f"Agent: {result}\n")

    print(f"[Memory] Stored user name: {memory.user_name}")


if __name__ == "__main__":
    asyncio.run(main())
