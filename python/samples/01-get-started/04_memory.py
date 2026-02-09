# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import MutableSequence
from typing import Any

from agent_framework import AgentThread, ChatMessage, Context, ContextProvider
from agent_framework.openai import OpenAIResponsesClient

"""
Step 4: Add Memory with Context Providers

Use a ContextProvider to inject persistent memory or preferences into every agent call.
The provider's `invoking` method runs before each call, letting you add context dynamically.

For more on conversations & context, see: ../02-agents/conversations/
For docs: https://learn.microsoft.com/agent-framework/get-started/memory
"""


# <define_context_provider>
class UserPreferencesProvider(ContextProvider):
    """A simple context provider that injects user preferences into agent calls."""

    def __init__(self, preferences: dict[str, str] | None = None):
        self.preferences = preferences or {}

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        """Called before each agent invocation — returns extra instructions."""
        if not self.preferences:
            return Context(instructions="No user preferences are known yet.")

        pref_lines = [f"- {k}: {v}" for k, v in self.preferences.items()]
        return Context(
            instructions="Known user preferences:\n" + "\n".join(pref_lines)
            + "\nUse these preferences to personalize your responses."
        )
# </define_context_provider>


async def main():
    # <create_agent_with_memory>
    preferences = UserPreferencesProvider(
        preferences={
            "name": "Alice",
            "favorite_color": "blue",
            "dietary_restriction": "vegetarian",
        }
    )

    client = OpenAIResponsesClient()
    agent = client.as_agent(
        name="PersonalAssistant",
        instructions="You are a helpful personal assistant. Be concise.",
        context_providers=preferences,
    )
    # </create_agent_with_memory>

    # <run_agent>
    thread = AgentThread()

    response = await agent.run("Suggest a meal for me.", thread=thread)
    print(f"Agent: {response}")

    response = await agent.run("What color should I paint my room?", thread=thread)
    print(f"Agent: {response}")
    # </run_agent>


if __name__ == "__main__":
    asyncio.run(main())
