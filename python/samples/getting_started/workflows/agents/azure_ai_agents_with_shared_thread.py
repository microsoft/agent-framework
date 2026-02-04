# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessageStore,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    executor,
)
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Sample: Agents with a shared thread in a workflow

A Writer agent generates content, then a Reviewer agent critiques it, sharing a common message thread.

Purpose:
Show how to use a shared thread between multiple agents in a workflow.
By default, agents have individual threads, but sharing a thread allows them to share all messages.

Notes:
- Not all agents can share threads; usually only the same type of agents can share threads.

Demonstrate:
- Creating multiple agents with Azure AI Agent Service (V2 API).
- Setting up a shared thread between agents.

Prerequisites:
- Azure AI Agent Service configured, along with the required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with agents, workflows, and executors in the agent framework.
"""


@executor(id="intercept_agent_response")
async def intercept_agent_response(
    agent_response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
) -> None:
    """This executor intercepts the agent response and sends a request without messages.

    This essentially prevents duplication of messages in the shared thread. Without this
    executor, the response will be added to the thread as input of the next agent call.
    """
    await ctx.send_message(AgentExecutorRequest(messages=[]))


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        writer = await provider.create_agent(
            instructions=(
                "You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."
            ),
            name="writer",
        )

        reviewer = await provider.create_agent(
            instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
            name="reviewer",
        )

        shared_thread = writer.get_new_thread()
        # Set the message store to store messages in memory.
        shared_thread.message_store = ChatMessageStore()

        workflow = (
            WorkflowBuilder()
            .register_agent(factory_func=lambda: writer, name="writer", agent_thread=shared_thread)
            .register_agent(factory_func=lambda: reviewer, name="reviewer", agent_thread=shared_thread)
            .register_executor(
                factory_func=lambda: intercept_agent_response,
                name="intercept_agent_response",
            )
            .add_chain(["writer", "intercept_agent_response", "reviewer"])
            .set_start_executor("writer")
            .build()
        )

        result = await workflow.run(
            "Write a tagline for a budget-friendly eBike.",
            # Keyword arguments will be passed to each agent call.
            # Setting store=False to avoid storing messages in the service for this example.
            options={"store": False},
        )
        # The final state should be IDLE since the workflow no longer has messages to
        # process after the reviewer agent responds.
        assert result.get_final_state() == WorkflowRunState.IDLE

        # The shared thread now contains the conversation between the writer and reviewer. Print it out.
        print("=== Shared Thread Conversation ===")
        for message in shared_thread.message_store.messages:
            print(f"{message.author_name or message.role}: {message.text}")


if __name__ == "__main__":
    asyncio.run(main())
