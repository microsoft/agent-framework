# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import ChatAgent, GroupChatBuilder, StandardGroupChatManager, WorkflowOutputEvent
from agent_framework.openai import OpenAIChatClient, OpenAIResponsesClient

logging.basicConfig(level=logging.INFO)

"""
Sample: Group Chat Orchestration (manager-directed)

What it does:
- Demonstrates the generic GroupChatBuilder with a language-model manager directing two agents.
- The manager coordinates a researcher (chat completions) and a writer (responses API) to solve a task.
- Uses the default group chat orchestration pipeline shared with Magentic.

Prerequisites:
- OpenAI environment variables configured for `OpenAIChatClient` and `OpenAIResponsesClient`.
"""


async def main() -> None:
    researcher = ChatAgent(
        name="Researcher",
        description="Collects relevant background information.",
        instructions="Gather concise facts that help a teammate answer the question.",
        chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),
    )

    writer = ChatAgent(
        name="Writer",
        description="Synthesizes a polished answer using the gathered notes.",
        instructions="Compose clear and structured answers using any notes provided.",
        chat_client=OpenAIResponsesClient(),
    )

    manager = StandardGroupChatManager(
        chat_client=OpenAIChatClient(),
        name="Coordinator",
    )

    workflow = (
        GroupChatBuilder()
        .set_manager(manager, display_name="Coordinator")
        .participants(researcher=researcher, writer=writer)
        .build()
    )

    task = "Outline the core considerations for planning a community hackathon, and finish with a concise action plan."

    print("\nStarting Group Chat Workflow...\n")
    print(f"TASK: {task}\n")

    final_response = None
    async for event in workflow.run_stream(task):
        if isinstance(event, WorkflowOutputEvent):
            final_response = getattr(event.data, "text", str(event.data))

    if final_response:
        print("=" * 60)
        print("FINAL RESPONSE")
        print("=" * 60)
        print(final_response)
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
