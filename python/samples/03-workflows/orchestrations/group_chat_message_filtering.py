# Copyright (c) Microsoft. All rights reserved.

"""Filter participant text before it reaches group-chat history or other participants.

The custom orchestrator validates the sending executor, withholds INTERNAL-only
messages, and redacts example email addresses before delegating to normal group-chat
routing. Filtering caller-facing workflow events would be too late: participants
would already have received the original response.

This is a text-only policy demonstration, not a complete PII detector or a security
boundary for the originating agent. Its local session, tools, model provider, and
telemetry may still contain the original data. User input is broadcast normally;
apply your input policy before starting the workflow. Participant intermediate
outputs are disabled, but executor lifecycle events can still contain raw responses
before this handler runs. Filter or restrict access to those events separately
before exposing workflow results to callers. This policy protects shared history
and broadcasts, not every event returned by workflow.run().

Prerequisites: install agent-framework-foundry and agent-framework-orchestrations,
set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL, and run az login.
"""

import asyncio
import os
import re

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorResponse,
    AgentResponse,
    Message,
    WorkflowContext,
    handler,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import GroupChatBuilder, GroupChatOrchestrator, GroupChatState
from agent_framework_orchestrations._base_group_chat_orchestrator import (
    GroupChatResponseMessage,
    GroupChatWorkflowContextOutT,
    ParticipantRegistry,
)
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


class FilteringGroupChatOrchestrator(GroupChatOrchestrator):
    """Intercept responses at the shared-history and broadcast boundary."""

    @handler
    async def handle_participant_response(
        self,
        response: AgentExecutorResponse | GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatWorkflowContextOutT, list[Message]],
    ) -> None:
        # Use workflow routing identity, not an author name supplied in model output.
        if len(ctx.source_executor_ids) != 1 or ctx.source_executor_ids[0] not in {"Researcher", "Writer"}:
            raise ValueError("Participant is not allowed to publish to this group chat.")

        sender = ctx.source_executor_ids[0]
        messages = self._process_participant_response(response)
        filtered: list[str] = []
        for message in messages:
            if message.text.lstrip().startswith("INTERNAL:"):
                filtered.append("[Internal message withheld]")
            else:
                filtered.append(re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", message.text))

        shared_text = "\n".join(filtered)
        print(f"{sender} (filtered): {shared_text}")
        # Create a new text envelope. Do not mutate the originating agent's response.
        # The base handler now appends and broadcasts only this filtered version.
        await super().handle_participant_response(
            GroupChatResponseMessage(Message(role="assistant", contents=[shared_text], author_name=sender)),
            ctx,
        )


def select_speaker(state: GroupChatState) -> str:
    """Give the researcher one turn, followed by the writer."""
    return "Researcher" if state.current_round == 0 else "Writer"


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )
    researcher = AgentExecutor(
        Agent(
            client=client,
            name="Researcher",
            instructions="Use this fictional support note: order 42 was delayed. Contact alex@example.com.",
        ),
        id="Researcher",
    )
    writer = AgentExecutor(
        Agent(
            client=client,
            name="Writer",
            instructions=(
                "Summarize the researcher's note. Preserve redaction placeholders; do not invent contact details."
            ),
        ),
        id="Writer",
    )
    participants = [researcher, writer]
    orchestrator = FilteringGroupChatOrchestrator(
        id="filtered_group_chat",
        participant_registry=ParticipantRegistry(participants),
        selection_func=select_speaker,
        max_rounds=2,
    )
    workflow = GroupChatBuilder(participants=participants, orchestrator=orchestrator).build()
    # Print only the orchestrator's completion. The result's executor lifecycle
    # events can still contain raw responses, even without participant outputs.
    result = await workflow.run("Prepare a brief summary of the fictional support case.")
    for response in result.get_outputs():
        if isinstance(response, AgentResponse):
            print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
