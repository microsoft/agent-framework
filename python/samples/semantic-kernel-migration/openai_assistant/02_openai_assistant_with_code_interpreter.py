# Copyright (c) Microsoft. All rights reserved.
"""Enable the code interpreter tool for OpenAI Assistants in SK and AF."""

import asyncio


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import OpenAIAssistantAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAISettings

    client = OpenAIAssistantAgent.create_client()

    code_interpreter_tool, code_interpreter_tool_resources = OpenAIAssistantAgent.configure_code_interpreter_tool()

    # Enable the hosted code interpreter tool on the assistant definition.
    definition = await client.beta.assistants.create(
        model=OpenAISettings().chat_deployment_name,
        name="CodeRunner",
        instructions="Run the provided request as code and return the result.",
        tools=code_interpreter_tool,
        tool_resources=code_interpreter_tool_resources,
    )
    agent = OpenAIAssistantAgent(client=client, definition=definition)
    response = await agent.get_response(
        "Use Python to calculate the mean of [41, 42, 45] and explain the steps.",
    )
    print(f"[SK]: {response}")


async def run_agent_framework() -> None:
    from agent_framework import HostedCodeInterpreterTool
    from agent_framework.openai import OpenAIAssistantsClient

    assistants_client = OpenAIAssistantsClient()
    # AF exposes the same tool configuration via create_agent.
    async with assistants_client.as_agent(
        name="CodeRunner",
        instructions="Use the code interpreter when calculations are required.",
        model="gpt-4.1",
        tools=[HostedCodeInterpreterTool()],
    ) as assistant_agent:
        response = await assistant_agent.run(
            "Use Python to calculate the mean of [41, 42, 45] and explain the steps.",
            tool_choice="auto",
        )
        print(f"[AF]: {response.text}")


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
