# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos import CosmosHistoryProvider

"""
This sample demonstrates CosmosHistoryProvider as an agent context provider.

Key components:
- AzureOpenAIResponsesClient configured with an Azure AI project endpoint
- CosmosHistoryProvider configured for Cosmos DB-backed message history
- Provider-configured container name with session_id as partition key

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME
  AZURE_COSMOS_ENDPOINT
  AZURE_COSMOS_DATABASE_NAME
  AZURE_COSMOS_CONTAINER_NAME
Optional:
  AZURE_COSMOS_KEY
"""

# Load environment variables from .env file.
load_dotenv()


async def main() -> None:
    """Run the Cosmos history provider sample with an Agent."""
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    deployment_name = os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    cosmos_container_name = os.getenv("AZURE_COSMOS_CONTAINER_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")

    if (
        not project_endpoint
        or not deployment_name
        or not cosmos_endpoint
        or not cosmos_database_name
        or not cosmos_container_name
    ):
        print(
            "Please set AZURE_AI_PROJECT_ENDPOINT, AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME, "
            "AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, and AZURE_COSMOS_CONTAINER_NAME."
        )
        return

    # 1. Create the Azure OpenAI Responses client using project endpoint auth.
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=project_endpoint,
        deployment_name=deployment_name,
        credential=credential,
    )

    # 3. Create an agent that uses the history provider as a context provider.
    async with (
        CosmosHistoryProvider(
            endpoint=cosmos_endpoint,
            database_name=cosmos_database_name,
            container_name=cosmos_container_name,
            credential=cosmos_key or credential,
        ) as history_provider,
        client.as_agent(
            name="CosmosHistoryAgent",
            instructions="You are a helpful assistant that remembers prior turns.",
            context_providers=[history_provider],
            default_options={"store": False},
        ) as agent,
    ):
        # 4. Create a session (session_id is used as the partition key).
        session = agent.create_session()

        # 5. Run a multi-turn conversation; history is persisted by CosmosHistoryProvider.
        response1 = await agent.run("My name is Ada and I enjoy distributed systems.", session=session)
        print(f"Assistant: {response1.text}")

        response2 = await agent.run("What do you remember about me?", session=session)
        print(f"Assistant: {response2.text}")
        print(f"Container: {history_provider.container_name}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Assistant: Nice to meet you, Ada! Distributed systems are a fascinating area.
Assistant: You told me your name is Ada and that you enjoy distributed systems.
Container: <AZURE_COSMOS_CONTAINER_NAME>
"""
