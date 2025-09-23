# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from typing_extensions import Never

from agent_framework import (
    ChatMessage,
    Executor,
    Role,
    SequentialBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Sample: Sequential workflow mixing agents and a custom summarizer executor

This demonstrates how SequentialBuilder chains participants with a shared
conversation context (list[ChatMessage]). An agent produces content; a custom
executor appends a compact summary to the conversation. The workflow completes
when idle, and the final output contains the complete conversation.

Custom executor contract:
- Provide at least one @handler accepting list[ChatMessage] and a WorkflowContext[list[ChatMessage]]
- Emit the updated conversation via ctx.send_message([...])

Note on internal adapters:
- You may see adapter nodes in the event stream such as "input-conversation",
  "to-conversation:<participant>", and "complete". These provide consistent typing,
  conversion of agent responses into the shared conversation, and a single point
  for completion—similar to concurrent's dispatcher/aggregator.

Prerequisites:
- Azure OpenAI access configured for AzureChatClient (use az login + env vars)
"""


class Summarizer(Executor):
    """Simple summarizer: consumes full conversation and appends an assistant summary."""

    @handler
    async def summarize(self, conversation: list[ChatMessage], ctx: WorkflowContext[Never, list[ChatMessage]]) -> None:
        users = sum(1 for m in conversation if m.role == Role.USER)
        assistants = sum(1 for m in conversation if m.role == Role.ASSISTANT)
        summary = ChatMessage(role=Role.ASSISTANT, text=f"Summary -> users:{users} assistants:{assistants}")
        final_conversation = list(conversation) + [summary]
        await ctx.yield_output(final_conversation)


async def main() -> None:
    # 1) Create a content agent
    chat_client = AzureChatClient(credential=AzureCliCredential())
    content = chat_client.create_agent(
        instructions="Produce a concise paragraph answering the user's request.",
        name="content",
    )

    # 2) Build sequential workflow: content -> summarizer
    summarizer = Summarizer(id="summarizer")
    workflow = SequentialBuilder().participants([content, summarizer]).build()

    # 3) Run and print final conversation
    events = await workflow.run("Explain the benefits of budget eBikes for commuters.")
    outputs = events.get_outputs()

    if outputs:
        print("===== Final Conversation =====")
        messages: list[ChatMessage] | Any = outputs[0]
        for i, msg in enumerate(messages, start=1):
            name = msg.author_name or ("assistant" if msg.role == Role.ASSISTANT else "user")
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")

    """
    Sample Output:

    ------------------------------------------------------------
    01 [user]
    Explain the benefits of budget eBikes for commuters.
    ------------------------------------------------------------
    02 [content]
    Budget eBikes offer commuters an affordable, eco-friendly alternative to cars and public transport.
    Their electric assistance reduces physical strain and allows riders to cover longer distances quickly,
    minimizing travel time and fatigue. Budget models are low-cost to maintain and operate, making them accessible
    for a wider range of people. Additionally, eBikes help reduce traffic congestion and carbon emissions,
    supporting greener urban environments. Overall, budget eBikes provide cost-effective, efficient, and
    sustainable transportation for daily commuting needs.
    ------------------------------------------------------------
    03 [assistant]
    Summary -> users:1 assistants:1
    """


if __name__ == "__main__":
    asyncio.run(main())
