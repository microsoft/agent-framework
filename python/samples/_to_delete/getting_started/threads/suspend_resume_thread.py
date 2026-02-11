# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIAgentClient
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import AzureCliCredential

"""
Thread Suspend and Resume Example

This sample demonstrates how to suspend and resume conversation threads, comparing
service-managed threads (Azure AI) with in-memory threads (OpenAI) for persistent
conversation state across sessions.
"""


async def suspend_resume_service_managed_thread() -> None:
    """Demonstrates how to suspend and resume a service-managed thread."""
    print("=== Suspend-Resume Service-Managed Thread ===")

    # AzureAIAgentClient supports service-managed threads.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="MemoryBot", instructions="You are a helpful assistant that remembers our conversation."
        ) as agent,
    ):
        # Start a new thread for the agent conversation.
        thread = agent.get_new_thread()

        # Respond to user input.
        query = "Hello! My name is Alice and I love pizza."
        print(f"User: {query}")
        print(f"Agent: {await agent.run(query, thread=thread)}\n")

        # Serialize the thread state, so it can be stored for later use.
        serialized_thread = await thread.serialize()

        # The thread can now be saved to a database, file, or any other storage mechanism and loaded again later.
        print(f"Serialized thread: {serialized_thread}\n")

        # Deserialize the thread state after loading from storage.
        resumed_thread = await agent.deserialize_thread(serialized_thread)

        # Respond to user input.
        query = "What do you remember about me?"
        print(f"User: {query}")
        print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")


async def suspend_resume_in_memory_thread() -> None:
    """Demonstrates how to suspend and resume an in-memory thread."""
    print("=== Suspend-Resume In-Memory Thread ===")

    # OpenAI Chat Client is used as an example here,
    # other chat clients can be used as well.
    agent = OpenAIChatClient().as_agent(
        name="MemoryBot", instructions="You are a helpful assistant that remembers our conversation."
    )

    # Start a new thread for the agent conversation.
    thread = agent.get_new_thread()

    # Respond to user input.
    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=thread)}\n")

    # Serialize the thread state, so it can be stored for later use.
    serialized_thread = await thread.serialize()

    # The thread can now be saved to a database, file, or any other storage mechanism and loaded again later.
    print(f"Serialized thread: {serialized_thread}\n")

    # Deserialize the thread state after loading from storage.
    resumed_thread = await agent.deserialize_thread(serialized_thread)

    # Respond to user input.
    query = "What do you remember about me?"
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")


async def main() -> None:
    print("=== Suspend-Resume Thread Examples ===")
    await suspend_resume_service_managed_thread()
    await suspend_resume_in_memory_thread()


if __name__ == "__main__":
    asyncio.run(main())
