# Copyright (c) Microsoft. All rights reserved.

import asyncio
from datetime import datetime, timedelta

from agent_framework.azure import AzureAIAgentClient
from agent_framework.mem0 import Mem0Provider
from azure.identity.aio import AzureCliCredential


async def main() -> None:
    """Example demonstrating advanced filtering with Mem0 context provider."""
    print("=== Mem0 Advanced Filtering Example ===\n")

    # For Azure authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    # For Mem0 authentication, set Mem0 API key via "api_key" parameter or MEM0_API_KEY environment variable.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).create_agent(
            name="FilterAssistant",
            instructions="You are a helpful assistant that retrieves and summarizes memories.",
            context_providers=Mem0Provider(user_id="demo_user"),
        ) as agent,
    ):
        # Store some memories with different timestamps
        print("Storing memories...")
        await agent.run("I love Python programming.")
        await agent.run("My favorite color is blue.")
        await agent.run("I work as a software engineer.")

        # Wait for memories to be indexed
        print("Waiting for memories to be processed...")
        await asyncio.sleep(12)  # Empirically determined delay for Mem0 indexing

        # Calculate a date from a week ago for filtering
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        print("\n=== Using OR Filter ===")
        # Use OR logic to find memories matching either condition
        query = "What do you know about me?"
        print(f"User: {query}")
        print(f"Filter: Memories from another user OR created after {week_ago}")

        result = await agent.run(
            query,
            filters={
                "OR": [
                    {"user_id": "another_user"},  # This won't match
                    {"created_at": {"gte": week_ago}},  # This will match our recent memories
                ]
            },
        )
        print(f"Agent: {result}\n")

        print("\n=== Using Complex Filter ===")
        # Demonstrate combining multiple filter conditions
        query = "Tell me about my preferences"
        print(f"User: {query}")
        print("Filter: Recent memories with specific keywords")

        result = await agent.run(
            query,
            filters={
                "AND": [
                    {"user_id": "demo_user"},
                    {"created_at": {"gte": week_ago}},
                ]
            },
        )
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
