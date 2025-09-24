# Copyright (c) Microsoft. All rights reserved.

import asyncio

from typing_extensions import Never

from agent_framework import (
    ChatAgent,
    ChatMessage,
    Executor,
    ExecutorFailedEvent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowFailedEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework._workflow._events import WorkflowOutputEvent
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Step 3: Agents in a workflow with streaming

A Writer agent generates content,
then passes the conversation to a Reviewer agent that finalizes the result.
The workflow is invoked with run_stream so you can observe events as they occur.

Purpose:
Show how to wrap chat agents created by AzureChatClient inside workflow executors, wire them with WorkflowBuilder,
and consume streaming events from the workflow. Demonstrate the @handler pattern with typed inputs and typed
WorkflowContext[T_Out, T_W_Out] outputs. Agents automatically yield outputs when they complete.
The streaming loop also surfaces WorkflowEvent.origin so you can distinguish runner-generated lifecycle events
from executor-generated data-plane events.

Prerequisites:
- Azure OpenAI configured for AzureChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
"""


class Writer(Executor):
    """Custom executor that owns a domain specific agent for content generation.

    This class demonstrates:
    - Attaching a ChatAgent to an Executor so it participates as a node in a workflow.
    - Using a @handler method to accept a typed input and forward a typed output via ctx.send_message.
    """

    agent: ChatAgent

    def __init__(self, chat_client: AzureChatClient, id: str = "writer"):
        # Create a domain specific agent using your configured AzureChatClient.
        agent = chat_client.create_agent(
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
        )
        # Associate this agent with the executor node. The base Executor stores it on self.agent.
        super().__init__(agent=agent, id=id)

    @handler
    async def handle(self, message: ChatMessage, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        """Generate content and forward the updated conversation.

        Contract for this handler:
        - message is the inbound user ChatMessage.
        - ctx is a WorkflowContext that expects a list[ChatMessage] to be sent downstream.

        Pattern shown here:
        1) Seed the conversation with the inbound message.
        2) Run the attached agent to produce assistant messages.
        3) Forward the cumulative messages to the next executor with ctx.send_message.
        """
        # Start the conversation with the incoming user message.
        messages: list[ChatMessage] = [message]
        # Run the agent and extend the conversation with the agent's messages.
        response = await self.agent.run(messages)
        messages.extend(response.messages)
        # Forward the accumulated messages to the next executor in the workflow.
        await ctx.send_message(messages)


class Reviewer(Executor):
    """Custom executor that owns a review agent and completes the workflow."""

    agent: ChatAgent

    def __init__(self, chat_client: AzureChatClient, id: str = "reviewer"):
        # Create a domain specific agent that evaluates and refines content.
        agent = chat_client.create_agent(
            instructions=(
                "You are an excellent content reviewer. You review the content and provide feedback to the writer."
            ),
        )
        super().__init__(agent=agent, id=id)

    @handler
    async def handle(self, messages: list[ChatMessage], ctx: WorkflowContext[Never, str]) -> None:
        """Review the full conversation transcript and yield the final output.

        This node consumes all messages so far. It uses its agent to produce the final text,
        then yields the output. The workflow completes when it becomes idle.
        """
        response = await self.agent.run(messages)
        await ctx.yield_output(response.text)


async def main():
    """Build the two node workflow and run it with streaming to observe events."""
    # Create the Azure chat client. AzureCliCredential uses your current az login.
    chat_client = AzureChatClient(credential=AzureCliCredential())
    # Instantiate the two agent backed executors.
    writer = Writer(chat_client)
    reviewer = Reviewer(chat_client)

    # Build the workflow using the fluent builder.
    # Set the start node and connect an edge from writer to reviewer.
    workflow = WorkflowBuilder().set_start_executor(writer).add_edge(writer, reviewer).build()

    # Run the workflow with the user's initial message and stream events as they occur.
    # This surfaces executor events, workflow outputs, run-state changes, and errors.
    async for event in workflow.run_stream(
        ChatMessage(role="user", text="Create a slogan for a new electric SUV that is affordable and fun to drive.")
    ):
        if isinstance(event, WorkflowStatusEvent):
            prefix = f"State ({event.origin.value}): "
            if event.state == WorkflowRunState.IN_PROGRESS:
                print(prefix + "IN_PROGRESS")
            elif event.state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS:
                print(prefix + "IN_PROGRESS_PENDING_REQUESTS (requests in flight)")
            elif event.state == WorkflowRunState.IDLE:
                print(prefix + "IDLE (no active work)")
            elif event.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
                print(prefix + "IDLE_WITH_PENDING_REQUESTS (prompt user or UI now)")
            else:
                print(prefix + str(event.state))
        elif isinstance(event, WorkflowOutputEvent):
            print(f"Workflow output ({event.origin.value}): {event.data}")
        elif isinstance(event, ExecutorFailedEvent):
            print(
                f"Executor failed ({event.origin.value}): "
                f"{event.executor_id} {event.details.error_type}: {event.details.message}"
            )
        elif isinstance(event, WorkflowFailedEvent):
            details = event.details
            print(f"Workflow failed ({event.origin.value}): {details.error_type}: {details.message}")
        else:
            print(f"{event.__class__.__name__} ({event.origin.value}): {event}")

    """
    Sample Output:

    State (RUNNER): IN_PROGRESS
    ExecutorInvokeEvent (RUNNER): ExecutorInvokeEvent(executor_id=writer)
    ExecutorCompletedEvent (RUNNER): ExecutorCompletedEvent(executor_id=writer)
    ExecutorInvokeEvent (RUNNER): ExecutorInvokeEvent(executor_id=reviewer)
    Workflow output (EXECUTOR): Drive the Future. Affordable Adventure, Electrified.
    ExecutorCompletedEvent (RUNNER): ExecutorCompletedEvent(executor_id=reviewer)
    State (RUNNER): IDLE
    """


if __name__ == "__main__":
    asyncio.run(main())
