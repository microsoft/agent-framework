# Copyright (c) Microsoft. All rights reserved.

"""Side-by-side concurrent orchestrations for Agent Framework and Semantic Kernel."""

import asyncio
from collections.abc import Sequence
from typing import cast

from agent_framework import ChatMessage, ConcurrentBuilder, WorkflowOutputEvent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from semantic_kernel.agents import Agent, ChatCompletionAgent, ConcurrentOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatMessageContent

PROMPT = "Explain the concept of temperature from multiple scientific perspectives."


######################################################################
# Semantic Kernel orchestration path
######################################################################


def build_semantic_kernel_agents() -> list[Agent]:
    credential = AzureCliCredential()

    physics_agent = ChatCompletionAgent(
        name="PhysicsExpert",
        instructions=("You are an expert in physics. Answer questions from a physics perspective."),
        service=AzureChatCompletion(credential=credential),
    )

    chemistry_agent = ChatCompletionAgent(
        name="ChemistryExpert",
        instructions=("You are an expert in chemistry. Answer questions from a chemistry perspective."),
        service=AzureChatCompletion(credential=credential),
    )

    return [physics_agent, chemistry_agent]


async def run_semantic_kernel_example(prompt: str) -> Sequence[ChatMessageContent]:
    concurrent_orchestration = ConcurrentOrchestration(members=build_semantic_kernel_agents())

    runtime = InProcessRuntime()
    runtime.start()

    try:
        orchestration_result = await concurrent_orchestration.invoke(task=prompt, runtime=runtime)
        final_value = await orchestration_result.get(timeout=60)
        if isinstance(final_value, ChatMessageContent):
            return [final_value]
        if isinstance(final_value, Sequence):
            return list(final_value)
        return []
    finally:
        await runtime.stop_when_idle()


def _print_semantic_kernel_outputs(outputs: Sequence[ChatMessageContent]) -> None:
    if not outputs:
        print("No Semantic Kernel output.")
        return

    print("===== Semantic Kernel Concurrent =====")
    for item in outputs:
        content = item.content or ""
        print(f"# {item.name}\n{content}\n")


######################################################################
# Agent Framework orchestration path
######################################################################


async def run_agent_framework_example(prompt: str) -> Sequence[list[ChatMessage]]:
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    physics = chat_client.as_agent(
        instructions=("You are an expert in physics. Answer questions from a physics perspective."),
        name="physics",
    )

    chemistry = chat_client.as_agent(
        instructions=("You are an expert in chemistry. Answer questions from a chemistry perspective."),
        name="chemistry",
    )

    workflow = ConcurrentBuilder().participants([physics, chemistry]).build()

    outputs: list[list[ChatMessage]] = []
    async for event in workflow.run_stream(prompt):
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(cast(list[ChatMessage], event.data))

    return outputs


def _print_agent_framework_outputs(conversations: Sequence[Sequence[ChatMessage]]) -> None:
    if not conversations:
        print("No Agent Framework output.")
        return

    print("===== Agent Framework Concurrent =====")
    for index, conversation in enumerate(conversations, start=1):
        print(f"--- Conversation {index} ---")
        for message in conversation:
            name = message.author_name or "assistant"
            print(f"[{name}] {message.text}")
        print()


async def main() -> None:
    agent_framework_outputs = await run_agent_framework_example(PROMPT)
    _print_agent_framework_outputs(agent_framework_outputs)

    semantic_kernel_outputs = await run_semantic_kernel_example(PROMPT)
    _print_semantic_kernel_outputs(semantic_kernel_outputs)


if __name__ == "__main__":
    asyncio.run(main())
