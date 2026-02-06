# Copyright (c) Microsoft. All rights reserved.
"""Attach a lightweight function tool to the Responses API in SK and AF."""

import asyncio


async def run_semantic_kernel() -> None:
    from azure.identity import AzureCliCredential
    from semantic_kernel.agents import AzureResponsesAgent
    from semantic_kernel.connectors.ai.open_ai import AzureOpenAISettings
    from semantic_kernel.functions import kernel_function

    class MathPlugin:
        @kernel_function(name="add", description="Add two numbers")
        def add(self, a: float, b: float) -> float:
            return a + b

    credential = AzureCliCredential()
    try:
        client = AzureResponsesAgent.create_client(credential=credential)
        # Plugins advertise callable tools to the Responses agent.
        agent = AzureResponsesAgent(
            ai_model_id=AzureOpenAISettings().responses_deployment_name,
            client=client,
            instructions="Use the add tool when math is required.",
            name="MathExpert",
            plugins=[MathPlugin()],
        )
        response = await agent.get_response("Use add(41, 1) and explain the result.")
        print("[SK]", response.message.content)
    finally:
        await credential.close()


async def run_agent_framework() -> None:
    from agent_framework import ChatAgent
    from agent_framework._tools import tool
    from agent_framework.openai import OpenAIResponsesClient

    @tool(name="add", description="Add two numbers")
    async def add(a: float, b: float) -> float:
        return a + b

    chat_agent = ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="Use the add tool when math is required.",
        name="MathExpert",
        # AF registers the async function as a tool at construction.
        tools=[add],
    )
    reply = await chat_agent.run("Use add(41, 1) and explain the result.")
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
