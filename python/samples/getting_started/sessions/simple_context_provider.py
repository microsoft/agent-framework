# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import (
    Agent,
    AgentSession,
    BaseContextProvider,
    SessionContext,
    SupportsChatGetResponse,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel


class UserInfo(BaseModel):
    name: str | None = None
    age: int | None = None


class UserInfoMemory(BaseContextProvider):
    """Context provider that extracts and remembers user info (name, age).

    State is stored in ``session.state["user_info_memory"]`` so it survives
    serialization via ``session.to_dict()`` / ``AgentSession.from_dict()``.
    """

    DEFAULT_SOURCE_ID = "user_info_memory"

    def __init__(self, client: SupportsChatGetResponse):
        super().__init__(self.DEFAULT_SOURCE_ID)
        self._chat_client = client

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Provide user information context before each agent call."""
        user_info = state.setdefault("user_info", UserInfo())

        instructions: list[str] = []

        if user_info.name is None:
            instructions.append(
                "Ask the user for their name and politely decline to answer any questions until they provide it."
            )
        else:
            instructions.append(f"The user's name is {user_info.name}.")

        if user_info.age is None:
            instructions.append(
                "Ask the user for their age and politely decline to answer any questions until they provide it."
            )
        else:
            instructions.append(f"The user's age is {user_info.age}.")

        context.extend_instructions(self.source_id, " ".join(instructions))

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Extract user information from messages after each agent call."""
        user_info = state.setdefault("user_info", UserInfo())
        if user_info.name is not None and user_info.age is not None:
            return  # Already have everything

        request_messages = context.get_messages(include_input=True, include_response=True)
        user_messages = [msg for msg in request_messages if hasattr(msg, "role") and msg.role == "user"]  # type: ignore
        if not user_messages:
            return

        try:
            result = await self._chat_client.get_response(
                messages=request_messages,  # type: ignore
                instructions="Extract the user's name and age from the message if present. "
                "If not present return nulls.",
                options={"response_format": UserInfo},
            )
            extracted = result.value
            if extracted and user_info.name is None and extracted.name:
                user_info.name = extracted.name
            if extracted and user_info.age is None and extracted.age:
                user_info.age = extracted.age
            state["user_info"] = user_info
        except Exception:
            pass  # Failed to extract, continue without updating


async def main():
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    async with Agent(
        client=client,
        instructions="You are a friendly assistant. Always address the user by their name.",
        default_options={"store": True},
        context_providers=[UserInfoMemory(client)],
    ) as agent:
        session = agent.create_session()

        print(await agent.run("Hello, what is the square root of 9?", session=session))
        print(await agent.run("My name is Ruaidhrí", session=session))
        print(await agent.run("I am 20 years old", session=session))

        # Inspect extracted user info from session state
        user_info = session.state.get(UserInfoMemory.DEFAULT_SOURCE_ID, {}).get("user_info", UserInfo())
        print()
        print(f"MEMORY - User Name: {user_info.name}")
        print(f"MEMORY - User Age: {user_info.age}")


if __name__ == "__main__":
    asyncio.run(main())
