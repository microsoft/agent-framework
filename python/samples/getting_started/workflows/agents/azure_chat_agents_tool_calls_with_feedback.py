# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from dataclasses import dataclass, field
from typing import Annotated

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    Role,
    ToolMode,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Sample: Tool-enabled agents with human feedback

Pipeline layout:
writer_agent (uses Azure OpenAI tools) -> DraftFeedbackCoordinator -> RequestInfoExecutor
-> DraftFeedbackCoordinator -> final_editor_agent

The writer agent calls tools to gather product facts before drafting copy. A custom executor
packages the draft and emits a RequestInfoEvent so a human can comment, then replays the human
guidance back into the conversation before the final editor agent produces the polished output.

Demonstrates:
- Attaching Python function tools to an agent inside a workflow.
- Capturing the writer's output and routing it through RequestInfoExecutor for human review.
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
class DraftFeedbackRequest(RequestInfoMessage):
    """Payload sent to RequestInfoExecutor for human review."""

    prompt: str = ""
    draft_text: str = ""
    conversation: list[ChatMessage] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class DraftFeedbackCoordinator(Executor):
    """Bridge between the writer agent, human feedback, and final editor."""

    def __init__(self, *, id: str = "draft_feedback_coordinator") -> None:
        super().__init__(id)

    @handler
    async def on_writer_response(
        self,
        draft: AgentExecutorResponse,
        ctx: WorkflowContext[DraftFeedbackRequest],
    ) -> None:
        # Preserve the full conversation so the final editor can see tool traces and the initial prompt.
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
        await ctx.send_message(DraftFeedbackRequest(prompt=prompt, draft_text=draft_text, conversation=conversation))

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[DraftFeedbackRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        note = (feedback.data or "").strip()
        request = feedback.original_request

        conversation: list[ChatMessage] = list(request.conversation)
        instruction = (
            "A human reviewer shared the following guidance:\n"
            f"{note or 'No specific guidance provided.'}\n\n"
            "Rewrite the draft from the previous assistant message into a polished final version. "
            "Keep the response under 120 words and reflect any requested tone adjustments."
        )
        conversation.append(ChatMessage(Role.USER, text=instruction))
        await ctx.send_message(AgentExecutorRequest(messages=conversation, should_respond=True))


async def main() -> None:
    """Run the workflow and bridge human feedback between two agents."""
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
            "You are an editor who polishes marketing copy using human guidance. "
            "Respect factual details from the prior messages while applying the feedback."
        ),
    )

    feedback_coordinator = DraftFeedbackCoordinator()
    request_info_executor = RequestInfoExecutor(id="human_feedback")

    workflow = (
        WorkflowBuilder()
        .add_agent(writer_agent, id="Writer")
        .add_agent(final_editor_agent, id="FinalEditor", output_response=True)
        .set_start_executor(writer_agent)
        .add_edge(writer_agent, feedback_coordinator)
        .add_edge(feedback_coordinator, request_info_executor)
        .add_edge(request_info_executor, feedback_coordinator)
        .add_edge(feedback_coordinator, final_editor_agent)
        .build()
    )

    print(
        "Interactive mode. When prompted, provide a short feedback note for the editor (type 'exit' to quit).",
        flush=True,
    )

    pending_responses: dict[str, str] | None = None
    completed = False
    printed_tool_calls: set[str] = set()
    printed_tool_results: set[str] = set()

    while not completed:
        last_executor: str | None = None
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses is not None
            else workflow.run_stream(
                "Create a short launch blurb for the LumenX desk lamp. Emphasize adjustability and warm lighting."
            )
        )
        pending_responses = None
        requests: list[tuple[str, DraftFeedbackRequest]] = []

        async for event in stream:
            if isinstance(event, AgentRunUpdateEvent):
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
                    if isinstance(args, dict):
                        args_preview = json.dumps(args, ensure_ascii=False)
                    else:
                        args_preview = (args or "").strip()
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
            elif isinstance(event, RequestInfoEvent) and isinstance(event.data, DraftFeedbackRequest):
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
                print("\nProvide guidance for the editor (or press Enter to accept the draft).")
                answer = input("Human feedback: ").strip()  # noqa: ASYNC250
                if answer.lower() == "exit":
                    print("Exiting...")
                    return
                responses[request_id] = answer
            pending_responses = responses

    print("Workflow complete.")


if __name__ == "__main__":
    asyncio.run(main())
