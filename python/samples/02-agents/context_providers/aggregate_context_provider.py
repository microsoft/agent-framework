# Copyright (c) Microsoft. All rights reserved.

"""
This sample demonstrates how to use multiple context providers with an agent.

Context providers can be passed as a list to the agent's context_providers parameter.
Each provider is called in order during the agent's lifecycle, and their context
is combined automatically.

You can use built-in providers or implement your own by extending BaseContextProvider.
"""

import asyncio
from typing import Any

from agent_framework import Agent, AgentSession, BaseContextProvider, Message, SessionContext
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential


# region Example Context Providers


class TimeContextProvider(BaseContextProvider):
    """A simple context provider that adds time-related instructions."""

    def __init__(self):
        super().__init__("time")

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        from datetime import datetime

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context.extend_instructions(self.source_id, f"The current date and time is: {current_time}. ")


class PersonaContextProvider(BaseContextProvider):
    """A context provider that adds a persona to the agent."""

    def __init__(self, persona: str):
        super().__init__("persona")
        self.persona = persona

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        context.extend_instructions(self.source_id, f"Your persona: {self.persona}. ")


class PreferencesContextProvider(BaseContextProvider):
    """A context provider that adds user preferences."""

    def __init__(self):
        super().__init__("preferences")
        self.preferences: dict[str, str] = {}

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        if not self.preferences:
            return
        prefs_str = ", ".join(f"{k}: {v}" for k, v in self.preferences.items())
        context.extend_instructions(self.source_id, f"User preferences: {prefs_str}. ")

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        # Simple example: extract and store preferences from user messages
        # In a real implementation, you might use structured extraction
        request_messages = context.get_messages()

        for msg in request_messages:
            content = msg.text if hasattr(msg, "text") else ""
            # Very simple extraction - in production, use LLM-based extraction
            if isinstance(content, str) and "prefer" in content.lower() and ":" in content:
                parts = content.split(":")
                if len(parts) >= 2:
                    key = parts[0].strip().lower().replace("i prefer ", "")
                    value = parts[1].strip()
                    self.preferences[key] = value


# endregion


# region Main


async def main():
    """Demonstrate using multiple context providers with an agent."""
    async with AzureCliCredential() as credential:
        client = AzureAIClient(credential=credential)

        # Create individual context providers
        time_provider = TimeContextProvider()
        persona_provider = PersonaContextProvider("You are a helpful and friendly AI assistant named Max.")
        preferences_provider = PreferencesContextProvider()

        # Create the agent with multiple context providers
        async with Agent(
            client=client,
            instructions="You are a helpful assistant.",
            context_providers=[
                time_provider,
                persona_provider,
                preferences_provider,
            ],
        ) as agent:
            # Create a new session for the conversation
            session = agent.create_session()

            # First message - the agent should include time and persona context
            print("User: Hello! Who are you?")
            result = await agent.run("Hello! Who are you?", session=session)
            print(f"Agent: {result}\n")

            # Set a preference
            print("User: I prefer language: formal English")
            result = await agent.run("I prefer language: formal English", session=session)
            print(f"Agent: {result}\n")

            # Ask something - the agent should now include the preference
            print("User: Can you tell me a fun fact?")
            result = await agent.run("Can you tell me a fun fact?", session=session)
            print(f"Agent: {result}\n")

            # Show what the aggregate provider is tracking
            print(f"\nPreferences tracked: {preferences_provider.preferences}")


if __name__ == "__main__":
    asyncio.run(main())
