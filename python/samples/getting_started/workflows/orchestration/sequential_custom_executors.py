# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import (
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    Role,
    SequentialBuilder,
    WorkflowContext,
    handler,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Sequential workflow mixing agents and a custom summarizer executor

This demonstrates how SequentialBuilder chains participants with a shared
conversation context (list[ChatMessage]). An agent produces content; a custom
executor appends a compact summary to the conversation. The workflow completes
after all participants have executed in sequence, and the final output contains
the complete conversation.

Custom executor contract:
- Provide at least one @handler accepting AgentExecutorResponse and a WorkflowContext[list[ChatMessage]]
- Emit the updated conversation via ctx.send_message([...])

Prerequisites:
- Azure OpenAI access configured for AzureOpenAIChatClient (use az login + env vars)
"""


class Summarizer(Executor):
    """Simple summarizer: consumes full conversation and appends an assistant summary."""

    @handler
    async def summarize(self, agent_response: AgentExecutorResponse, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        """Append a summary message to a copy of the full conversation.

        Note: A custom executor must be able to handle the message type from the prior participant, and produce
        the message type expected by the next participant. In this case, the prior participant is an agent thus
        the input is AgentExecutorResponse (an agent will be wrapped in an AgentExecutor, which produces
        `AgentExecutorResponse`). If the next participant is also an agent or this is the final participant,
        the output must be `list[ChatMessage]`.
        """
        if not agent_response.full_conversation:
            await ctx.send_message([ChatMessage(role=Role.ASSISTANT, text="No conversation to summarize.")])
            return

        users = sum(1 for m in agent_response.full_conversation if m.role == Role.USER)
        assistants = sum(1 for m in agent_response.full_conversation if m.role == Role.ASSISTANT)
        summary = ChatMessage(role=Role.ASSISTANT, text=f"Summary -> users:{users} assistants:{assistants}")
        final_conversation = list(agent_response.full_conversation) + [summary]
        await ctx.send_message(final_conversation)


async def main() -> None:
    # 1) Create a content agent
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    content = chat_client.as_agent(
        instructions="Produce a concise paragraph answering the user's request.",
        name="content",
    )

    # 2) Build sequential workflow: content -> summarizer
    summarizer = Summarizer(id="summarizer")
    workflow = SequentialBuilder().participants([content, summarizer]).build()

    # 3) Run workflow and extract final conversation
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
