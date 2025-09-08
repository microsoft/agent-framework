# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.foundry import FoundryChatClient
from agent_framework.mem0 import Mem0Provider
from azure.identity.aio import AzureCliCredential


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

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="FriendlyAssistant",
            instructions="You are a friendly assistant.",
            tools=retrieve_company_report,
        ) as agent,
        # Set Mem0 API key via "api_key" parameter or MEM0_API_KEY environment variable.
        Mem0Provider(agent_id=agent.id) as context_provider,
    ):
        # Add Mem0 context provider
        agent.context_providers.add(context_provider)

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
