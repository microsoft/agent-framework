# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import (
    Agent,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
    WorkflowContext,
    handler,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from typing_extensions import Never

# Load environment variables from .env file
load_dotenv()

"""
Sample: Sequential workflow mixing agents and a custom summarizer executor

This demonstrates how SequentialBuilder chains participants with a shared
conversation context (list[Message]). An agent produces content; a custom
executor synthesizes a compact summary and yields it as the workflow's terminal
output.

Custom executor contract:
- Intermediate custom executors: handle the message type from the prior participant
  and forward `list[Message]` via `ctx.send_message(...)` for the next participant.
- Terminator custom executors: handle the message type from the prior participant and
  yield the workflow's final answer as an `AgentResponse` via `ctx.yield_output(...)`.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL must be set to your Azure OpenAI model deployment name.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""


class Summarizer(Executor):
    """Terminator custom executor: synthesizes a one-line summary as the workflow's final answer."""

    @handler
    async def summarize(
        self,
        agent_response: AgentExecutorResponse,
        ctx: WorkflowContext[Never, AgentResponse],
    ) -> None:
        """Yield a terminal AgentResponse containing the summary.

        The prior participant is an agent, which is wrapped in an `AgentExecutor` that
        produces `AgentExecutorResponse`. As the last participant in the sequential workflow,
        this executor calls `ctx.yield_output(AgentResponse(...))` so its output becomes the
        workflow's terminal output (rather than being forwarded to a downstream participant).
        """
        if not agent_response.full_conversation:
            await ctx.yield_output(AgentResponse(messages=[Message("assistant", ["No conversation to summarize."])]))
            return

        users = sum(1 for m in agent_response.full_conversation if m.role == "user")
        assistants = sum(1 for m in agent_response.full_conversation if m.role == "assistant")
        summary = Message("assistant", [f"Summary -> users:{users} assistants:{assistants}"])
        await ctx.yield_output(AgentResponse(messages=[summary]))


async def main() -> None:
    # 1) Create a content agent
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )
    content = Agent(
        client=client,
        instructions="Produce a concise paragraph answering the user's request.",
        name="content",
    )

    # 2) Build sequential workflow: content -> summarizer
    summarizer = Summarizer(id="summarizer")
    workflow = SequentialBuilder(participants=[content, summarizer]).build()

    # 3) Run workflow and extract the final summary
    events = await workflow.run("Explain the benefits of budget eBikes for commuters.")
    outputs = events.get_outputs()

    if outputs:
        print("===== Final Summary =====")
        final: AgentResponse = outputs[0]
        for msg in final.messages:
            print(msg.text)

    """
    Sample Output:

    ===== Final Summary =====
    Summary -> users:1 assistants:1
    """


if __name__ == "__main__":
    asyncio.run(main())
