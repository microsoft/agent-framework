# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent Response Format Example with Runtime JSON Schema

This sample demonstrates basic usage of AzureAIProjectAgentProvider with response format,
also known as structured outputs.
"""


runtime_schema = {
    "title": "WeatherDigest",
    "type": "object",
    "properties": {
        "location": {"type": "string"},
        "conditions": {"type": "string"},
        "temperature_c": {"type": "number"},
        "advisory": {"type": "string"},
    },
    # OpenAI strict mode requires every property to appear in required.
    "required": ["location", "conditions", "temperature_c", "advisory"],
    "additionalProperties": False,
}


async def main() -> None:
    """Example of using response_format property with a runtime JSON schema."""

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Pass response_format via default_options using dict schema format
        agent = await provider.create_agent(
            name="WeatherDigestAgent",
            instructions="Return sample weather digest as structured JSON.",
            default_options={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": runtime_schema["title"],
                        "strict": True,
                        "schema": runtime_schema,
                    },
                }
            },
        )

        query = "Draft a sample weather digest."
        print(f"User: {query}")
        result = await agent.run(query)

        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
