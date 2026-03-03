# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure OpenAI Responses Client with Foundry Tools Example.

If a ``AzureOpenAIResponsesClient`` is initialized with a Foundry project endpoint and valid credentials,
it will automatically wire up Foundry-hosted tools that are available to the agent.
This sample demonstrates how to set up such a client and use it within an agent, along with a variety of Foundry tools.

The same tools are available directly on the ``AzureAIClient`` as well,
so this wiring is not unique to the responses client.

Important:
- This sample is intentionally non-defensive and includes direct tool wiring.
- Comment out any tool entries you do not want to use, or whose required environment
  variables/connections you have not configured yet.

Required project settings:
- AZURE_AI_PROJECT_ENDPOINT
- AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME

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

For memory capabilities, prefer ``FoundryMemoryProvider`` from:
- samples/02-agents/context_providers/azure_ai_foundry_memory.py
"""


async def main() -> None:
    print("=== Azure OpenAI Responses Client with Foundry Tools Example ===")

    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    deployment_name = os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")

    client: Any = AzureOpenAIResponsesClient(
        project_endpoint=project_endpoint,
        deployment_name=deployment_name,
        credential=AzureCliCredential(),
    )

    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can use Foundry-hosted tools when useful.",
        tools=[
            client.get_code_interpreter_tool(),
            # client.get_web_search_tool(
            #     user_location={"country": "US", "city": "Seattle"}
            # ),
            client.get_image_generation_tool(),
            # client.get_mcp_tool(
            #     name="Microsoft Learn MCP",
            #     url="https://learn.microsoft.com/api/mcp",
            #     approval_mode="never_require",
            # ),
            # client.get_openapi_tool(
            #     name="get_countries",
            #     spec={
            #         "openapi": "3.0.0",
            #         "info": {"title": "Countries API", "version": "1.0.0"},
            #         "paths": {
            #             "/countries": {
            #                 "get": {
            #                     "operationId": "listCountries",
            #                     "responses": {"200": {"description": "OK"}},
            #                 }
            #             }
            #         },
            #     },
            #     description="Retrieve information about countries.",
            #     auth={"type": "anonymous"},
            # ),
            # client.get_file_search_tool(
            #     vector_store_ids=os.environ["FILE_SEARCH_VECTOR_STORE_ID"]
            # ),
            # client.get_bing_tool(variant="grounding"),
            # client.get_bing_tool(variant="custom_search"),
            # client.get_fabric_data_agent_tool(),
            # client.get_sharepoint_grounding_tool(),
            # client.get_azure_ai_search_tool(query_type="simple"),
            client.get_browser_automation_tool(),
            # client.get_a2a_tool(),
        ],
    )
    session = agent.create_session()

    user_message = input("User: ")
    while user_message.lower() not in {"exit", "quit"}:
        result = await agent.run(user_message, session=session)
        print(f"Agent: {result}")
        user_message = input("User: ")


if __name__ == "__main__":
    asyncio.run(main())
