# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from dataclasses import dataclass

from agent_framework import ChatClientAgent, ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    HumanInTheLoopEvent,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    message_handler,
)

if sys.version_info >= (3, 12):
    pass  # pragma: no cover
else:
    pass  # pragma: no cover

"""
The following sample demonstrates a basic workflow that simulates
a round-robin group chat with a Human-in-the-Loop (HIL) executor.
"""


@dataclass
class GroupChatMessage:
    """A data class to hold the messages in a group chat."""

    messages: list[ChatMessage]


@dataclass
class AgentSelectionDecision(GroupChatMessage):
    """A data class to hold the decision made by the Human-in-the-Loop executor."""

    selection: str


class CriticGroupChatManagerWithHIL(Executor):
    """An executor that manages a round-robin group chat."""

    def __init__(self, members: list[str], id: str | None = None):
        """Initialize the executor with a unique identifier."""
        super().__init__(id)
        self._members = members
        self._current_round = 0
        self._chat_history: list[ChatMessage] = []

    @message_handler(output_types=[AgentExecutorRequest])
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

        # Update the cache with the initial message
        self._chat_history.append(initial_message)

    @message_handler(output_types=[AgentExecutorRequest])
    async def handle_agent_response(self, response: AgentExecutorResponse, ctx: WorkflowContext) -> None:
        """Execute the task by sending messages to the next executor in the round-robin sequence."""
        # Update the chat history with the response
        self._chat_history.extend(response.agent_run_response.messages)

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
        """Determine if the group chat should terminate based on the last message."""
        if len(self._chat_history) == 0:
            return False

        last_message = self._chat_history[-1]
        return bool(last_message.role == ChatRole.USER and "approve" in last_message.text.lower())

    def _should_request_hil(self) -> bool:
        """Determine if the group chat should request HIL based on the last message."""
        if len(self._chat_history) == 0:
            return True

        last_message = self._chat_history[-1]
        return last_message.role == ChatRole.ASSISTANT

    def _get_next_member(self) -> str:
        """Get the next member in the round-robin sequence."""
        return self._members[(self._current_round - 1) % len(self._members)]


async def main():
    """Main function to run the group chat workflow."""
    # Step 1: Create the executors.
    chat_client = AzureChatClient()
    writer = AgentExecutor(
        ChatClientAgent(
            chat_client,
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
        ),
        id="writer",
    )
    reviewer = AgentExecutor(
        ChatClientAgent(
            chat_client,
            instructions=(
                "You are an excellent content reviewer. You review the content and provide feedback to the writer."
            ),
        ),
        id="reviewer",
    )

    group_chat_manager = CriticGroupChatManagerWithHIL(
        members=[writer.id, reviewer.id],
        id="group_chat_manager",
    )

    # Step 2: Build the workflow with the defined edges.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(group_chat_manager)
        .add_edge(group_chat_manager, hil_executor)
        .add_edge(hil_executor, group_chat_manager)
        .add_edge(group_chat_manager, executor_a, condition=lambda x: x.selection == executor_a.id)
        .add_edge(group_chat_manager, executor_b, condition=lambda x: x.selection == executor_b.id)
        .add_edge(group_chat_manager, executor_c, condition=lambda x: x.selection == executor_c.id)
        .add_edge(executor_a, group_chat_manager)
        .add_edge(executor_b, group_chat_manager)
        .add_edge(executor_c, group_chat_manager)
        .build()
    )

    # Step 3: Run the workflow with an initial message.
    # Here we are capturing the human-in-the-loop event and allowing the user to provide input.
    # Once the user provides input, we will provide it back to the workflow to continue the execution.
    completion_event: WorkflowCompletedEvent | None = None
    human_in_the_loop_event: HumanInTheLoopEvent | None = None
    user_input = "Start group chat"

    while True:
        # Depending on whether we have a human-in-the-loop event, we either
        # run the workflow normally or send the message to the HIL executor.
        if not human_in_the_loop_event:
            response = workflow.run_stream([ChatMessage(ChatRole.USER, text=user_input)])
        else:
            response = workflow.run_stream(
                [ChatMessage(ChatRole.USER, text=user_input)],
                executor=human_in_the_loop_event.executor_id,
            )
            human_in_the_loop_event = None

        async for event in response:
            print(f"{event}")

            if isinstance(event, WorkflowCompletedEvent):
                completion_event = event
            elif isinstance(event, HumanInTheLoopEvent):
                human_in_the_loop_event = event

        # Prompt for user input if we are waiting for human intervention
        if human_in_the_loop_event:
            user_input = input("Human intervention required. Type 'stop' to end the loop or any message to continue: ")
        elif completion_event:
            break

    print(f"Completion Event: {completion_event}")


if __name__ == "__main__":
    asyncio.run(main())
