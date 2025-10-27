# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import (
    ChatAgent,
    HostedCodeInterpreterTool,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticBuilder,
    MagenticFinalResultEvent,
    MagenticOrchestratorMessageEvent,
    WorkflowOutputEvent,
)
from agent_framework.openai import OpenAIChatClient, OpenAIResponsesClient

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

"""
Sample: Build a Magentic orchestration and wrap it as an agent.

The script configures a Magentic workflow with streaming callbacks, then invokes the
orchestration through `workflow.as_agent(...)` so the entire Magentic loop can be reused
like any other agent while still emitting callback telemetry.

Prerequisites:
- OpenAI credentials configured for `OpenAIChatClient` and `OpenAIResponsesClient`.
"""


async def main() -> None:
    researcher_agent = ChatAgent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        # This agent requires the gpt-4o-search-preview model to perform web searches.
        # Feel free to explore with other agents that support web search, for example,
        # the `OpenAIResponseAgent` or `AzureAgentProtocol` with bing grounding.
        chat_client=OpenAIChatClient(model_id="gpt-4o-search-preview"),
    )

    coder_agent = ChatAgent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        chat_client=OpenAIResponsesClient(),
        tools=HostedCodeInterpreterTool(),
    )

    print("\nBuilding Magentic Workflow...")

    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher_agent, coder=coder_agent)
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
        last_stream_agent_id: str | None = None
        stream_line_open: bool = False
        final_output: str | None = None

        async for event in workflow.run_stream(task):
            if isinstance(event, MagenticOrchestratorMessageEvent):
                print(f"\n[ORCH:{event.kind}]\n\n{getattr(event.message, 'text', '')}\n{'-' * 26}")
            elif isinstance(event, MagenticAgentDeltaEvent):
                if last_stream_agent_id != event.agent_id or not stream_line_open:
                    if stream_line_open:
                        print()
                    print(f"\n[STREAM:{event.agent_id}]: ", end="", flush=True)
                    last_stream_agent_id = event.agent_id
                    stream_line_open = True
                if event.text:
                    print(event.text, end="", flush=True)
            elif isinstance(event, MagenticAgentMessageEvent):
                if stream_line_open:
                    print(" (final)")
                    stream_line_open = False
                    print()
                msg = event.message
                if msg is not None:
                    response_text = (msg.text or "").replace("\n", " ")
                    print(f"\n[AGENT:{event.agent_id}] {msg.role.value}\n\n{response_text}\n{'-' * 26}")
            elif isinstance(event, MagenticFinalResultEvent):
                print("\n" + "=" * 50)
                print("FINAL RESULT:")
                print("=" * 50)
                if event.message is not None:
                    print(event.message.text)
                print("=" * 50)
            elif isinstance(event, WorkflowOutputEvent):
                final_output = str(event.data) if event.data is not None else None

        if stream_line_open:
            print()
            stream_line_open = False

        if final_output is not None:
            print(f"\nWorkflow completed with result:\n\n{final_output}\n")

        # Wrap the workflow as an agent for composition scenarios
        workflow_agent = workflow.as_agent(name="MagenticWorkflowAgent")
        agent_result = await workflow_agent.run(task)

        if agent_result.messages:
            print("\n===== as_agent() Transcript =====")
            for i, msg in enumerate(agent_result.messages, start=1):
                role_value = getattr(msg.role, "value", msg.role)
                speaker = msg.author_name or role_value
                print(f"{'-' * 50}\n{i:02d} [{speaker}]\n{msg.text}")

    except Exception as e:
        print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
