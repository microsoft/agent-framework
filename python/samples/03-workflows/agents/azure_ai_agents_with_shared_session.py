# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    InMemoryHistoryProvider,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    executor,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Agents with a shared thread in a workflow

A Writer agent generates content, then a Reviewer agent critiques it, sharing a common message thread.

Purpose:
Show how to use a shared thread between multiple agents in a workflow.
By default, agents have individual threads, but sharing a thread allows them to share all messages.

Notes:
- Not all agents can share threads; usually only the same type of agents can share threads.

Demonstrate:
- Creating multiple agents with AzureOpenAIResponsesClient.
- Setting up a shared thread between agents.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- AZURE_AI_MODEL_DEPLOYMENT_NAME must be set to your Azure OpenAI model deployment name.
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
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    # set the same context provider (same default source_id) for both agents to share the thread
    writer = client.as_agent(
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        name="writer",
        context_providers=[InMemoryHistoryProvider()],
    )

    reviewer = client.as_agent(
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
        context_providers=[InMemoryHistoryProvider()],
    )

    # Create the shared session
    shared_session = writer.create_session()
    writer_executor = AgentExecutor(writer, session=shared_session)
    reviewer_executor = AgentExecutor(reviewer, session=shared_session)

    workflow = (
        WorkflowBuilder(start_executor=writer_executor)
        .add_chain([writer_executor, intercept_agent_response, reviewer_executor])
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

    # The shared session now contains the conversation between the writer and reviewer. Print it out.
    print("=== Shared Session Conversation ===")
    memory_state = shared_session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
    for message in memory_state.get("messages", []):
        print(f"{message.author_name or message.role}: {message.text}")


if __name__ == "__main__":
    asyncio.run(main())
