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
from typing import cast

from agent_framework import Workflow
from agent_framework.declarative import ExternalInputRequest, WorkflowFactory


async def run_with_streaming(workflow: Workflow) -> None:
    """Demonstrate streaming workflow execution."""
    print("\n=== Streaming Execution ===")
    print("-" * 40)

    async for event in workflow.run({}, stream=True):
        # WorkflowOutputEvent wraps the actual output data
        if event.type == "output":
            data = event.data
            if isinstance(data, str):
                print(f"[Bot]: {data}")
            else:
                print(f"[Output]: {data}")
        elif event.type == "request_info":
            request = cast(ExternalInputRequest, event.data)
            # In a real scenario, you would:
            # 1. Display the prompt to the user
            # 2. Wait for their response
            # 3. Use the response to continue the workflow
            output_property = request.metadata.get("output_property", "unknown")
            print(f"[System] Input requested for: {output_property}")
            if request.message:
                print(f"[System] Prompt: {request.message}")


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

    print("\n" + "-" * 40)
    print("=== Workflow Complete ===")
    print()
    print("Note: This demo uses simulated responses. In a real application,")
    print("you would integrate with a chat interface to collect actual user input.")


if __name__ == "__main__":
    asyncio.run(main())
