# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import (
    MAGENTIC_EVENT_TYPE_AGENT_DELTA,
    MAGENTIC_EVENT_TYPE_ORCHESTRATOR,
    ChatAgent,
    HostedCodeInterpreterTool,
    MagenticBuilder,
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

    # Create a manager agent for orchestration
    manager_agent = ChatAgent(
        name="MagenticManager",
        description="Orchestrator that coordinates the research and coding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        chat_client=OpenAIChatClient(),
    )

    print("\nBuilding Magentic Workflow...")

    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher_agent, coder=coder_agent)
        .with_standard_manager(
            agent=manager_agent,
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
        # Wrap the workflow as an agent for composition scenarios
        print("\nWrapping workflow as an agent and running...")
        workflow_agent = workflow.as_agent(name="MagenticWorkflowAgent")
        async for response in workflow_agent.run_stream(task):
            # AgentRunResponseUpdate objects contain the streaming agent data
            # Check metadata to understand event type
            props = response.additional_properties
            event_type = props.get("magentic_event_type") if props else None

            if event_type == MAGENTIC_EVENT_TYPE_ORCHESTRATOR:
                kind = props.get("orchestrator_message_kind", "") if props else ""
                print(f"\n[ORCHESTRATOR:{kind}] {response.text}")
            elif event_type == MAGENTIC_EVENT_TYPE_AGENT_DELTA:
                if response.text:
                    print(response.text, end="", flush=True)
            elif response.text:
                # Fallback for any other events with text
                print(response.text, end="", flush=True)

    except Exception as e:
        print(f"Workflow execution failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
