# Copyright (c) Microsoft. All rights reserved.

"""
Run the declarative workflow sample with DevUI.

Demonstrates conditional branching based on age input using YAML-defined workflow.
"""

from pathlib import Path

from agent_framework.declarative import WorkflowFactory
from agent_framework.devui import serve

_factory = WorkflowFactory()
_workflow_path = Path(__file__).parent / "workflow.yaml"
workflow = _factory.create_workflow_from_yaml_path(_workflow_path)


def main():
    """Run the declarative workflow with DevUI."""
    serve(entities=[workflow], auto_open=True)


if __name__ == "__main__":
    main()
