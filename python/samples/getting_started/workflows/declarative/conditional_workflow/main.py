# Copyright (c) Microsoft. All rights reserved.

"""
Run the conditional workflow sample.

Usage:
    python main.py

Demonstrates conditional branching based on age input.
"""

import asyncio
from pathlib import Path

from agent_framework.declarative import WorkflowFactory


async def main() -> None:
    """Run the conditional workflow with various age inputs."""
    # Create a workflow factory
    factory = WorkflowFactory()

    # Load the workflow from YAML
    workflow_path = Path(__file__).parent / "workflow.yaml"
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print(f"Loaded workflow: {workflow.name}")
    print("-" * 40)

    # Print out the executors in this workflow
    print("\nExecutors in workflow:")
    for executor_id, executor in workflow.executors.items():
        print(f"  - {executor_id}: {type(executor).__name__}")
    print("-" * 40)

    # Test with different ages
    test_ages = [8, 15, 35, 70]

    for age in test_ages:
        print(f"\n--- Testing with age: {age} ---")

        # Run the workflow with age input
        result = await workflow.run({"age": age})
        for output in result.get_outputs():
            print(f"  Output: {output}")

    print("\n" + "-" * 40)
    print("Workflow completed for all test cases!")


if __name__ == "__main__":
    asyncio.run(main())
