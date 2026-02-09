# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from dataclasses import dataclass, field

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    ChatMessage,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from typing_extensions import Never

"""
Sample: AzureOpenAI Chat Agents in workflow with human feedback

Pipeline layout:
writer_agent -> Coordinator -> writer_agent -> Coordinator -> final_editor_agent -> Coordinator -> output

The writer agent drafts marketing copy. A custom executor emits a request_info event (type='request_info') so a
human can comment, then relays the human guidance back into the conversation before the final editor agent
produces the polished output.

Demonstrates:
- Capturing agent responses in a custom executor.
- Emitting request_info events (type='request_info') to request human input.
- Handling human feedback and routing it to the appropriate agents.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Run `az login` before executing.
"""


@dataclass
class DraftFeedbackRequest:
    """Payload sent for human review."""

    prompt: str = ""
    conversation: list[ChatMessage] = field(default_factory=lambda: [])


class Coordinator(Executor):
    """Bridge between the writer agent, human feedback, and final editor."""

    def __init__(self, id: str, writer_name: str, final_editor_name: str) -> None:
        super().__init__(id)
        self.writer_name = writer_name
        self.final_editor_name = final_editor_name

    @handler
    async def on_writer_response(
        self,
        draft: AgentExecutorResponse,
        ctx: WorkflowContext[Never, AgentResponse],
    ) -> None:
        """Handle responses from the writer and final editor agents."""
        if draft.executor_id == self.final_editor_name:
            # No further processing is needed when the final editor has responded.
            return

        # Writer agent response; request human feedback.
        # Preserve the full conversation so that the final editor has context.
        conversation: list[ChatMessage]
        if draft.full_conversation is not None:
            conversation = list(draft.full_conversation)
        else:
            conversation = list(draft.agent_response.messages)

        prompt = (
            "Review the draft from the writer and provide a short directional note "
            "(tone tweaks, must-have detail, target audience, etc.). "
            "Keep it under 30 words."
        )
        await ctx.request_info(
            request_data=DraftFeedbackRequest(prompt=prompt, conversation=conversation),
            response_type=str,
        )

    @response_handler
    async def on_human_feedback(
        self,
        original_request: DraftFeedbackRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """Process human feedback and forward to the appropriate agent."""
        note = feedback.strip()
        if note.lower() == "approve":
            # Human approved the draft as-is; forward it unchanged.
            await ctx.send_message(
                AgentExecutorRequest(
                    messages=original_request.conversation + [ChatMessage("user", text="The draft is approved as-is.")],
                    should_respond=True,
                ),
                target_id=self.final_editor_name,
            )
            return

        # Human provided feedback; prompt the writer to revise.
        conversation: list[ChatMessage] = list(original_request.conversation)
        instruction = (
            "A human reviewer shared the following guidance:\n"
            f"{note or 'No specific guidance provided.'}\n\n"
            "Rewrite the draft from the previous assistant message into a polished final version. "
            "Keep the response under 120 words and reflect any requested tone adjustments."
        )
        conversation.append(ChatMessage("user", text=instruction))
        await ctx.send_message(
            AgentExecutorRequest(messages=conversation, should_respond=True), target_id=self.writer_name
        )


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, str] | None:
    """Process events from the workflow stream to capture human feedback requests."""
    # Track the last author to format streaming output.
    last_author: str | None = None

    requests: list[tuple[str, DraftFeedbackRequest]] = []
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, DraftFeedbackRequest):
            requests.append((event.request_id, event.data))
        elif event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            # This workflow should only produce AgentResponseUpdate as outputs.
            # Streaming updates from an agent will be consecutive, because no two agents run simultaneously
            # in this workflow. So we can use last_author to format output nicely.
            update = event.data
            author = update.author_name
            if author != last_author:
                if last_author is not None:
                    print()  # Newline between different authors
                print(f"{author}: {update.text}", end="", flush=True)
                last_author = author
            else:
                print(update.text, end="", flush=True)

    # Handle any pending human feedback requests.
    if requests:
        responses: dict[str, str] = {}
        for request_id, _ in requests:
            print("\nProvide guidance for the editor (or 'approve' to accept the draft).")
            answer = input("Human feedback: ").strip()  # noqa: ASYNC250
            if answer.lower() == "exit":
                print("Exiting...")
                return None
            responses[request_id] = answer
        return responses
    return None


async def main() -> None:
    """Run the workflow and bridge human feedback between two agents."""
    # Create the agents
    writer_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="writer_agent",
        instructions=("You are a marketing writer."),
        tool_choice="required",
    )

    final_editor_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="final_editor_agent",
        instructions=(
            "You are an editor who polishes marketing copy after human approval. "
            "Correct any legal or factual issues. Return the final version even if no changes are made. "
        ),
    )

    # Create the executor
    coordinator = Coordinator(
        id="coordinator",
        writer_name=writer_agent.name,  # type: ignore
        final_editor_name=final_editor_agent.name,  # type: ignore
    )

    # Build the workflow.
    workflow = (
        WorkflowBuilder(start_executor=writer_agent)
        .add_edge(writer_agent, coordinator)
        .add_edge(coordinator, writer_agent)
        .add_edge(final_editor_agent, coordinator)
        .add_edge(coordinator, final_editor_agent)
        .build()
    )

    print(
        "Interactive mode. When prompted, provide a short feedback note for the editor.",
        flush=True,
    )

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run.
    stream = workflow.run(
        "Create a short launch blurb for the LumenX desk lamp. Emphasize adjustability and warm lighting.",
        stream=True,
    )

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)

    print("\nWorkflow complete.")


if __name__ == "__main__":
    asyncio.run(main())
