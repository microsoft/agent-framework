# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from dataclasses import dataclass

from agent_framework import ChatMessage, ChatResponse, ChatRole
from agent_framework.workflow import (
    AgentRunEvent,
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    output_message_types,
)

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover

"""
The following sample demonstrates a basic workflow that simulates
a round-robin group chat.
"""


@dataclass
class GroupChatMessage:
    """A data class to hold the messages in a group chat."""

    messages: list[ChatMessage]


@dataclass
class AgentSelectionDecision(GroupChatMessage):
    """A data class to hold the decision made by the manager executor."""

    selection: str


@output_message_types(AgentSelectionDecision)
class RoundRobinGroupChatManager(Executor[list[ChatMessage]]):
    """An executor that manages a round-robin group chat."""

    def __init__(self, members: list[str], max_round: int, id: str | None = None):
        """Initialize the executor with a unique identifier."""
        super().__init__(id)
        self._members = members
        self._max_round = max_round
        self._current_round = 0
        self._chat_history: list[ChatMessage] = []

    @override
    async def _execute(self, data: list[ChatMessage], ctx: WorkflowContext) -> None:
        """Execute the task by sending messages to the next executor in the round-robin sequence."""
        self._chat_history.extend(data)

        if self._should_terminate():
            await ctx.add_event(WorkflowCompletedEvent(data=self._chat_history))
            return

        self._current_round += 1
        selection_decision = AgentSelectionDecision(
            messages=self._chat_history,
            selection=self._get_next_member(),
        )
        await ctx.send_message(selection_decision)

    def _should_terminate(self) -> bool:
        """Determine if the group chat should terminate based on the current round."""
        return self._current_round >= self._max_round

    def _get_next_member(self) -> str:
        """Get the next member in the round-robin sequence."""
        return self._members[(self._current_round - 1) % len(self._members)]


@output_message_types(list[ChatMessage])
class FakeAgentExecutor(Executor[AgentSelectionDecision]):
    """An executor that simulates a group chat agent A."""

    @override
    async def _execute(self, data: AgentSelectionDecision, ctx: WorkflowContext) -> None:
        """Simulate a response."""
        response = ChatResponse(
            messages=[
                ChatMessage(
                    ChatRole.ASSISTANT,
                    text=f"{self.id} received request. Current message size: {len(data.messages)}",
                    author_name=f"{self.id}",
                )
            ]
        )

        await ctx.add_event(AgentRunEvent(self.id, data=response))
        await ctx.send_message(response.messages)


async def main():
    """Main function to run the group chat workflow."""
    # Step 1: Create the executors.
    executor_a = FakeAgentExecutor(id="executor_a")
    executor_b = FakeAgentExecutor(id="executor_b")
    executor_c = FakeAgentExecutor(id="executor_c")

    group_chat_manager = RoundRobinGroupChatManager(
        members=[executor_a.id, executor_b.id, executor_c.id],
        max_round=3,
        id="group_chat_manager",
    )
    # The workflow graph:
    #
    # GroupChatManager -> executor_a -> GroupChatManager
    # GroupChatManager -> executor_b -> GroupChatManager
    # GroupChatManager -> executor_c -> GroupChatManager

    # Step 2: Build the workflow with the defined edges.
    # This time we are creating edges and loops with conditions.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(group_chat_manager)
        .add_edge(group_chat_manager, executor_a, condition=lambda x: x.selection == executor_a.id)
        .add_edge(group_chat_manager, executor_b, condition=lambda x: x.selection == executor_b.id)
        .add_edge(group_chat_manager, executor_c, condition=lambda x: x.selection == executor_c.id)
        .add_edge(executor_a, group_chat_manager)
        .add_edge(executor_b, group_chat_manager)
        .add_edge(executor_c, group_chat_manager)
        .build()
    )

    # Step 3: Run the workflow with an initial message.
    completion_event = None
    async for event in workflow.run_stream([ChatMessage(ChatRole.USER, text="Start group chat")]):
        if isinstance(event, AgentRunEvent):
            print(f"{event}")

        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Completion Event: {completion_event}")


if __name__ == "__main__":
    asyncio.run(main())
