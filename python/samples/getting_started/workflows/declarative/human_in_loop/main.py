# Copyright (c) Microsoft. All rights reserved.

"""
Run the human-in-loop workflow sample.

Usage:
    python main.py

Demonstrates interactive workflows that request user input.

Note: This sample shows the conceptual pattern for handling ExternalInputRequest.
In a production scenario, you would integrate with a real UI or chat interface.
"""

import asyncio
from pathlib import Path

from agent_framework import Workflow, WorkflowOutputEvent
from agent_framework.declarative import ExternalInputRequest, WorkflowFactory
from agent_framework_declarative._workflows._handlers import TextOutputEvent


async def run_with_streaming(workflow: Workflow) -> None:
    """Demonstrate streaming workflow execution with run_stream()."""
    print("\n=== Streaming Execution (run_stream) ===")
    print("-" * 40)

    async for event in workflow.run_stream({}):
        # WorkflowOutputEvent wraps the actual output data
        if isinstance(event, WorkflowOutputEvent):
            data = event.data
            if isinstance(data, TextOutputEvent):
                print(f"[Bot]: {data.text}")
            elif isinstance(data, ExternalInputRequest):
                # In a real scenario, you would:
                # 1. Display the prompt to the user
                # 2. Wait for their response
                # 3. Use the response to continue the workflow
                output_property = data.metadata.get("output_property", "unknown")
                print(f"[System] Input requested for: {output_property}")
                if data.message:
                    print(f"[System] Prompt: {data.message}")
            else:
                print(f"[Output]: {data}")


async def run_with_result(workflow: Workflow) -> None:
    """Demonstrate batch workflow execution with run()."""
    print("\n=== Batch Execution (run) ===")
    print("-" * 40)

    result = await workflow.run({})
    for output in result.get_outputs():
        print(f"  Output: {output}")


async def main() -> None:
    """Run the human-in-loop workflow demonstrating both execution styles."""
    # Create a workflow factory
    factory = WorkflowFactory()

    # Load the workflow from YAML
    workflow_path = Path(__file__).parent / "workflow.yaml"
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print(f"Loaded workflow: {workflow.name}")
    print("=== Human-in-Loop Workflow Demo ===")
    print("(Using simulated responses for demonstration)")

    # Demonstrate streaming execution
    await run_with_streaming(workflow)

    # Demonstrate batch execution
    # await run_with_result(workflow)

    print("\n" + "-" * 40)
    print("=== Workflow Complete ===")
    print()
    print("Note: This demo uses simulated responses. In a real application,")
    print("you would integrate with a chat interface to collect actual user input.")


if __name__ == "__main__":
    asyncio.run(main())
