# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.azure import AzureAIClient, AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Client with Foundry Tools Example.

This sample uses ``AzureAIProjectAgentProvider`` for agent setup while sourcing
all Foundry tool configurations from ``AzureAIClient`` helper methods.

Important:
- This sample is intentionally non-defensive and includes direct tool wiring.
- Comment out any tool entries you do not want to use, or whose required environment
  variables/connections you have not configured yet.

Required project settings:
- AZURE_AI_PROJECT_ENDPOINT
- AZURE_AI_MODEL_DEPLOYMENT_NAME

Tool-to-environment mapping used in this sample:
- client.get_file_search_tool(...): FILE_SEARCH_VECTOR_STORE_ID (explicitly read in code).
- client.get_bing_tool(variant="grounding"): BING_PROJECT_CONNECTION_ID.
- client.get_bing_tool(variant="custom_search"):
  BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID and BING_CUSTOM_SEARCH_INSTANCE_NAME.
- client.get_fabric_data_agent_tool(): FABRIC_PROJECT_CONNECTION_ID.
- client.get_sharepoint_grounding_tool(): SHAREPOINT_PROJECT_CONNECTION_ID.
- client.get_azure_ai_search_tool(...): AI_SEARCH_PROJECT_CONNECTION_ID and AI_SEARCH_INDEX_NAME.
- client.get_browser_automation_tool(): BROWSER_AUTOMATION_PROJECT_CONNECTION_ID.
- client.get_a2a_tool(): A2A_PROJECT_CONNECTION_ID (optionally A2A_ENDPOINT for base_url).

No additional environment settings are required for:
- client.get_code_interpreter_tool()
- client.get_web_search_tool(...)
- client.get_image_generation_tool(...)
- client.get_mcp_tool(...)
- client.get_openapi_tool(...)

For Memory, we have two approaches:
- client.get_memory_search_tool(...)
To run the memory service in Foundry within the Agent Framework code as a ContextProvider, see:
- samples/02-agents/context_providers/azure_ai_foundry_memory.py
"""


async def main() -> None:
    print("=== Azure AI Client with Foundry Tools Example ===")

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        ) as provider,
    ):
        client = AzureAIClient(credential=credential)
        agent = await provider.create_agent(
            name="FoundryToolsAgent",
            instructions="You are a helpful assistant that can use Foundry-hosted tools when useful.",
            tools=[
                client.get_code_interpreter_tool(),
                client.get_web_search_tool(
                    user_location={"country": "US", "city": "Seattle"}
                ),
                client.get_image_generation_tool(),
                client.get_mcp_tool(
                    name="Microsoft Learn MCP",
                    url="https://learn.microsoft.com/api/mcp",
                    approval_mode="never_require",
                ),
                client.get_openapi_tool(
                    name="get_countries",
                    spec={
                        "openapi": "3.0.0",
                        "info": {"title": "Countries API", "version": "1.0.0"},
                        "paths": {
                            "/countries": {
                                "get": {
                                    "operationId": "listCountries",
                                    "responses": {"200": {"description": "OK"}},
                                }
                            }
                        },
                    },
                    description="Retrieve information about countries.",
                    auth={"type": "anonymous"},
                ),
                client.get_memory_search_tool(
                    memory_store_name="agent-framework-memory-store",
                    scope="user_123",
                    update_delay=1,
                ),
                client.get_file_search_tool(
                    vector_store_ids=os.environ["FILE_SEARCH_VECTOR_STORE_ID"]
                ),
                client.get_bing_tool(variant="grounding"),
                client.get_bing_tool(variant="custom_search"),
                client.get_fabric_data_agent_tool(),
                client.get_sharepoint_grounding_tool(),
                client.get_azure_ai_search_tool(query_type="simple"),
                client.get_browser_automation_tool(),
                client.get_a2a_tool(),
            ],
        )

        query = "List the tool categories available to you and when each category is useful."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
