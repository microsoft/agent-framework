# Copyright (c) Microsoft. All rights reserved.

"""Azure Managed Redis History Provider with Azure AD Authentication

This example demonstrates how to use Azure Managed Redis with Azure AD authentication
to persist conversational details using RedisHistoryProvider.

Requirements:
  - Azure Managed Redis instance with Azure AD authentication enabled
  - Azure credentials configured (az login or managed identity)
  - agent-framework-redis: pip install agent-framework-redis
  - azure-identity: pip install azure-identity

Environment Variables:
  - AZURE_REDIS_HOST: Your Azure Managed Redis host (e.g., myredis.redis.cache.windows.net)
  - AZURE_AI_PROJECT_ENDPOINT: Your Azure AI Foundry project endpoint
  - AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME: Azure OpenAI Responses deployment name
  - AZURE_USER_OBJECT_ID: Your Azure AD User Object ID for authentication
"""

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.redis import RedisHistoryProvider
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv
from redis.credentials import CredentialProvider

# Load environment variables from .env file
load_dotenv()


class AzureCredentialProvider(CredentialProvider):
    """Credential provider for Azure AD authentication with Redis Enterprise."""

    def __init__(self, azure_credential: AsyncAzureCliCredential, user_object_id: str):
        self.azure_credential = azure_credential
        self.user_object_id = user_object_id

    async def get_credentials_async(self) -> tuple[str] | tuple[str, str]:
        """Get Azure AD token for Redis authentication.

        Returns (username, token) where username is the Azure user's Object ID.
        """
        token = await self.azure_credential.get_token("https://redis.azure.com/.default")
        return (self.user_object_id, token.token)


async def main() -> None:
    redis_host = os.environ.get("AZURE_REDIS_HOST")
    if not redis_host:
        print("ERROR: Set AZURE_REDIS_HOST environment variable")
        return

    # For Azure Redis with Entra ID, username must be your Object ID
    user_object_id = os.environ.get("AZURE_USER_OBJECT_ID")
    if not user_object_id:
        print("ERROR: Set AZURE_USER_OBJECT_ID environment variable")
        print("Get your Object ID from the Azure Portal")
        return

    # Create Azure CLI credential provider (uses 'az login' credentials)
    azure_credential = AsyncAzureCliCredential()
    credential_provider = AzureCredentialProvider(azure_credential, user_object_id)

    # Create Azure Redis history provider
    history_provider = RedisHistoryProvider(
        source_id="redis_memory",
        credential_provider=credential_provider,
        host=redis_host,
        port=10000,
        ssl=True,
        key_prefix="chat_messages",
        max_messages=100,
    )

    # Create chat client
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    # Create agent with Azure Redis history provider
    agent = client.as_agent(
        name="AzureRedisAssistant",
        instructions="You are a helpful assistant.",
        context_providers=[history_provider],
    )

    # Conversation
    query = "Remember that I enjoy gumbo"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    # Ask the agent to recall the stored preference; it should retrieve from memory
    query = "What do I enjoy?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "What did I say to you just now?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "Remember that I have a meeting at 3pm tomorrow"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "Tulips are red"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    query = "What was the first thing I said to you this conversation?"
    result = await agent.run(query)
    print("User: ", query)
    print("Agent: ", result)

    # Cleanup
    await azure_credential.close()


if __name__ == "__main__":
    asyncio.run(main())
