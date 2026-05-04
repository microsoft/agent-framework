# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from maximem_synap import MaximemSynapSDK
from synap_microsoft_agent import SynapContextProvider

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    """Example of persistent cross-session memory with SynapContextProvider."""
    print("=== Synap Context Provider Example ===")

    # Use a stable user_id so memories persist across runs.
    # In production, derive this from the authenticated user's identity.
    user_id = str(uuid.uuid4())

    sdk = MaximemSynapSDK(api_key="your-synap-api-key")  # or set SYNAP_API_KEY env var

    # For Azure authentication, run `az login` or replace AzureCliCredential with
    # your preferred authentication option.
    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="MemoryAssistant",
            instructions="You are a helpful assistant with long-term memory.",
            context_providers=[
                SynapContextProvider(
                    sdk=sdk,
                    user_id=user_id,
                    customer_id="acme_corp",
                )
            ],
        ) as agent,
    ):
        # First turn — teach the agent something about the user
        query = "I always prefer concise answers and I'm a software engineer."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Synap stores memories asynchronously. Allow time for processing
        # before querying in a new session — the agent should recall preferences.
        print("Waiting for Synap to process memories...")
        await asyncio.sleep(5)

        # Second turn in a new session — agent recalls from Synap
        print("Request within a new session:")
        session = agent.create_session()
        query = "How should you answer my questions?"
        print(f"User: {query}")
        result = await agent.run(query, session=session)
        print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
