# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunEvent,
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from azure.identity import DefaultAzureCredential

"""
The following sample demonstrates a basic workflow that simulates
a round-robin group chat.
"""


class RoundRobinGroupChatManager(Executor):
    """An executor that manages a round-robin group chat."""

    def __init__(self, members: list[str], max_round: int, id: str | None = None):
        """Initialize the executor with a unique identifier."""
        super().__init__(id)
        self._members = members
        self._max_round = max_round
        self._current_round = 0

    @handler(output_types=[AgentExecutorRequest])
    async def start(self, task: str, ctx: WorkflowContext) -> None:
        """Execute the task by sending messages to the next executor in the round-robin sequence."""
        initial_message = ChatMessage(ChatRole.USER, text=task)

        # Send the initial message to the members
        await asyncio.gather(*[
            ctx.send_message(
                AgentExecutorRequest(messages=[initial_message], should_respond=False),
                target_id=member_id,
            )
            for member_id in self._members
        ])

        # Invoke the first member to start the round-robin chat
        await ctx.send_message(
            AgentExecutorRequest(messages=[], should_respond=True),
            target_id=self._get_next_member(),
        )

    @handler(output_types=[AgentExecutorRequest])
    async def handle_agent_response(self, response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
        """Execute the task by sending messages to the next executor in the round-robin sequence."""
        # Send the response to the other members
        await asyncio.gather(*[
            ctx.send_message(
                AgentExecutorRequest(messages=response.agent_run_response.messages, should_respond=False),
                target_id=member_id,
            )
            for member_id in self._members
            if member_id != response.executor_id
        ])

        # Check for termination condition
        if self._should_terminate():
            await ctx.add_event(WorkflowCompletedEvent(data=response))
            return

        # Request the next member to respond
        selection = self._get_next_member()
        await ctx.send_message(AgentExecutorRequest(messages=[], should_respond=True), target_id=selection)

    def _should_terminate(self) -> bool:
        """Determine if the group chat should terminate based on the current round."""
        return self._current_round >= self._max_round

    def _get_next_member(self) -> str:
        """Get the next member in the round-robin sequence."""
        next_member = self._members[self._current_round % len(self._members)]
        self._current_round += 1

        return next_member


async def main():
    """Main function to run the group chat workflow."""

    # Step 1: Create the executors.
    chat_client = AzureChatClient(ad_credential=DefaultAzureCredential())
    writer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
        ),
        id="writer",
    )
    reviewer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content reviewer. You review the content and provide feedback to the writer."
            ),
        ),
        id="reviewer",
    )

    group_chat_manager = RoundRobinGroupChatManager(
        members=[writer.id, reviewer.id],
        # max_rounds is odd, so that the writer gets the last round
        max_round=5,
        id="group_chat_manager",
    )

    # Step 2: Build the workflow with the defined edges.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(group_chat_manager)
        .add_fan_out_edges(group_chat_manager, [writer, reviewer])
        .add_edge(writer, group_chat_manager)
        .add_edge(reviewer, group_chat_manager)
        .build()
    )

    # Step 3: Run the workflow with an initial message.
    completion_event = None
    async for event in workflow.run_streaming(
        "Create a slogan for a new electric SUV that is affordable and fun to drive."
    ):
        if isinstance(event, AgentRunEvent):
            print(f"{event}")

        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Completion Event: {completion_event}")


if __name__ == "__main__":
    asyncio.run(main())
