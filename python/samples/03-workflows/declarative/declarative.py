# Copyright (c) Microsoft. All rights reserved.

"""
Declarative Workflow Sample

Demonstrates defining workflows in YAML and loading them with WorkflowFactory.
A simple greeting workflow is defined declaratively and run with different inputs.

What you'll learn:
- Defining workflows in YAML files
- Loading and running declarative workflows with WorkflowFactory
- Passing inputs to declarative workflows

Related samples:
- ../sequential/ — Programmatic sequential workflows
- ../state-management/ — Share state across steps

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
from pathlib import Path

from agent_framework.declarative import WorkflowFactory


# <running>
async def main() -> None:
    """Run the simple greeting workflow."""
    factory = WorkflowFactory()

    # <workflow_definition>
    workflow_path = Path(__file__).parent / "workflow.yaml"
    workflow = factory.create_workflow_from_yaml_path(workflow_path)
    # </workflow_definition>

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
# </running>


if __name__ == "__main__":
    asyncio.run(main())
