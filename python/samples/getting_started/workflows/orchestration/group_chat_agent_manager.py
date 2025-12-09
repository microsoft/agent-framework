# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from typing import cast

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    GroupChatBuilder,
    Role,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

logging.basicConfig(level=logging.INFO)

"""
Sample: Group Chat with Agent-Based Manager

What it does:
- Demonstrates the new set_manager() API for agent-based coordination
- Manager is a full ChatAgent with access to tools, context, and observability
- Coordinates a researcher and writer agent to solve tasks collaboratively

Prerequisites:
- OpenAI environment variables configured for OpenAIChatClient
"""


def _get_chat_client() -> AzureOpenAIChatClient:
    return AzureOpenAIChatClient(credential=AzureCliCredential())


async def main() -> None:
    # Create coordinator agent with structured output for speaker selection
    # Note: response_format is enforced to ManagerSelectionResponse by set_manager()
    coordinator = ChatAgent(
        name="Coordinator",
        description="Coordinates multi-agent collaboration by selecting speakers",
        instructions="""
You coordinate a team conversation to solve the user's task.

Review the conversation history and select the next participant to speak.

Guidelines:
- Start with Researcher to gather information
- Then have Writer synthesize the final answer
- Only finish after both have contributed meaningfully
- Allow for multiple rounds of information gathering if needed
""",
        chat_client=_get_chat_client(),
    )

    researcher = ChatAgent(
        name="Researcher",
        description="Collects relevant background information",
        instructions="Gather concise facts that help a teammate answer the question.",
        chat_client=_get_chat_client(),
    )

    writer = ChatAgent(
        name="Writer",
        description="Synthesizes polished answers from gathered information",
        instructions="Compose clear and structured answers using any notes provided.",
        chat_client=_get_chat_client(),
    )

    workflow = (
        GroupChatBuilder()
        .set_manager(coordinator, display_name="Orchestrator")
        .with_termination_condition(lambda messages: sum(1 for msg in messages if msg.role == Role.ASSISTANT) >= 2)
        .participants([researcher, writer])
        .build()
    )

    task = "What are the key benefits of using async/await in Python? Provide a concise summary."

    print("\nStarting Group Chat with Agent-Based Manager...\n")
    print(f"TASK: {task}\n")
    print("=" * 80)

    final_conversation: list[ChatMessage] = []
    last_executor_id: str | None = None
    async for event in workflow.run_stream(task):
        if isinstance(event, AgentRunUpdateEvent):
            eid = event.executor_id
            if eid != last_executor_id:
                if last_executor_id is not None:
                    print()
                print(f"{eid}:", end=" ", flush=True)
                last_executor_id = eid
            print(event.data, end="", flush=True)
        elif isinstance(event, WorkflowOutputEvent):
            final_conversation = cast(list[ChatMessage], event.data)

    if final_conversation and isinstance(final_conversation, list):
        print("\n\n" + "=" * 80)
        print("FINAL CONVERSATION")
        print("=" * 80)
        for msg in final_conversation:
            author = getattr(msg, "author_name", "Unknown")
            text = getattr(msg, "text", str(msg))
            print(f"\n[{author}]")
            print(text)
            print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())
