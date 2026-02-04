# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from pydantic import BaseModel, ConfigDict

"""
Azure AI Agent Response Format Example

This sample demonstrates basic usage of AzureAIProjectAgentProvider with response format,
also known as structured outputs.
"""


class ReleaseBrief(BaseModel):
    feature: str
    benefit: str
    launch_date: str
    model_config = ConfigDict(extra="forbid")


async def main() -> None:
    """Example of using response_format property."""

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="ProductMarketerAgent",
            instructions="Return launch briefs as structured JSON.",
            # Specify Pydantic model for structured output via default_options
            default_options={"response_format": ReleaseBrief},
        )

        query = "Draft a launch brief for the Contoso Note app."
        print(f"User: {query}")
        result = await agent.run(query)

        if release_brief := result.try_parse_value(ReleaseBrief):
            print("Agent:")
            print(f"Feature: {release_brief.feature}")
            print(f"Benefit: {release_brief.benefit}")
            print(f"Launch date: {release_brief.launch_date}")
        else:
            print(f"Failed to parse response: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
