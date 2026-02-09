# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential

"""
Azure OpenAI Provider

Demonstrates setting up AzureOpenAIResponsesClient and running a simple query.
Uses Azure Active Directory authentication via AzureCliCredential.

Environment variables:
- AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint
- AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME: Model deployment name

For more Azure OpenAI examples:
- With tools: getting_started/agents/azure_openai/azure_responses_client_with_function_tools.py
- With threads: getting_started/agents/azure_openai/azure_responses_client_with_thread.py
- Docs: https://learn.microsoft.com/agent-framework/providers/azure-openai
"""


async def main() -> None:
    print("=== Azure OpenAI Provider ===\n")

    # <create_agent>
    # For authentication, run `az login` or replace AzureCliCredential with your preferred credential.
    agent = AzureOpenAIResponsesClient(
        credential=AzureCliCredential(),
        api_version="preview",
    ).as_agent(
        name="AzureAgent",
        instructions="You are a helpful assistant.",
    )
    # </create_agent>

    # <run_query>
    query = "What is the capital of France?"
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Agent: {response}")
    # </run_query>


if __name__ == "__main__":
    asyncio.run(main())
