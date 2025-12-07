# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import ChatAgent, GroupChatBuilder
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

    workflow = (
        GroupChatBuilder()
        .set_manager(manager=OpenAIChatClient().create_agent(), display_name="Coordinator")
        .participants(researcher=researcher, writer=writer)
        .build()
    )

    task = "Outline the core considerations for planning a community hackathon, and finish with a concise action plan."

    print("\nStarting Group Chat Workflow...\n")
    print(f"Input: {task}\n")

    try:
        workflow_agent = workflow.as_agent(name="GroupChatWorkflowAgent")
        agent_result = await workflow_agent.run(task)

        if agent_result.messages:
            print("\n===== as_agent() Transcript =====")
            for i, msg in enumerate(agent_result.messages, start=1):
                role_value = getattr(msg.role, "value", msg.role)
                speaker = msg.author_name or role_value
                print(f"{'-' * 50}\n{i:02d} [{speaker}]\n{msg.text}")

    except Exception as e:
        print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
