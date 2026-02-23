# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/orchestrations/sequential.py

# Copyright (c) Microsoft. All rights reserved.

"""Side-by-side sequential orchestrations for Agent Framework and Semantic Kernel."""

import asyncio
from collections.abc import Sequence
from typing import cast

from agent_framework import Message
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from semantic_kernel.agents import Agent, ChatCompletionAgent, SequentialOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatMessageContent

# Load environment variables from .env file
load_dotenv()

PROMPT = "Write a tagline for a budget-friendly eBike."


######################################################################
# Semantic Kernel orchestration path
######################################################################


def build_semantic_kernel_agents() -> list[Agent]:
    credential = AzureCliCredential()

    writer_agent = ChatCompletionAgent(
        name="WriterAgent",
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        service=AzureChatCompletion(credential=credential),
    )

    reviewer_agent = ChatCompletionAgent(
        name="ReviewerAgent",
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        service=AzureChatCompletion(credential=credential),
    )

    return [writer_agent, reviewer_agent]


async def sk_agent_response_callback(
    message: ChatMessageContent | Sequence[ChatMessageContent],
) -> None:
    if isinstance(message, ChatMessageContent):
        messages: Sequence[ChatMessageContent] = [message]
    elif isinstance(message, Sequence) and not isinstance(message, (str, bytes)):
        messages = list(message)
    else:
        messages = [cast(ChatMessageContent, message)]

    for item in messages:
        content = item.content or ""
        print(f"# {item.name}\n{content}\n")


######################################################################
# Agent Framework orchestration path
######################################################################


async def run_agent_framework_example(prompt: str) -> list[Message]:
    client = AzureOpenAIChatClient(credential=AzureCliCredential())

    writer = client.as_agent(
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        name="writer",
    )

    reviewer = client.as_agent(
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
    )

    workflow = SequentialBuilder(participants=[writer, reviewer]).build()

    conversation_outputs: list[list[Message]] = []
    async for event in workflow.run(prompt, stream=True):
        if event.type == "output":
            conversation_outputs.append(cast(list[Message], event.data))

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


def _format_conversation(conversation: list[Message]) -> None:
    if not conversation:
        print("No Agent Framework output.")
        return

    print("===== Agent Framework Sequential =====")
    for index, message in enumerate(conversation, start=1):
        name = message.author_name or ("assistant" if message.role == "assistant" else "user")
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
