# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os
import uuid

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient, FoundryMemoryProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
    ResponsesUserMessageItemParam,
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

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT environment variable
2. Set AZURE_AI_CHAT_MODEL_DEPLOYMENT_NAME for the memory chat model
3. Set AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME for the memory embedding model
4. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT environment variables
5. Deploy both a chat model (e.g. gpt-4) and an embedding model (e.g. text-embedding-3-small)
"""
load_dotenv()


async def main() -> None:
    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    # Generate a unique memory store name to avoid conflicts
    memory_store_name = f"agent_framework_memory_{uuid.uuid4().hex[:8]}"
    memory_store_name = "agent_framework_memory"  # Use a fixed name for easier debugging (delete after each run)
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

    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        try:
            # Create a memory store
            memory_store = await project_client.memory_stores.get(name=memory_store_name)
            memory_store = await project_client.memory_stores.create(
                name=memory_store_name,
                description="Memory store for Agent Framework with FoundryMemoryProvider",
                definition=memory_store_definition,
            )
            print(f"Created memory store: {memory_store.name} ({memory_store.id})")
            print(f"Description: {memory_store.description}\n")

            update = await project_client.memory_stores.begin_update_memories(
                name=memory_store.name,
                scope="user_123",
                items=[ResponsesUserMessageItemParam(content="I am a coffee lover and prefer dark roast.")],
                update_delay=0,
            )
            # await update.wait()
            await update.result()

            # Create the chat client
            client = AzureOpenAIResponsesClient(project_client=project_client)

            # Create the Foundry Memory context provider
            memory_provider = FoundryMemoryProvider(
                project_client=project_client,
                memory_store_name=memory_store.name,
                scope="user_123",  # Scope memories to a specific user
                update_delay=0,  # Wait 5 seconds before updating memories (use higher value in production)
            )

            # Create an agent with the memory context provider
            async with Agent(
                name="MemoryAgent",
                client=client,
                instructions="""You are a helpful assistant that remembers past conversations.
                    The memories from previous interactions are automatically provided to you.""",
                context_providers=[memory_provider],
                default_options={"store": False},
            ) as agent:
                # note that we do not have a History provider in this session, and we've set `store` to False
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

                async for mem in project_client.memory_stores.list():
                    print(f"Memory store: {mem}")
                    res = await project_client.memory_stores.search_memories(name=mem.name, scope="user_123")
                    for memory in res.memories:
                        print(f"Memory: {memory.memory_item.content}")
                    # await project_client.memory_stores.delete(mem.name)

        except Exception as e:
            print(f"An error occurred: {e}")

        # finally:
        #     await project_client.memory_stores.delete(memory_store_name)
        #     print("Memory store deleted")


if __name__ == "__main__":
    asyncio.run(main())
