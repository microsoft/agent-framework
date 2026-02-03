# Copyright (c) Microsoft. All rights reserved.
import asyncio
import json
from pathlib import Path

import aiofiles
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with OpenAPI Tool Example

This sample demonstrates usage of AzureAIProjectAgentProvider with OpenAPI tools
to call external APIs defined by OpenAPI specifications.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. The countries.json OpenAPI specification is included in the resources folder.
"""


async def main() -> None:
    # Load the OpenAPI specification
    resources_path = Path(__file__).parent.parent / "resources" / "countries.json"

    async with aiofiles.open(resources_path, "r") as f:
        content = await f.read()
        openapi_countries = json.loads(content)

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="MyOpenAPIAgent",
            instructions="""You are a helpful assistant that can use country APIs to provide information.
            Use the available OpenAPI tools to answer questions about countries, currencies, and demographics.""",
            tools={
                "type": "openapi",
                "openapi": {
                    "name": "get_countries",
                    "spec": openapi_countries,
                    "description": "Retrieve information about countries by currency code",
                    "auth": {"type": "anonymous"},
                },
            },
        )

        query = "What is the name and population of the country that uses currency with abbreviation THB?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
