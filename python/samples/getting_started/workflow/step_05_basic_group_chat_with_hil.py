# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatMessage, Role
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from azure.identity import AzureCliCredential

"""
The following sample demonstrates a basic workflow that simulates
a round-robin group chat with a Human-in-the-Loop (HIL) executor.
"""


class CriticGroupChatManager(Executor):
    """An executor that manages a round-robin group chat."""

    def __init__(self, members: list[str], id: str | None = None):
        """Initialize the executor with a unique identifier."""
        super().__init__(id)
        self._members = members
        self._current_round = 0
        self._chat_history: list[ChatMessage] = []

    @handler
    async def start(self, task: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Handler that starts the group chat with an initial task."""
        initial_message = ChatMessage(Role.USER, text=task)

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

    @handler
    async def handle_agent_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[RequestInfoMessage | AgentExecutorRequest],
    ) -> None:
        """Handler that processes the response from the agent."""
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

        # Check if we need to request additional information
        if self._should_request_info():
            await ctx.send_message(RequestInfoMessage())
            return

        # Check for termination condition
        if self._should_terminate():
            await ctx.add_event(WorkflowCompletedEvent(data=response))
            return

        # Request the next member to respond
        selection = self._get_next_member()
        await ctx.send_message(AgentExecutorRequest(messages=[], should_respond=True), target_id=selection)

    @handler
    async def handle_request_response(
        self,
        response: RequestResponse[RequestInfoMessage, list[ChatMessage]],
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """Handler that processes the response from the RequestInfoExecutor."""
        messages: list[ChatMessage] = response.data or []

        # Update the chat history with the response
        self._chat_history.extend(messages)

        # Send the response to the other members
        await asyncio.gather(*[
            ctx.send_message(
                AgentExecutorRequest(messages=messages, should_respond=False),
                target_id=member_id,
            )
            for member_id in self._members
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
        return bool(last_message.role == Role.USER and "approve" in last_message.text.lower())

    def _should_request_info(self) -> bool:
        """Determine if the group chat should request HIL based on the last message."""
        if len(self._chat_history) == 0:
            return True

        last_message = self._chat_history[-1]
        return last_message.role == Role.ASSISTANT

    def _get_next_member(self) -> str:
        """Get the next member in the round-robin sequence."""
        next_member = self._members[self._current_round % len(self._members)]
        self._current_round += 1

        return next_member


async def main():
    """Main function to run the group chat workflow."""
    # Step 1: Create the executors.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    chat_client = AzureChatClient(credential=AzureCliCredential())
    writer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content writer. You create new content and edit contents based on the feedback."
            ),
            name="Writer",
            id="Writer",
        ),
    )
    reviewer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an excellent content reviewer. You review the content and provide feedback to the writer. "
                "You do not address user requests. Only provide feedback to the writer."
            ),
            name="Reviewer",
            id="Reviewer",
        ),
    )

    group_chat_manager = CriticGroupChatManager(members=[writer.id, reviewer.id], id="GroupChatManager")

    request_info_executor = RequestInfoExecutor()

    # Step 2: Build the workflow with the defined edges.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(group_chat_manager)
        .add_edge(group_chat_manager, request_info_executor)
        .add_edge(request_info_executor, group_chat_manager)
        .add_fan_out_edges(group_chat_manager, [writer, reviewer])
        .add_edge(writer, group_chat_manager)
        .add_edge(reviewer, group_chat_manager)
        .build()
    )

    # Step 3: Run the workflow with an initial message.
    # Here we are capturing the RequestInfoEvent event and allowing the user to provide input.
    # Once the user provides input, we will provide it back to the workflow to continue the execution.
    completion_event: WorkflowCompletedEvent | None = None
    request_info_event: RequestInfoEvent | None = None
    user_input = ""

    while True:
        # Depending on whether we have a RequestInfoEvent event, we either
        # run the workflow normally or send the message to the HIL executor.
        if not request_info_event:
            response_stream = workflow.run_stream(
                "Create a slogan for a new electric SUV that is affordable and fun to drive."
            )
        else:
            response_stream = workflow.send_responses_streaming({
                request_info_event.request_id: [ChatMessage(Role.USER, text=user_input)]
            })
            request_info_event = None

        async for event in response_stream:
            print(event)

            if isinstance(event, WorkflowCompletedEvent):
                completion_event = event
            elif isinstance(event, RequestInfoEvent):
                request_info_event = event

        # Prompt for user input if we are waiting for human intervention
        if request_info_event:
            user_input = input("Human feedback required. Please provide your input (type 'approve' to end): ")
        elif completion_event:
            break

    print(f"Completion Event: {completion_event}")


if __name__ == "__main__":
    asyncio.run(main())
