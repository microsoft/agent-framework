# Copyright (c) Microsoft. All rights reserved.

"""Side-by-side sequential orchestrations for Agent Framework and Semantic Kernel."""

import asyncio
from typing import cast

from agent_framework import ChatMessage, Role, SequentialBuilder, WorkflowOutputEvent
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential
from semantic_kernel.agents import Agent, ChatCompletionAgent, SequentialOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatMessageContent

PROMPT = "Write a tagline for a budget-friendly eBike."


def build_semantic_kernel_agents() -> list[Agent]:
    credential = AzureCliCredential()

    writer_agent = ChatCompletionAgent(
        name="WriterAgent",
        instructions=(
            "You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."
        ),
        service=AzureChatCompletion(credential=credential),
    )

    reviewer_agent = ChatCompletionAgent(
        name="ReviewerAgent",
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        service=AzureChatCompletion(credential=credential),
    )

    return [writer_agent, reviewer_agent]


def sk_agent_response_callback(message: ChatMessageContent) -> None:
    content = message.content or ""
    print(f"# {message.name}\n{content}\n")


async def run_agent_framework_example(prompt: str) -> list[ChatMessage]:
    chat_client = AzureChatClient(credential=AzureCliCredential())

    writer = chat_client.create_agent(
        instructions=(
            "You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."
        ),
        name="writer",
    )

    reviewer = chat_client.create_agent(
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
    )

    workflow = SequentialBuilder().participants([writer, reviewer]).build()

    conversation_outputs: list[list[ChatMessage]] = []
    async for event in workflow.run_stream(prompt):
        if isinstance(event, WorkflowOutputEvent):
            conversation_outputs.append(cast(list[ChatMessage], event.data))

    return conversation_outputs[-1] if conversation_outputs else []


async def run_semantic_kernel_example(prompt: str) -> str:
    sequential_orchestration = SequentialOrchestration(
        members=build_semantic_kernel_agents(),
        agent_response_callback=sk_agent_response_callback,
    )

    runtime = InProcessRuntime()
    runtime.start()

    try:
        orchestration_result = await sequential_orchestration.invoke(task=prompt, runtime=runtime)
        final_message = await orchestration_result.get(timeout=20)
        if isinstance(final_message, ChatMessageContent):
            return final_message.content or ""
        return str(final_message)
    finally:
        await runtime.stop_when_idle()


def _format_conversation(conversation: list[ChatMessage]) -> None:
    if not conversation:
        print("No Agent Framework output.")
        return

    print("===== Agent Framework Sequential =====")
    for index, message in enumerate(conversation, start=1):
        name = message.author_name or ("assistant" if message.role == Role.ASSISTANT else "user")
        print(f"{'-' * 60}\n{index:02d} [{name}]\n{message.text}")
    print()


async def main() -> None:
    conversation = await run_agent_framework_example(PROMPT)
    _format_conversation(conversation)

    print("===== Semantic Kernel Sequential =====")
    final_text = await run_semantic_kernel_example(PROMPT)
    print(final_text)


if __name__ == "__main__":
    asyncio.run(main())
