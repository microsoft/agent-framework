# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid

from agent_framework.azure import AzureAIAgentClient
from agent_framework.mem0 import Mem0Provider
from azure.identity.aio import AzureCliCredential
from agent_framework import tool

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def retrieve_company_report(company_code: str, detailed: bool) -> str:
    if company_code != "CNTS":
        raise ValueError("Company code not found")
    if not detailed:
        return "CNTS is a company that specializes in technology."
    return (
        "CNTS is a company that specializes in technology. "
        "It had a revenue of $10 million in 2022. It has 100 employees."
    )


async def main() -> None:
    """Example of memory usage with Mem0 context provider."""
    print("=== Mem0 Context Provider Example ===")

    # Each record in Mem0 should be associated with agent_id or user_id or application_id or thread_id.
    # In this example, we associate Mem0 records with user_id.
    user_id = str(uuid.uuid4())

    # For Azure authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    # For Mem0 authentication, set Mem0 API key via "api_key" parameter or MEM0_API_KEY environment variable.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="FriendlyAssistant",
            instructions="You are a friendly assistant.",
            tools=retrieve_company_report,
            context_provider=Mem0Provider(user_id=user_id),
        ) as agent,
    ):
        # First ask the agent to retrieve a company report with no previous context.
        # The agent will not be able to invoke the tool, since it doesn't know
        # the company code or the report format, so it should ask for clarification.
        query = "Please retrieve my company report"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Now tell the agent the company code and the report format that you want to use
        # and it should be able to invoke the tool and return the report.
        query = "I always work with CNTS and I always want a detailed report format. Please remember and retrieve it."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Mem0 processes and indexes memories asynchronously.
        # Wait for memories to be indexed before querying in a new thread.
        # In production, consider implementing retry logic or using Mem0's
        # eventual consistency handling instead of a fixed delay.
        print("Waiting for memories to be processed...")
        await asyncio.sleep(12)  # Empirically determined delay for Mem0 indexing

        print("\nRequest within a new thread:")
        # Create a new thread for the agent.
        # The new thread has no context of the previous conversation.
        thread = agent.get_new_thread()

        # Since we have the mem0 component in the thread, the agent should be able to
        # retrieve the company report without asking for clarification, as it will
        # be able to remember the user preferences from Mem0 component.
        query = "Please retrieve my company report"
        print(f"User: {query}")
        result = await agent.run(query, thread=thread)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
