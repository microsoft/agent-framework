# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from agent_framework._sessions import AgentSession, BaseContextProvider, SessionContext
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Agent Memory with Context Providers

Context providers let you inject dynamic instructions and context into each
agent invocation. This sample defines a simple provider that tracks the user's
name and enriches every request with personalization instructions.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT        — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""


# <context_provider>
class UserNameProvider(BaseContextProvider):
    """A simple context provider that remembers the user's name."""

    def __init__(self) -> None:
        super().__init__(source_id="user-name-provider")
        self.user_name: str | None = None

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called before each agent invocation — add extra instructions."""
        if self.user_name:
            context.instructions.append(f"The user's name is {self.user_name}. Always address them by name.")
        else:
            context.instructions.append("You don't know the user's name yet. Ask for it politely.")

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Called after each agent invocation — extract information."""
        for msg in context.input_messages:
            text = msg.text if hasattr(msg, "text") else ""
            if isinstance(text, str) and "my name is" in text.lower():
                # Simple extraction — production code should use structured extraction
                self.user_name = text.lower().split("my name is")[-1].strip().split()[0].capitalize()
# </context_provider>


async def main() -> None:
    # <create_agent>
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    memory = UserNameProvider()

    agent = client.as_agent(
        name="MemoryAgent",
        instructions="You are a friendly assistant.",
        context_providers=[memory],
    )
    # </create_agent>

    # <run_with_memory>
    session = agent.create_session()

    # The provider doesn't know the user yet — it will ask for a name
    result = await agent.run("Hello! What's the square root of 9?", session=session)
    print(f"Agent: {result}\n")

    # Now provide the name — the provider extracts and stores it
    result = await agent.run("My name is Alice", session=session)
    print(f"Agent: {result}\n")

    # Subsequent calls are personalized
    result = await agent.run("What is 2 + 2?", session=session)
    print(f"Agent: {result}\n")

    print(f"[Memory] Stored user name: {memory.user_name}")
    # </run_with_memory>


if __name__ == "__main__":
    asyncio.run(main())
