# Copyright (c) Microsoft. All rights reserved.

"""Simple workflow sample - demonstrates basic variable setting and output."""

import asyncio
from pathlib import Path

from agent_framework.declarative import WorkflowFactory


async def main() -> None:
    """Run the simple greeting workflow."""
    # Create a workflow factory
    factory = WorkflowFactory()

    # Load the workflow from YAML
    workflow_path = Path(__file__).parent / "workflow.yaml"
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print(f"Loaded workflow: {workflow.name}")
    print("-" * 40)

    # Run with default name
    print("\nRunning with default name:")
    result = await workflow.run({})
    for output in result.get_outputs():
        print(f"  Output: {output}")

    # Run with a custom name
    print("\nRunning with custom name 'Alice':")
    result = await workflow.run({"name": "Alice"})
    for output in result.get_outputs():
        print(f"  Output: {output}")

    print("\n" + "-" * 40)
    print("Workflow completed!")


if __name__ == "__main__":
    asyncio.run(main())
