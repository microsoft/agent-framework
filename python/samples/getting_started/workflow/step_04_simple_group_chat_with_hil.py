# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from dataclasses import dataclass

from agent_framework import ChatMessage, ChatResponse, ChatRole
from agent_framework.workflow import (
    AgentRunEvent,
    Executor,
    ExecutorContext,
    HumanInTheLoopEvent,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    output_message_types,
)

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


@dataclass
class GroupChatMessage:
    """A data class to hold the messages in a group chat."""

    messages: list[ChatMessage]


@dataclass
class AgentSelectionDecision(GroupChatMessage):
    """A data class to hold the decision made by the Human-in-the-Loop executor."""

    selection: str


@output_message_types(AgentSelectionDecision, list[ChatMessage])
class CriticGroupChatManagerWithHIL(Executor[list[ChatMessage]]):
    """An executor that manages a round-robin group chat."""

    def __init__(self, members: list[str], id: str | None = None):
        """Initialize the executor with a unique identifier."""
        super().__init__(id)
        self._members = members
        self._current_round = 0
        self._chat_history: list[ChatMessage] = []

    @override
    async def _execute(
        self,
        data: list[ChatMessage],
        ctx: ExecutorContext,
    ) -> AgentSelectionDecision | list[ChatMessage] | None:
        """Execute the task by sending messages to the next executor in the round-robin sequence."""
        self._chat_history.extend(data)

        if self._should_terminate():
            await ctx.add_event(WorkflowCompletedEvent(data=self._chat_history))
            return None

        if self._should_request_hil():
            # Request human intervention if the last message was from the assistant
            await ctx.send_message(self._chat_history)
            return self._chat_history

        self._current_round += 1
        selection_decision = AgentSelectionDecision(
            messages=self._chat_history,
            selection=self._get_next_member(),
        )
        await ctx.send_message(selection_decision)

        return selection_decision

    def _should_terminate(self) -> bool:
        """Determine if the group chat should terminate based on the last message."""
        if len(self._chat_history) == 0:
            return False

        last_message = self._chat_history[-1]
        return bool(last_message.role == ChatRole.USER and "stop" in last_message.text.lower())

    def _should_request_hil(self) -> bool:
        """Determine if the group chat should request HIL based on the last message."""
        if len(self._chat_history) == 0:
            return True

        last_message = self._chat_history[-1]
        return last_message.role == ChatRole.ASSISTANT

    def _get_next_member(self) -> str:
        """Get the next member in the round-robin sequence."""
        return self._members[(self._current_round - 1) % len(self._members)]


@output_message_types(list[ChatMessage])
class HumanInTheLoopExecutor(Executor[list[ChatMessage]]):
    """An executor that simulates a human-in-the-loop decision-making process."""

    def __init__(self, id: str | None = None):
        """Initialize the executor with a unique identifier."""
        super().__init__(id)

        self._is_waiting_for_human_input = False

    @override
    async def _execute(self, data: list[ChatMessage], ctx: ExecutorContext) -> list[ChatMessage] | None:
        """Simulate a human-in-the-loop response."""
        if not self._is_waiting_for_human_input:
            # If it's not waiting but received a message, it means it should prompt for human input.
            self._is_waiting_for_human_input = True
            await ctx.add_event(HumanInTheLoopEvent(executor_id=self.id))
            return None

        self._is_waiting_for_human_input = False
        # If it is waiting, it means the human has provided input. It should return the messages.
        await ctx.send_message(data)
        return data


@output_message_types(list[ChatMessage])
class FakeAgentExecutor(Executor[AgentSelectionDecision]):
    """An executor that simulates a group chat agent A."""

    @override
    async def _execute(self, data: AgentSelectionDecision, ctx: ExecutorContext) -> None:
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
    executor_a = FakeAgentExecutor(id="executor_a")
    executor_b = FakeAgentExecutor(id="executor_b")
    executor_c = FakeAgentExecutor(id="executor_c")

    hil_executor = HumanInTheLoopExecutor(id="hil_executor")

    group_chat_manager = CriticGroupChatManagerWithHIL(
        members=[executor_a.id, executor_b.id, executor_c.id],
        id="group_chat_manager",
    )
    # The workflow graph:
    #
    # CriticGroupChatManagerWithHIL -> executor_a <-> CriticGroupChatManagerWithHIL <-> HumanInTheLoopExecutor
    # CriticGroupChatManagerWithHIL -> executor_b <-> CriticGroupChatManagerWithHIL <-> HumanInTheLoopExecutor
    # CriticGroupChatManagerWithHIL -> executor_c <-> CriticGroupChatManagerWithHIL <-> HumanInTheLoopExecutor

    workflow = (
        WorkflowBuilder()
        .set_start_executor(group_chat_manager)
        .add_loop(group_chat_manager, hil_executor)
        .add_loop(group_chat_manager, executor_a, condition=lambda x: x.selection == executor_a.id)
        .add_loop(group_chat_manager, executor_b, condition=lambda x: x.selection == executor_b.id)
        .add_loop(group_chat_manager, executor_c, condition=lambda x: x.selection == executor_c.id)
        .build()
    )

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
