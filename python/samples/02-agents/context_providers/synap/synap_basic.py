# Copyright (c) Microsoft. All rights reserved.
# Demonstrates SynapContextProvider with Microsoft Agent Framework.
# Install: pip install maximem-synap-microsoft-agent
# Get API key at synap.maximem.ai

import asyncio
import os

from agent_framework import Agent
from maximem_synap import MaximemSynapSDK
from synap_microsoft_agent import SynapContextProvider


async def main() -> None:
    """Example: SynapContextProvider for persistent cross-session memory."""
    sdk = MaximemSynapSDK(api_key=os.environ["SYNAP_API_KEY"])

    user_id = "demo-user-001"

    provider = SynapContextProvider(
        sdk=sdk,
        user_id=user_id,
        customer_id="acme_corp",
    )

    async with Agent(
        name="MemoryAssistant",
        instructions="You are a helpful assistant with long-term memory.",
        context_providers=[provider],
    ) as agent:
        # First turn — teach the agent something about the user
        query = "I always prefer concise answers and I'm a software engineer."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Second turn — the agent recalls from Synap
        query = "How should you answer my questions?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
