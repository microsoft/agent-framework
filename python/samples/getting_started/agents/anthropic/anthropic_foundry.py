# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedMCPTool, HostedWebSearchTool
from agent_framework_anthropic import AnthropicClient

"""
Anthropic Foundry Chat Agent Example

This sample demonstrates using Anthropic via Azure AI Foundry with:
- Setting up an Anthropic-based agent with hosted tools.
- Using the `thinking` feature.
- Displaying both thinking and usage information during streaming responses.

To use the Foundry integration ensure you have the following environment variables set:
- ANTHROPIC_FOUNDRY_API_KEY
    Or use ad_token_provider parameter for Azure AD authentication.
- ANTHROPIC_FOUNDRY_RESOURCE
    Your Azure resource name (e.g., "my-resource" for https://my-resource.services.ai.azure.com/models)
    Alternatively, set ANTHROPIC_FOUNDRY_BASE_URL directly.
- ANTHROPIC_CHAT_MODEL_ID
    Should be something like claude-haiku-4-5

You can also explicitly set the backend:
- ANTHROPIC_CHAT_CLIENT_BACKEND=foundry
"""


async def main() -> None:
    """Example of streaming response with Azure AI Foundry backend."""
    # The backend="foundry" explicitly selects Azure AI Foundry
    # Without it, the backend is auto-detected based on available credentials
    agent = AnthropicClient(backend="foundry").as_agent(
        name="DocsAgent",
        instructions="You are a helpful agent for both Microsoft docs questions and general questions.",
        tools=[
            HostedMCPTool(
                name="Microsoft Learn MCP",
                url="https://learn.microsoft.com/api/mcp",
            ),
            HostedWebSearchTool(),
        ],
        default_options={
            # anthropic needs a value for the max_tokens parameter
            # we set it to 1024, but you can override like this:
            "max_tokens": 20000,
            "thinking": {"type": "enabled", "budget_tokens": 10000},
        },
    )

    query = "Can you compare Python decorators with C# attributes?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        for content in chunk.contents:
            if content.type == "text_reasoning":
                print(f"\033[32m{content.text}\033[0m", end="", flush=True)
            if content.type == "usage":
                print(
                    f"\n\033[34m[Usage so far: {content.usage_details}]\033[0m\n",
                    end="",
                    flush=True,
                )
        if chunk.text:
            print(chunk.text, end="", flush=True)

    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
