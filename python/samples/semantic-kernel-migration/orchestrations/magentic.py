# Copyright (c) Microsoft. All rights reserved.

"""Side-by-side Magentic orchestrations for Agent Framework and Semantic Kernel."""

import asyncio
from collections.abc import Sequence
from typing import cast

from agent_framework import ChatAgent, HostedCodeInterpreterTool, MagenticBuilder, WorkflowOutputEvent
from agent_framework.openai import OpenAIChatClient, OpenAIResponsesClient
from semantic_kernel.agents import (
    Agent,
    ChatCompletionAgent,
    MagenticOrchestration,
    OpenAIAssistantAgent,
    StandardMagenticManager,
)
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion, OpenAISettings
from semantic_kernel.contents import ChatMessageContent

PROMPT = (
    "I am preparing a report on the energy efficiency of different machine learning model architectures. "
    "Compare the estimated training and inference energy consumption of ResNet-50, BERT-base, and GPT-2 "
    "on standard datasets (e.g., ImageNet for ResNet, GLUE for BERT, WebText for GPT-2). "
    "Then, estimate the CO2 emissions associated with each, assuming training on an Azure Standard_NC6s_v3 VM "
    "for 24 hours. Provide tables for clarity, and recommend the most energy-efficient model per task type "
    "(image classification, text classification, and text generation)."
)


######################################################################
# Semantic Kernel orchestration path
######################################################################


async def build_semantic_kernel_agents() -> list[Agent]:
    research_agent = ChatCompletionAgent(
        name="ResearchAgent",
        description="A helpful assistant with access to web search. Ask it to perform web searches.",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        service=OpenAIChatCompletion(ai_model_id="gpt-4o-search-preview"),
    )

    client = OpenAIAssistantAgent.create_client()
    code_interpreter_tool, code_interpreter_tool_resources = OpenAIAssistantAgent.configure_code_interpreter_tool()
    openai_settings = OpenAISettings()
    model_id = openai_settings.chat_model_id if openai_settings.chat_model_id else "gpt-5"
    definition = await client.beta.assistants.create(
        model=model_id,
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        tools=code_interpreter_tool,
        tool_resources=code_interpreter_tool_resources,
    )
    coder_agent = OpenAIAssistantAgent(
        client=client,
        definition=definition,
    )

    return [research_agent, coder_agent]


def sk_agent_response_callback(
    message: ChatMessageContent | Sequence[ChatMessageContent],
) -> None:
    if isinstance(message, ChatMessageContent):
        messages: Sequence[ChatMessageContent] = [message]
    elif isinstance(message, Sequence) and not isinstance(message, (str, bytes)):
        messages = [item for item in message if isinstance(item, ChatMessageContent)]
    else:
        messages = []

    for item in messages:
        content = item.content or ""
        print(f"**{item.name}**\n{content}\n")


async def run_semantic_kernel_example(prompt: str) -> Sequence[ChatMessageContent]:
    agents = await build_semantic_kernel_agents()
    magentic_orchestration = MagenticOrchestration(
        members=agents,
        manager=StandardMagenticManager(chat_completion_service=OpenAIChatCompletion()),
        agent_response_callback=sk_agent_response_callback,
    )

    runtime = InProcessRuntime()
    runtime.start()

    try:
        orchestration_result = await magentic_orchestration.invoke(task=prompt, runtime=runtime)
        value = await orchestration_result.get()
        if isinstance(value, ChatMessageContent):
            return [value]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [item for item in value if isinstance(item, ChatMessageContent)]
        return []
    finally:
        await runtime.stop_when_idle()


def _print_semantic_kernel_outputs(outputs: Sequence[ChatMessageContent]) -> None:
    if not outputs:
        print("No Semantic Kernel output.")
        return

    print("===== Semantic Kernel Magentic =====")
    for item in outputs:
        content = item.content or ""
        print(f"**{item.name}**\n{content}\n")


######################################################################
# Agent Framework orchestration path
######################################################################


async def run_agent_framework_example(prompt: str) -> str | None:
    researcher = ChatAgent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-search-preview"),
    )

    coder = ChatAgent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        chat_client=OpenAIResponsesClient(),
        tools=HostedCodeInterpreterTool(),
    )

    # Create a manager agent for orchestration
    manager_agent = ChatAgent(
        name="MagenticManager",
        description="Orchestrator that coordinates the research and coding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        chat_client=OpenAIChatClient(),
    )

    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher, coder=coder)
        .with_standard_manager(agent=manager_agent)
        .build()
    )

    final_text: str | None = None
    async for event in workflow.run_stream(prompt):
        if isinstance(event, WorkflowOutputEvent):
            final_text = cast(str, event.data)

    return final_text


def _print_agent_framework_output(result: str | None) -> None:
    if result is None:
        print("No Agent Framework output.")
        return

    print("===== Agent Framework Magentic =====")
    print(result)


async def main() -> None:
    agent_framework_result = await run_agent_framework_example(PROMPT)
    _print_agent_framework_output(agent_framework_result)

    semantic_kernel_outputs = await run_semantic_kernel_example(PROMPT)
    _print_semantic_kernel_outputs(semantic_kernel_outputs)


if __name__ == "__main__":
    asyncio.run(main())
