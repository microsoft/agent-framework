# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from dataclasses import dataclass, field
from typing import Annotated

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    RequestInfoEvent,
    Role,
    ToolMode,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
    response_handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field
from typing_extensions import Never

"""
Sample: Tool-enabled agents with human feedback

Pipeline layout:
writer_agent (uses Azure OpenAI tools) -> Coordinator -> writer_agent
-> Coordinator -> final_editor_agent -> Coordinator -> output

The writer agent calls tools to gather product facts before drafting copy. A custom executor
packages the draft and emits a RequestInfoEvent so a human can comment, then replays the human
guidance back into the conversation before the final editor agent produces the polished output.

Demonstrates:
- Attaching Python function tools to an agent inside a workflow.
- Capturing the writer's output for human review.
- Streaming AgentRunUpdateEvent updates alongside human-in-the-loop pauses.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Run `az login` before executing.
"""


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
    conversation: list[ChatMessage] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


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
        ctx: WorkflowContext[Never, AgentRunResponse],
    ) -> None:
        """Handle responses from the other two agents in the workflow."""
        if draft.executor_id == self.final_editor_id:
            # Final editor response; yield output directly.
            await ctx.yield_output(draft.agent_run_response)
            return

        # Writer agent response; request human feedback.
        # Preserve the full conversation so the final editor
        # can see tool traces and the initial prompt.
        conversation: list[ChatMessage]
        if draft.full_conversation is not None:
            conversation = list(draft.full_conversation)
        else:
            conversation = list(draft.agent_run_response.messages)
        draft_text = draft.agent_run_response.text.strip()
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
                    messages=original_request.conversation
                    + [ChatMessage(Role.USER, text="The draft is approved as-is.")],
                    should_respond=True,
                ),
                target_id=self.final_editor_id,
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
        conversation.append(ChatMessage(Role.USER, text=instruction))
        await ctx.send_message(
            AgentExecutorRequest(messages=conversation, should_respond=True), target_id=self.writer_id
        )


def display_agent_run_update(event: AgentRunUpdateEvent, last_executor: str | None) -> None:
    """Display an AgentRunUpdateEvent in a readable format."""
    printed_tool_calls: set[str] = set()
    printed_tool_results: set[str] = set()
    executor_id = event.executor_id
    update = event.data
    # Extract and print any new tool calls or results from the update.
    function_calls = [c for c in update.contents if isinstance(c, FunctionCallContent)]  # type: ignore[union-attr]
    function_results = [c for c in update.contents if isinstance(c, FunctionResultContent)]  # type: ignore[union-attr]
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


async def main() -> None:
    """Run the workflow and bridge human feedback between two agents."""
    # Create agents with tools and instructions.
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    writer_agent = chat_client.create_agent(
        name="writer_agent",
        instructions=(
            "You are a marketing writer. Call the available tools before drafting copy so you are precise. "
            "Always call both tools once before drafting. Summarize tool outputs as bullet points, then "
            "produce a 3-sentence draft."
        ),
        tools=[fetch_product_brief, get_brand_voice_profile],
        tool_choice=ToolMode.REQUIRED_ANY,
    )

    final_editor_agent = chat_client.create_agent(
        name="final_editor_agent",
        instructions=(
            "You are an editor who polishes marketing copy after human approval. "
            "Correct any legal or factual issues. Return the final version even if no changes are made. "
        ),
    )

    coordinator = Coordinator(
        id="coordinator",
        writer_id="writer_agent",
        final_editor_id="final_editor_agent",
    )

    # Build the workflow.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(writer_agent)
        .add_edge(writer_agent, coordinator)
        .add_edge(coordinator, writer_agent)
        .add_edge(final_editor_agent, coordinator)
        .add_edge(coordinator, final_editor_agent)
        .build()
    )

    # Switch to turn on agent run update display.
    # By default this is off to reduce clutter during human input.
    display_agent_run_update_switch = False

    print(
        "Interactive mode. When prompted, provide a short feedback note for the editor.",
        flush=True,
    )

    pending_responses: dict[str, str] | None = None
    completed = False
    initial_run = True

    while not completed:
        last_executor: str | None = None
        if initial_run:
            stream = workflow.run_stream(
                "Create a short launch blurb for the LumenX desk lamp. Emphasize adjustability and warm lighting."
            )
            initial_run = False
        elif pending_responses is not None:
            stream = workflow.send_responses_streaming(pending_responses)
            pending_responses = None
        else:
            break

        requests: list[tuple[str, DraftFeedbackRequest]] = []

        async for event in stream:
            if isinstance(event, AgentRunUpdateEvent) and display_agent_run_update_switch:
                display_agent_run_update(event, last_executor)
            if isinstance(event, RequestInfoEvent) and isinstance(event.data, DraftFeedbackRequest):
                # Stash the request so we can prompt the human after the stream completes.
                requests.append((event.request_id, event.data))
                last_executor = None
            elif isinstance(event, WorkflowOutputEvent):
                last_executor = None
                response = event.data
                print("\n===== Final output =====")
                final_text = getattr(response, "text", str(response))
                print(final_text.strip())
                completed = True

        if requests and not completed:
            responses: dict[str, str] = {}
            for request_id, request in requests:
                print("\n----- Writer draft -----")
                print(request.draft_text.strip())
                print("\nProvide guidance for the editor (or 'approve' to accept the draft).")
                answer = input("Human feedback: ").strip()  # noqa: ASYNC250
                if answer.lower() == "exit":
                    print("Exiting...")
                    return
                responses[request_id] = answer
            pending_responses = responses

    print("Workflow complete.")


if __name__ == "__main__":
    asyncio.run(main())
