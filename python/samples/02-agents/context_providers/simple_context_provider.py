# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from contextlib import suppress
from typing import Any

from agent_framework import Agent, AgentSession, BaseContextProvider, SessionContext, SupportsChatGetResponse
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel


class UserInfo(BaseModel):
    name: str | None = None
    age: int | None = None


class UserInfoMemory(BaseContextProvider):
    def __init__(self, source_id: str = "user-info-memory", *, client: SupportsChatGetResponse, **kwargs: Any):
        """Create the memory.

        If you pass in kwargs, they will be attempted to be used to create a UserInfo object.
        """
        super().__init__(source_id)
        self._chat_client = client

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Extract user information from messages after each agent call."""
        # ensure you get all the messages you want to parse from, including the input in this case.
        request_messages = context.get_messages(include_input=True, include_response=True)
        # Check if we need to extract user info from user messages
        user_messages = [msg for msg in request_messages if hasattr(msg, "role") and msg.role == "user"]  # type: ignore

        if (
            state[self.source_id]["user_info"].name is None or state[self.source_id]["user_info"].age is None
        ) and user_messages:
            with suppress(Exception):
                # Use the chat client to extract structured information
                result = await self._chat_client.get_response(
                    messages=request_messages,  # type: ignore
                    instructions="Extract the user's name and age from the message if present. "
                    "If not present return nulls.",
                    options={"response_format": UserInfo},
                )

                # Update user info with extracted data
                with suppress(Exception):
                    extracted = result.value
                    if state[self.source_id]["user_info"].name is None and extracted.name:
                        state[self.source_id]["user_info"].name = extracted.name
                    if state[self.source_id]["user_info"].age is None and extracted.age:
                        state[self.source_id]["user_info"].age = extracted.age

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Provide user information context before each agent call."""
        if state.setdefault(self.source_id, None) is None:
            state[self.source_id] = {"user_info": UserInfo()}

        context.extend_instructions(
            self.source_id,
            "Ask the user for their name and politely decline to answer any questions until they provide it."
            if state[self.source_id]["user_info"].name is None
            else f"The user's name is {state[self.source_id]['user_info'].name}.",
        )
        context.extend_instructions(
            self.source_id,
            "Ask the user for their age and politely decline to answer any questions until they provide it."
            if state[self.source_id]["user_info"].age is None
            else f"The user's age is {state[self.source_id]['user_info'].age}.",
        )


async def main():
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    context_name = "user-info-memory"

    # Create the memory provider
    memory_provider = UserInfoMemory(context_name, client=client)

    # Create the agent with memory
    async with Agent(
        client=client,
        instructions="You are a friendly assistant. Always address the user by their name.",
        context_providers=[memory_provider],
    ) as agent:
        # Create a new session for the conversation
        session = agent.create_session()

        for msg in ["Hello, what is the square root of 9?", "My name is Ruaidhrí", "I am 20 years old"]:
            print(f"User: {msg}")
            print(f"Assistant: {await agent.run(msg, session=session)}")

        # Access the memory component and inspect the memories
        print()
        print(f"MEMORY - User Name: {session.state[context_name]['user_info'].name}")
        print(f"MEMORY - User Age: {session.state[context_name]['user_info'].age}")


if __name__ == "__main__":
    asyncio.run(main())
