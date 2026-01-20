# Copyright (c) Microsoft. All rights reserved.

"""
Run the marketing copy workflow sample.

Usage:
    python main.py

Demonstrates sequential multi-agent pipeline:
- AnalystAgent: Identifies key features, target audience, USPs
- WriterAgent: Creates compelling marketing copy
- EditorAgent: Polishes grammar, clarity, and tone
"""

import asyncio
from pathlib import Path

from agent_framework import WorkflowOutputEvent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.declarative import WorkflowFactory
from azure.identity import AzureCliCredential

ANALYST_INSTRUCTIONS = """You are a product analyst. Analyze the given product and identify:
1. Key features and benefits
2. Target audience demographics
3. Unique selling propositions (USPs)
4. Competitive advantages

Be concise and structured in your analysis."""

WRITER_INSTRUCTIONS = """You are a marketing copywriter. Based on the product analysis provided,
create compelling marketing copy that:
1. Has a catchy headline
2. Highlights key benefits
3. Speaks to the target audience
4. Creates emotional connection
5. Includes a call to action

Write in an engaging, persuasive tone."""

EDITOR_INSTRUCTIONS = """You are a senior editor. Review and polish the marketing copy:
1. Fix any grammar or spelling issues
2. Improve clarity and flow
3. Ensure consistent tone
4. Tighten the prose
5. Make it more impactful

Return the final polished version."""


async def main() -> None:
    """Run the marketing workflow with real Azure AI agents."""
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    analyst_agent = chat_client.as_agent(
        name="AnalystAgent",
        instructions=ANALYST_INSTRUCTIONS,
    )
    writer_agent = chat_client.as_agent(
        name="WriterAgent",
        instructions=WRITER_INSTRUCTIONS,
    )
    editor_agent = chat_client.as_agent(
        name="EditorAgent",
        instructions=EDITOR_INSTRUCTIONS,
    )

    factory = WorkflowFactory(
        agents={
            "AnalystAgent": analyst_agent,
            "WriterAgent": writer_agent,
            "EditorAgent": editor_agent,
        }
    )

    workflow_path = Path(__file__).parent / "workflow.yaml"
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print(f"Loaded workflow: {workflow.name}")
    print("=" * 60)
    print("Marketing Copy Generation Pipeline")
    print("=" * 60)

    # Pass a simple string input - like .NET
    product = "An eco-friendly stainless steel water bottle that keeps drinks cold for 24 hours."

    async for event in workflow.run_stream(product):
        if isinstance(event, WorkflowOutputEvent):
            print(f"{event.data}", end="", flush=True)

    print("\n" + "=" * 60)
    print("Pipeline Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
