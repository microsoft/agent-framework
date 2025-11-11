# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid

from agent_framework.azure import AzureAIAgentClient
from agent_framework_zep import ZepProvider
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
    """Example of memory usage with Zep context provider."""
    print("=== Zep Context Provider Example ===\n")

    # Zep requires a user_id for all threads. In a real application,
    # this would be your application's user identifier.
    user_id = "demo_user_" + str(uuid.uuid4())[:8]
    print(f"Using user_id: {user_id}")

    # For Azure authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    # For Zep authentication, set Zep API key via "api_key" parameter or ZEP_API_KEY environment variable.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="FriendlyAssistant",
            instructions="You are a friendly assistant.",
            tools=retrieve_company_report,
            context_providers=ZepProvider(user_id=user_id),
        ) as agent,
    ):
        # First ask the agent to retrieve a company report with no previous context.
        # The agent will not be able to invoke the tool, since it doesn't know
        # the company code or the report format, so it should ask for clarification.
        query = "Please retrieve my company report"
        print(f"\n[First Request]")
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Now tell the agent the company code and the report format that you want to use
        # and it should be able to invoke the tool and return the report.
        query = "I always work with CNTS and I always want a detailed report format. Please remember and retrieve it."
        print(f"[Teaching Preferences]")
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        print("\n=== Creating a New Thread ===")
        # Create a new thread for the agent.
        # The new thread has no conversation history, but Zep's knowledge graph
        # will still provide relevant context about the user's preferences.
        thread = agent.get_new_thread()

        # Since Zep builds a knowledge graph across all threads, the agent should be able to
        # retrieve the company report without asking for clarification, even in this new thread.
        # The provider will automatically create a new Zep thread when the framework
        # assigns a service_thread_id to this conversation.
        query = "Please retrieve my company report"
        print(f"[New Thread Request]")
        print(f"User: {query}")
        result = await agent.run(query, thread=thread)
        print(f"Agent: {result}\n")

        print("\n✓ Zep successfully remembered user preferences across threads!")


if __name__ == "__main__":
    asyncio.run(main())
