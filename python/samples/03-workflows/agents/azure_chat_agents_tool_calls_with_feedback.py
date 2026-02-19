# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from typing import Annotated

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
    tool,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from pydantic import Field
from typing_extensions import Never

"""
Sample: Tool-enabled agents with human feedback

Pipeline layout:
writer_agent (uses Azure OpenAI tools) -> Coordinator -> writer_agent
-> Coordinator -> final_editor_agent -> Coordinator -> output

The writer agent calls tools to gather product facts before drafting copy. A custom executor
packages the draft and emits a request_info event (type='request_info') so a human can comment, then replays the human
guidance back into the conversation before the final editor agent produces the polished output.

Demonstrates:
- Attaching Python function tools to an agent inside a workflow.
- Capturing the writer's output for human review.
- Streaming AgentRunUpdateEvent updates alongside human-in-the-loop pauses.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure OpenAI configured for AzureOpenAIResponsesClient with required environment variables.
- Authentication via azure-identity. Run `az login` before executing.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py and
# samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def fetch_product_brief(
    product_name: Annotated[str, Field(description="Product name to look up.")],
) -> str:
    """Return a marketing brief for a product."""
    briefs = {
        "lumenx desk lamp": (
            "Product: LumenX Desk Lamp\n"
            "- Three-point adjustable arm with 270° rotation.\n"
            "- Custom warm-to-neutral LED spectrum (2700K-4000K).\n"
            "- USB-C charging pad integrated in the base.\n"
            "- Designed for home offices and late-night study sessions."
        )
    }
    return briefs.get(product_name.lower(), f"No stored brief for '{product_name}'.")


@tool(approval_mode="never_require")
def get_brand_voice_profile(
    voice_name: Annotated[str, Field(description="Brand or campaign voice to emulate.")],
) -> str:
    """Return guidance for the requested brand voice."""
    voices = {
        "lumenx launch": (
            "Voice guidelines:\n"
            "- Friendly and modern with concise sentences.\n"
            "- Highlight practical benefits before aesthetics.\n"
            "- End with an invitation to imagine the product in daily use."
        )
    }
    return voices.get(voice_name.lower(), f"No stored voice profile for '{voice_name}'.")


@dataclass
class DraftFeedbackRequest:
    """Payload sent for human review."""

    prompt: str = ""
    draft_text: str = ""
    conversation: list[Message] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class Coordinator(Executor):
    """Bridge between the writer agent, human feedback, and final editor."""

    def __init__(self, id: str, writer_id: str, final_editor_id: str) -> None:
        super().__init__(id)
        self.writer_id = writer_id
        self.final_editor_id = final_editor_id

    @handler
    async def on_writer_response(
        self,
        draft: AgentExecutorResponse,
        ctx: WorkflowContext[Never, AgentResponse],
    ) -> None:
        """Handle responses from the other two agents in the workflow."""
        if draft.executor_id == self.final_editor_id:
            # Final editor response; yield output directly.
            await ctx.yield_output(draft.agent_response)
            return

        # Writer agent response; request human feedback.
        # Preserve the full conversation so the final editor
        # can see tool traces and the initial prompt.
        conversation: list[Message]
        if draft.full_conversation is not None:
            conversation = list(draft.full_conversation)
        else:
            conversation = list(draft.agent_response.messages)
        draft_text = draft.agent_response.text.strip()
        if not draft_text:
            draft_text = "No draft text was produced."

        prompt = (
            "Review the draft from the writer and provide a short directional note "
            "(tone tweaks, must-have detail, target audience, etc.). "
            "Keep it under 30 words."
        )
        await ctx.request_info(
            request_data=DraftFeedbackRequest(prompt=prompt, draft_text=draft_text, conversation=conversation),
            response_type=str,
        )

    @response_handler
    async def on_human_feedback(
        self,
        original_request: DraftFeedbackRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        note = feedback.strip()
        if note.lower() == "approve":
            # Human approved the draft as-is; forward it unchanged.
            await ctx.send_message(
                AgentExecutorRequest(
                    messages=original_request.conversation + [Message("user", text="The draft is approved as-is.")],
                    should_respond=True,
                ),
                target_id=self.final_editor_id,
            )
            return

        # Human provided feedback; prompt the writer to revise.
        conversation: list[Message] = list(original_request.conversation)
        instruction = (
            "A human reviewer shared the following guidance:\n"
            f"{note or 'No specific guidance provided.'}\n\n"
            "Rewrite the draft from the previous assistant message into a polished final version. "
            "Keep the response under 120 words and reflect any requested tone adjustments."
        )
        conversation.append(Message("user", text=instruction))
        await ctx.send_message(
            AgentExecutorRequest(messages=conversation, should_respond=True), target_id=self.writer_id
        )


def create_writer_agent() -> Agent:
    """Creates a writer agent with tools."""
    return AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        # This sample has been tested only on `gpt-5.1` and may not work as intended on other models
        # This sample is known to fail on `gpt-5-mini` reasoning input (GH issue #4059)
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    ).as_agent(
        name="writer_agent",
        instructions=(
            "You are a marketing writer. Call the available tools before drafting copy so you are precise. "
            "Always call both tools once before drafting. Summarize tool outputs as bullet points, then "
            "produce a 3-sentence draft."
        ),
        tools=[fetch_product_brief, get_brand_voice_profile],
        tool_choice="required",
    )


def create_final_editor_agent() -> Agent:
    """Creates a final editor agent."""
    return AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    ).as_agent(
        name="final_editor_agent",
        instructions=(
            "You are an editor who polishes marketing copy after human approval. "
            "Correct any legal or factual issues. Return the final version even if no changes are made. "
        ),
    )


def display_agent_run_update(event: WorkflowEvent, last_executor: str | None) -> None:
    """Display an AgentRunUpdateEvent in a readable format."""
    printed_tool_calls: set[str] = set()
    printed_tool_results: set[str] = set()
    executor_id = event.executor_id
    update = event.data
    # Extract and print any new tool calls or results from the update.
    function_calls = [c for c in update.contents if c.type == "function_call"]  # type: ignore[union-attr]
    function_results = [c for c in update.contents if c.type == "function_result"]  # type: ignore[union-attr]
    if executor_id != last_executor:
        if last_executor is not None:
            print()
        print(f"{executor_id}:", end=" ", flush=True)
        last_executor = executor_id
    # Print any new tool calls before the text update.
    for call in function_calls:
        if call.call_id in printed_tool_calls:
            continue
        printed_tool_calls.add(call.call_id)
        args = call.arguments
        args_preview = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else (args or "").strip()
        print(
            f"\n{executor_id} [tool-call] {call.name}({args_preview})",
            flush=True,
        )
        print(f"{executor_id}:", end=" ", flush=True)
    # Print any new tool results before the text update.
    for result in function_results:
        if result.call_id in printed_tool_results:
            continue
        printed_tool_results.add(result.call_id)
        result_text = result.result
        if not isinstance(result_text, str):
            result_text = json.dumps(result_text, ensure_ascii=False)
        print(
            f"\n{executor_id} [tool-result] {result.call_id}: {result_text}",
            flush=True,
        )
        print(f"{executor_id}:", end=" ", flush=True)
    # Finally, print the text update.
    print(update, end="", flush=True)


async def consume_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, str] | None:
    """Consume a workflow event stream, printing outputs and returning any pending human responses."""
    requests: list[WorkflowEvent] = []
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, DraftFeedbackRequest):
            # Stash the request so we can prompt the human after the stream completes.
            requests.append(event)

    if requests:
        pending_responses: dict[str, str] = {}
        for request in requests:
            print("\n----- Writer draft -----")
            print(request.data.draft_text.strip())
            print("\nProvide guidance for the editor (or 'approve' to accept the draft).")
            answer = input("Human feedback: ").strip()  # noqa: ASYNC250
            if answer.lower() == "exit":
                print("Exiting...")
                exit(0)
            pending_responses[request.request_id] = answer

        return pending_responses

    return None


async def main() -> None:
    """Run the workflow and bridge human feedback between two agents."""

    # Build the workflow.
    writer_agent = AgentExecutor(create_writer_agent())
    final_editor_agent = AgentExecutor(create_final_editor_agent())
    coordinator = Coordinator(
        id="coordinator",
        writer_id="writer_agent",
        final_editor_id="final_editor_agent",
    )

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
    pending_responses = await consume_stream(stream)

    # Run until there are no more requests
    while pending_responses is not None:
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await consume_stream(stream)

    print("Workflow complete.")


if __name__ == "__main__":
    asyncio.run(main())
