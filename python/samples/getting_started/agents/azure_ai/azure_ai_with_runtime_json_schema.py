# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent Response Format Example with Runtime JSON Schema

This sample demonstrates basic usage of AzureAIClient with response format,
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
    """Example of using response_format property."""

    # Since no Agent ID is provided, the agent will be automatically created.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="ProductMarketerAgent",
            instructions="Return launch briefs as structured JSON.",
        ) as agent,
    ):
        query = "Draft a launch brief for the Contoso Note app."
        print(f"User: {query}")
        result = await agent.run(
            query,
            # Specify type to use as response
            additional_chat_options={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": runtime_schema["title"],
                        "strict": True,
                        "schema": runtime_schema,
                    },
                },
            },
        )

        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
