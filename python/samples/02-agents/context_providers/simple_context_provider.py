# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import Agent, AgentSession, BaseContextProvider, SessionContext, SupportsChatGetResponse
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential
from pydantic import BaseModel


class UserInfo(BaseModel):
    name: str | None = None
    age: int | None = None


class UserInfoMemory(BaseContextProvider):
    def __init__(self, client: SupportsChatGetResponse, user_info: UserInfo | None = None, **kwargs: Any):
        """Create the memory.

        If you pass in kwargs, they will be attempted to be used to create a UserInfo object.
        """
        super().__init__("user-info-memory")
        self._chat_client = client
        if user_info:
            self.user_info = user_info
        elif kwargs:
            self.user_info = UserInfo.model_validate(kwargs)
        else:
            self.user_info = UserInfo()

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Extract user information from messages after each agent call."""
        request_messages = context.get_messages()
        # Check if we need to extract user info from user messages
        user_messages = [msg for msg in request_messages if hasattr(msg, "role") and msg.role == "user"]  # type: ignore

        if (self.user_info.name is None or self.user_info.age is None) and user_messages:
            try:
                # Use the chat client to extract structured information
                result = await self._chat_client.get_response(
                    messages=request_messages,  # type: ignore
                    instructions="Extract the user's name and age from the message if present. "
                    "If not present return nulls.",
                    options={"response_format": UserInfo},
                )

                # Update user info with extracted data
                try:
                    extracted = result.value
                    if self.user_info.name is None and extracted.name:
                        self.user_info.name = extracted.name
                    if self.user_info.age is None and extracted.age:
                        self.user_info.age = extracted.age
                except Exception:
                    pass  # Failed to extract, continue without updating

            except Exception:
                pass  # Failed to extract, continue without updating

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Provide user information context before each agent call."""
        instructions: list[str] = []

        if self.user_info.name is None:
            instructions.append(
                "Ask the user for their name and politely decline to answer any questions until they provide it."
            )
        else:
            instructions.append(f"The user's name is {self.user_info.name}.")

        if self.user_info.age is None:
            instructions.append(
                "Ask the user for their age and politely decline to answer any questions until they provide it."
            )
        else:
            instructions.append(f"The user's age is {self.user_info.age}.")

        # Add context with additional instructions
        context.extend_instructions(self.source_id, " ".join(instructions))

    def serialize(self) -> str:
        """Serialize the user info for session persistence."""
        return self.user_info.model_dump_json()


async def main():
    async with AzureCliCredential() as credential:
        client = AzureAIClient(credential=credential)

        # Create the memory provider
        memory_provider = UserInfoMemory(client)

        # Create the agent with memory
        async with Agent(
            client=client,
            instructions="You are a friendly assistant. Always address the user by their name.",
            context_providers=[memory_provider],
        ) as agent:
            # Create a new session for the conversation
            session = agent.create_session()

            print(await agent.run("Hello, what is the square root of 9?", session=session))
            print(await agent.run("My name is Ruaidhrí", session=session))
            print(await agent.run("I am 20 years old", session=session))

            # Access the memory component and inspect the memories
            if memory_provider:
                print()
                print(f"MEMORY - User Name: {memory_provider.user_info.name}")
                print(f"MEMORY - User Age: {memory_provider.user_info.age}")


if __name__ == "__main__":
    asyncio.run(main())
