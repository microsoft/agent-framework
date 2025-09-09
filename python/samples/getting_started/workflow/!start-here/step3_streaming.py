# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, ChatMessage
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import Executor, WorkflowBuilder, WorkflowCompletedEvent, WorkflowContext, handler
from azure.identity import AzureCliCredential

"""
Step 3: Agents in a workflow with streaming

A Writer agent generates content,
then passes the conversation to a Reviewer agent that finalizes the result.
The workflow is invoked with run_stream so you can observe events as they occur.

Purpose:
Show how to wrap chat agents created by AzureChatClient inside workflow executors, wire them with WorkflowBuilder,
and consume streaming events from the workflow. Demonstrate the @handler pattern with typed inputs and typed
WorkflowContext[T] outputs, and finish by emitting a WorkflowCompletedEvent from the terminal node while printing
intermediate events for observability.

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
    async def handle(self, messages: list[ChatMessage], ctx: WorkflowContext[str]) -> None:
        """Review the full conversation transcript and complete with a final string.

        This node consumes all messages so far. It uses its agent to produce the final text,
        then signals completion by adding a WorkflowCompletedEvent to the event stream.
        """
        response = await self.agent.run(messages)
        await ctx.add_event(WorkflowCompletedEvent(response.text))


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
    # Events include executor invoke and completion, as well as the terminal WorkflowCompletedEvent.
    async for event in workflow.run_stream(
        ChatMessage(role="user", text="Create a slogan for a new electric SUV that is affordable and fun to drive.")
    ):
        print(event)

    """
    Sample Output:

    ExecutorInvokeEvent(executor_id=writer)
    ExecutorCompletedEvent(executor_id=writer)
    ExecutorInvokeEvent(executor_id=reviewer)
    WorkflowCompletedEvent(data=Drive the Future. Affordable Adventure, Electrified.)
    ExecutorCompletedEvent(executor_id=reviewer)
    """


if __name__ == "__main__":
    asyncio.run(main())
