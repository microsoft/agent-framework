# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from agent_framework import AgentSession, BaseContextProvider, SessionContext
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Memory with Context Providers and Session State

Context providers inject dynamic context into each agent call. This sample
shows a provider that stores the user's name in session state and personalizes
responses — the name persists across turns via the session.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT        — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""


# <context_provider>
class UserMemoryProvider(BaseContextProvider):
    """A context provider that remembers user info in session state."""

    DEFAULT_SOURCE_ID = "user_memory"

    def __init__(self):
        super().__init__(self.DEFAULT_SOURCE_ID)

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject personalization instructions based on stored user info."""
        user_name = state.get("user_name")
        if user_name:
            context.extend_instructions(
                self.source_id,
                f"The user's name is {user_name}. Always address them by name.",
            )
        else:
            context.extend_instructions(
                self.source_id,
                "You don't know the user's name yet. Ask for it politely.",
            )

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Extract and store user info in session state after each call."""
        for msg in context.input_messages:
            text = msg.text if hasattr(msg, "text") else ""
            if isinstance(text, str) and "my name is" in text.lower():
                state["user_name"] = text.lower().split("my name is")[-1].strip().split()[0].capitalize()
# </context_provider>


async def main() -> None:
    # <create_agent>
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    agent = client.as_agent(
        name="MemoryAgent",
        instructions="You are a friendly assistant.",
        context_providers=[UserMemoryProvider()],
    )
    # </create_agent>

    # <run_with_memory>
    session = agent.create_session()

    # The provider doesn't know the user yet — it will ask for a name
    result = await agent.run("Hello! What's the square root of 9?", session=session)
    print(f"Agent: {result}\n")

    # Now provide the name — the provider stores it in session state
    result = await agent.run("My name is Alice", session=session)
    print(f"Agent: {result}\n")

    # Subsequent calls are personalized — name persists via session state
    result = await agent.run("What is 2 + 2?", session=session)
    print(f"Agent: {result}\n")

    # Inspect session state to see what the provider stored
    provider_state = session.state.get("user_memory", {})
    print(f"[Session State] Stored user name: {provider_state.get('user_name')}")
    # </run_with_memory>


if __name__ == "__main__":
    asyncio.run(main())
