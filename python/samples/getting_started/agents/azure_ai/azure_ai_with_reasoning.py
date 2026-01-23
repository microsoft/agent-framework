# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.models import Reasoning
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Reasoning Example

Demonstrates how to enable reasoning capabilities using the Reasoning option.
Shows both non-streaming and streaming approaches, including how to access
reasoning content (type="text_reasoning") separately from answer content.

Requires a reasoning-capable model (e.g., gpt-5.2) deployed in your Azure AI Project configured
as `AZURE_AI_MODEL_DEPLOYMENT_NAME` in your environment.
"""


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="ReasoningWeatherAgent",
            instructions="You are a helpful weather agent who likes to understand the underlying physics.",
            default_options={"reasoning": Reasoning(effort="medium", summary="concise")},
        )

        query = "How does the Bernoulli effect work?"
        print(f"User: {query}")
        result = await agent.run(query)

        for msg in result.messages:
            for content in msg.contents:
                if content.type == "text_reasoning":
                    print(f"[Reasoning]: {content.text}")
                elif content.type == "text":
                    print(f"[Answer]: {content.text}")
            print()


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="ReasoningWeatherAgent",
            instructions="You are a helpful weather agent who likes to understand the underlying physics.",
            default_options={"reasoning": Reasoning(effort="medium", summary="concise")},
        )

        query = "Help explain how air updrafts work?"
        print(f"User: {query}")

        shown_reasoning_label = False
        shown_text_label = False
        async for chunk in agent.run_stream(query):
            for content in chunk.contents:
                if content.type == "text_reasoning":
                    if not shown_reasoning_label:
                        print("[Reasoning]: ", end="", flush=True)
                        shown_reasoning_label = True
                    print(content.text, end="", flush=True)
                elif content.type == "text":
                    if not shown_text_label:
                        print("\n\n[Answer]: ", end="", flush=True)
                        shown_text_label = True
                    print(content.text, end="", flush=True)
        print("\n")


async def main() -> None:
    print("=== Azure AI Agent with Reasoning Example ===")

    # await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
