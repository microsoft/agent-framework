# Copyright (c) Microsoft. All rights.

import asyncio
import logging

from agent_framework import AgentRunResponseUpdate, ChatClientAgent, ChatMessage, HostedCodeInterpreterTool
from agent_framework.openai import OpenAIAssistantsClient, OpenAIChatClient
from agent_framework_workflow import (
    MagenticWorkflowBuilder,
    WorkflowCompletedEvent,
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

"""
Magentic Workflow (multi-agent) sample.

This sample shows how to orchestrate multiple agents using the
MagenticWorkflowBuilder:

- ResearcherAgent (ChatClientAgent backed by an OpenAI chat client) for
    finding information.
- CoderAgent (ChatClientAgent backed by OpenAI Assistants with the hosted
    code interpreter tool) for analysis and computation.

The workflow is configured with:
- A Standard Magentic manager (uses a chat client for planning and progress).
- Callbacks for final results, per-message agent responses, and streaming
    token updates.

When run, the script builds the workflow, submits a task about estimating the
energy efficiency and CO2 emissions of several ML models, streams intermediate
events to the console, and prints the final aggregated answer at completion.
"""


async def main() -> None:
    researcher_agent = ChatClientAgent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        # This agent requires the gpt-4o-search-preview model to perform web searches.
        # Feel free to explore with other agents that support web search, for example,
        # the `OpenAIResponseAgent` or `AzureAIAgent` with bing grounding.
        chat_client=OpenAIChatClient(ai_model_id="gpt-4o-search-preview"),
    )

    async with ChatClientAgent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        chat_client=OpenAIAssistantsClient(),
        tools=HostedCodeInterpreterTool(),
    ) as coder_agent:
        # Callbacks
        async def on_result(final_answer: ChatMessage) -> None:
            print("\n" + "=" * 50)
            print("FINAL RESULT:")
            print("=" * 50)
            print(final_answer.text)
            print("=" * 50)

        async def on_agent_response(agent_id: str, message: ChatMessage) -> None:
            # Non-streaming callback: final messages from orchestrator and agents
            response_text = (message.text or "").replace("\n", " ")
            print(f"\n[on_agent_response] {agent_id}: {message.role.value}\n\n{response_text}\n{'-' * 26}")

        async def on_agent_stream(agent_id: str, update: AgentRunResponseUpdate, is_final: bool) -> None:
            # Streaming callback: incremental agent updates when available
            # Print the agent id once and append chunks on the same line until final.
            nonlocal last_stream_agent_id, stream_line_open

            chunk = getattr(update, "text", None)
            if not chunk:
                try:
                    # Fallback: concatenate text from contents if present
                    contents = getattr(update, "contents", []) or []
                    chunk = "".join(getattr(c, "text", "") for c in contents)
                except Exception:
                    chunk = None
            if not chunk:
                return

            if last_stream_agent_id != agent_id or not stream_line_open:
                if stream_line_open:
                    print()  # close previous agent's line
                print(f"\n[on_agent_stream] {agent_id}: ", end="", flush=True)
                last_stream_agent_id = agent_id
                stream_line_open = True

            print(chunk, end="", flush=True)

            if is_final:
                print(" (final)")
                stream_line_open = False
                print()

        print("\nBuilding Magentic Workflow...")

        # State used by on_agent_stream callback
        last_stream_agent_id: str | None = None
        stream_line_open: bool = False

        workflow = (
            MagenticWorkflowBuilder()
            .participants(researcher=researcher_agent, coder=coder_agent)
            .on_result(on_result)
            .on_agent_response(on_agent_response)
            .on_agent_stream(on_agent_stream)
            .with_standard_manager(
                chat_client=OpenAIChatClient(),
                max_round_count=10,
                max_stall_count=3,
                max_reset_count=2,
            )
            .build()
        )

        task = (
            "I am preparing a report on the energy efficiency of different machine learning model architectures. "
            "Compare the estimated training and inference energy consumption of ResNet-50, BERT-base, and GPT-2 "
            "on standard datasets (e.g., ImageNet for ResNet, GLUE for BERT, WebText for GPT-2). "
            "Then, estimate the CO2 emissions associated with each, assuming training on an Azure Standard_NC6s_v3 "
            "VM for 24 hours. Provide tables for clarity, and recommend the most energy-efficient model "
            "per task type (image classification, text classification, and text generation)."
        )

        print(f"\nTask: {task}")
        print("\nStarting workflow execution...")

        try:
            completion_event = None
            async for event in workflow.run_streaming(task):
                print(f"Event: {event}")

                if isinstance(event, WorkflowCompletedEvent):
                    completion_event = event

            if completion_event is not None:
                data = getattr(completion_event, "data", None)
                preview = getattr(data, "text", None) or (str(data) if data is not None else "")
                print(f"Workflow completed with result:\n\n{preview}")

        except Exception as e:
            print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
