# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIChatClient


async def suspend_resume_service_managed_thread() -> None:
    """Demonstrates how to suspend and resume a service-managed thread."""
    print("=== Suspend-Resume Service-Managed Thread ===")

    # OpenAI Chat Client is used as an example here,
    # other chat clients can be used as well.
    agent = OpenAIChatClient().create_agent(name="Joker", instructions="You are good at telling jokes.")

    # Start a new thread for the agent conversation.
    thread = agent.get_new_thread()

    # Respond to user input.
    query = "Tell me a joke about a pirate."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=thread)}\n")

    # Serialize the thread state, so it can be stored for later use.
    serialized_thread = await thread.serialize()

    # The thread can now be saved to a database, file, or any other storage mechanism and loaded again later.
    print(f"Serialized thread: {serialized_thread}\n")

    # Deserialize the thread state after loading from storage.
    resumed_thread = await agent.deserialize_thread(serialized_thread)

    # Respond to user input.
    query = "Now tell the same joke in the voice of a pirate, and add some emojis to the joke."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")


async def suspend_resume_in_memory_thread() -> None:
    """Demonstrates how to suspend and resume an in-memory thread."""
    print("=== Suspend-Resume In-Memory Thread ===")

    # OpenAI Chat Client is used as an example here,
    # other chat clients can be used as well.
    agent = OpenAIChatClient().create_agent(name="Joker", instructions="You are good at telling jokes.")

    # Start a new thread for the agent conversation.
    thread = agent.get_new_thread()

    # Respond to user input.
    query = "Tell me a joke about a pirate."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=thread)}\n")

    # Serialize the thread state, so it can be stored for later use.
    serialized_thread = await thread.serialize()

    # The thread can now be saved to a database, file, or any other storage mechanism and loaded again later.
    print(f"Serialized thread: {serialized_thread}\n")

    # Deserialize the thread state after loading from storage.
    resumed_thread = await agent.deserialize_thread(serialized_thread)

    # Respond to user input.
    query = "Now tell the same joke in the voice of a pirate, and add some emojis to the joke."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")


async def main() -> None:
    print("=== Suspend-Resume Thread Examples ===")
    await suspend_resume_service_managed_thread()
    await suspend_resume_in_memory_thread()


if __name__ == "__main__":
    asyncio.run(main())
