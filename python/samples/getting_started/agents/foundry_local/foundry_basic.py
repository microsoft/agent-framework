# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.foundry import FoundryLocalChatClient


async def non_streaming_example(client: FoundryLocalChatClient) -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.

    agent = client.create_agent(
        name="LocalAgent",
        instructions="You are a helpful agent.",
    )
    query = "How do you calculate a factorial? Please share some python code snippets to illustrate."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example(client: FoundryLocalChatClient) -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = client.create_agent(
        name="LocalAgent",
        instructions="You are a helpful agent.",
    )
    query = "How do you calculate a factorial? Please share some python code snippets to illustrate."
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_streaming(query):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Basic Foundry Chat Client Agent Example ===")

    client = FoundryLocalChatClient(ai_model_id="phi-4-mini-reasoning")
    print(f"Client Model ID: {client.ai_model_id}\n")
    print("Other available models:")
    for model in client.manager.list_catalog_models():
        print(
            f"- {model.alias} for {model.task} - id={model.id} - {(model.file_size_mb / 1000):.2f} GB - {model.license}"
        )

    await non_streaming_example(client)
    await streaming_example(client)


if __name__ == "__main__":
    asyncio.run(main())
