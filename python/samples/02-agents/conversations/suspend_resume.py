# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIChatClient

"""
Suspend and Resume Conversations

Demonstrates serializing a conversation thread to save its state, then
deserializing it later to resume the conversation. Works with any provider's
thread implementation (in-memory, service-managed, Redis, etc.).

For more on suspend/resume:
- Custom stores: ./persistent_conversation.py
- Redis storage: ./redis_storage.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/threads
"""


# <suspend_resume>
async def main() -> None:
    print("=== Suspend and Resume Conversations ===\n")

    agent = OpenAIChatClient().as_agent(
        name="MemoryBot",
        instructions="You are a helpful assistant that remembers our conversation.",
    )

    # Start a conversation
    thread = agent.get_new_thread()

    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=thread)}\n")

    # --- Suspend: serialize the thread state ---
    serialized_thread = await thread.serialize()
    print(f"Serialized thread state: {serialized_thread}\n")
    # Save serialized_thread to database, file, or any storage mechanism

    # --- Resume: deserialize and continue ---
    resumed_thread = await agent.deserialize_thread(serialized_thread)

    query = "What do you remember about me?"
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, thread=resumed_thread)}\n")
# </suspend_resume>


if __name__ == "__main__":
    asyncio.run(main())
