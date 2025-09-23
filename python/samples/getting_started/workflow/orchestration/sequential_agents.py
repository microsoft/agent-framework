# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import cast

from agent_framework import ChatMessage, Role, SequentialBuilder, WorkflowOutputEvent
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Sample: Sequential workflow (agent-focused API) with shared conversation context

Build a high-level sequential workflow using SequentialBuilder and two domain agents.
The shared conversation (list[ChatMessage]) flows through each participant. Each agent
appends its assistant message to the context. The workflow outputs the final conversation
list when complete.

Note on internal adapters:
- Sequential orchestration includes small adapter nodes for input normalization
  ("input-conversation"), agent-response conversion ("to-conversation:<participant>"),
  and completion ("complete"). These may appear as ExecutorInvoke/Completed events in
  the stream—similar to how concurrent orchestration includes a dispatcher/aggregator.
  You can safely ignore them when focusing on agent progress.

Prerequisites:
- Azure OpenAI access configured for AzureChatClient (use az login + env vars)
"""


async def main() -> None:
    # 1) Create agents
    chat_client = AzureChatClient(credential=AzureCliCredential())

    writer = chat_client.create_agent(
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        name="writer",
    )

    reviewer = chat_client.create_agent(
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
    )

    # 2) Build sequential workflow: writer -> reviewer
    workflow = SequentialBuilder().participants([writer, reviewer]).build()

    # 3) Run and collect outputs
    outputs: list[list[ChatMessage]] = []
    async for event in workflow.run_stream("Write a tagline for a budget-friendly eBike."):
        if isinstance(event, WorkflowOutputEvent):
            outputs.append(cast(list[ChatMessage], event.data))

    if outputs:
        print("===== Final Conversation =====")
        for i, msg in enumerate(outputs[-1], start=1):
            name = msg.author_name or ("assistant" if msg.role == Role.ASSISTANT else "user")
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")

    """
    Sample Output:

    ===== Final Conversation =====
    ------------------------------------------------------------
    01 [user]
    Write a tagline for a budget-friendly eBike.
    ------------------------------------------------------------
    02 [writer]
    Ride farther, spend less—your affordable eBike adventure starts here.
    ------------------------------------------------------------
    03 [reviewer]
    This tagline clearly communicates affordability and the benefit of extended travel, making it
    appealing to budget-conscious consumers. It has a friendly and motivating tone, though it could
    be slightly shorter for more punch. Overall, a strong and effective suggestion!
    """


if __name__ == "__main__":
    asyncio.run(main())
