# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os
from datetime import datetime, timezone

from agent_framework import Agent, InMemoryHistoryProvider
from agent_framework.azure import AzureOpenAIResponsesClient, FoundryMemoryProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
)
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

"""
Azure AI Agent with Foundry Memory Context Provider Example

This sample demonstrates using the FoundryMemoryProvider as a context provider
to add semantic memory capabilities to your agents. The provider automatically:
1. Retrieves static (user profile) memories on first run
2. Searches for contextual memories based on conversation
3. Updates the memory store with new conversation messages

The sample creates a temporary memory store with user profile enabled (and chat summary
disabled), scopes memories to a specific user ID ("user_123"), and sets update_delay=0
so memories are stored immediately (in production, use a delay to batch updates and
reduce costs). Conversation history is intentionally not stored (neither service-side
via ``store=False`` nor client-side via ``load_messages=False`` on the history provider),
so that follow-up responses demonstrate the agent relying solely on Foundry Memory
rather than chat history. The memory store is deleted at the end of the run.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT environment variable
2. Set AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME for the chat/responses model
3. Set AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME for the embedding model
4. Deploy both a chat model (e.g. gpt-4) and an embedding model (e.g. text-embedding-3-small)
"""
load_dotenv()


async def main() -> None:
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        # Generate a unique memory store name to avoid conflicts
        memory_store_name = f"agent_framework_memory_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        # Specify memory store options
        options = MemoryStoreDefaultOptions(
            chat_summary_enabled=False,
            user_profile_enabled=True,
            user_profile_details="Avoid irrelevant or sensitive data, such as age, financials, precise location, and credentials",
        )
        memory_store_definition = MemoryStoreDefaultDefinition(
            chat_model=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
            embedding_model=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"],
            options=options,
        )
        print(f"Creating memory store '{memory_store_name}'...")
        try:
            # Create a memory store
            memory_store = await project_client.memory_stores.create(
                name=memory_store_name,
                description="Memory store for Agent Framework with FoundryMemoryProvider",
                definition=memory_store_definition,
            )
        except Exception as e:
            print(f"Failed to create memory store: {e}")
            return

        print(f"Created memory store: {memory_store.name} ({memory_store.id})")
        print(f"Description: {memory_store.description}\n")
        print("==========================================")

        # Create the chat client
        client = AzureOpenAIResponsesClient(project_client=project_client)
        # Create the Foundry Memory context provider
        memory_provider = FoundryMemoryProvider(
            project_client=project_client,
            memory_store_name=memory_store.name,
            scope="user_123",  # Scope memories to a specific user, if not set, the session_id
            # will be used as scope, which means memories are only shared within the same session
            update_delay=0,  # Do not wait to update memories after each interaction (for demo purposes)
            # In production, consider setting a delay to batch updates and reduce costs
        )

        # Create an agent with the memory context provider
        async with Agent(
            name="MemoryAgent",
            client=client,
            instructions="""You are a helpful assistant that remembers past conversations.
                The memories from previous interactions are automatically provided to you.""",
            context_providers=[memory_provider, InMemoryHistoryProvider(load_messages=False)],
            default_options={"store": False},
        ) as agent:
            try:
                # note that we will use the service side storage, nor load messsages from the history provider,
                # but we include it to demonstrate that it can be used alongside the Foundry provider for other use cases.
                session = agent.create_session()

                # First interaction - establish some preferences
                print("=== First conversation ===")
                query1 = "I prefer dark roast coffee and I'm allergic to nuts"
                print(f"User: {query1}")
                result1 = await agent.run(query1, session=session)
                print(f"Agent: {result1}\n")

                # Wait for memories to be processed
                print("Waiting for memories to be stored...")
                await asyncio.sleep(8)

                # Second interaction - test memory recall
                print("=== Second conversation ===")
                query2 = "Can you recommend a coffee and snack for me?"
                print(f"User: {query2}")
                result2 = await agent.run(query2, session=session)
                print(f"Agent: {result2}\n")

                # Third interaction - continue the conversation
                print("=== Third conversation ===")
                query3 = "What do you remember about my preferences?"
                print(f"User: {query3}")
                result3 = await agent.run(query3, session=session)
                print(f"Agent: {result3}\n")

                print(f"Stored memories from: {memory_store.name} ({memory_store.id})")
                res = await project_client.memory_stores.search_memories(name=memory_store.name, scope="user_123")
                for memory in res.memories:
                    print(f"Memory: {memory.memory_item.content}")

            except Exception as e:
                print(f"An error occurred: {e}")

            finally:
                await project_client.memory_stores.delete(memory_store_name)
                print("==========================================")
                print("Memory store deleted")


if __name__ == "__main__":
    asyncio.run(main())

"""
Example output:
Creating memory store 'agent_framework_memory_20260223'...
Created memory store: agent_framework_memory_20260223 (memstore_57c1f95bb4040c6d00RVOP71Q8tS23opIc4G4ZE8DuALiBFx44)
Description: Memory store for Agent Framework with FoundryMemoryProvider

==========================================
=== First conversation ===
User: I prefer dark roast coffee and I'm allergic to nuts
Agent: Got it—I’ll remember: you prefer dark roast coffee, and you’re allergic to nuts.

Waiting for memories to be stored...
=== Second conversation ===
User: Can you recommend a coffee and snack for me?
Agent: For coffee: **dark roast drip or Americano** (choose a **dark roast** like French/Italian roast). If you like it smoother, try a **dark-roast cold brew**.

For a snack (nut-free): **Greek yogurt with berries**, or a **cheese stick + whole-grain crackers**. If you want something sweet: **dark chocolate (check “may contain nuts” warnings)**.

=== Third conversation ===
User: What do you remember about my preferences?
Agent: - You’re allergic to nuts.
- You prefer dark roast coffee.

Stored memories from: agent_framework_memory_20260223 (memstore_57c1f95bb4040c6d00RVOP71Q8tS23opIc4G4ZE8DuALiBFx44)
Memory: The user is allergic to nuts.
Memory: The user prefers dark roast coffee.
==========================================
Memory store deleted
"""
