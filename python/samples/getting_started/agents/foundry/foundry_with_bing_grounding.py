# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio

from agent_framework import AgentRunResponse, ChatAgent, FunctionCallContent, HostedWebSearchTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential


async def main() -> None:
    """Example showing how to use the HostedCodeInterpreterTool with Foundry."""
    print("=== Foundry Agent with Code Interpreter Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=FoundryChatClient(async_credential=credential),
            instructions="You are a helpful assistant that search the web to answer questions.",
            tools=HostedWebSearchTool(),
        ) as agent,
    ):
        query = "what is the top news today?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        all_updates = []
        async for update in agent.run_stream(query):
            all_updates.append(update)
            if update.text:
                print(update.text, end="", flush=True)

        full_response = AgentRunResponse.from_agent_run_response_updates(all_updates)
        for messages in full_response.messages:
            for content in messages.contents:
                if isinstance(content, FunctionCallContent):
                    print("\n\nFunction Call:")
                    print(f"Name: {content.name}")
                    print(f"Arguments: {content.arguments}")


if __name__ == "__main__":
    asyncio.run(main())
