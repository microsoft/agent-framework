# Copyright (c) Microsoft. All rights reserved.

"""
Sample Validation Workflow using Microsoft Agent Framework.

Workflow composition for sample validation.
"""

from agent_framework import Workflow, WorkflowBuilder

from sample_validation.create_dynamic_workflow_executor import (
    CreateConcurrentValidationWorkflowExecutor,
)
from sample_validation.discovery import DiscoverSamplesExecutor, ValidationConfig
from sample_validation.report import GenerateReportExecutor
from sample_validation.run_dynamic_validation_workflow_executor import (
    RunDynamicValidationWorkflowExecutor,
)


def create_validation_workflow(
    config: ValidationConfig,
) -> Workflow:
    """
    Create the sample validation workflow.

    Args:
        config: Validation configuration

    Returns:
        Configured Workflow instance
    """
    discover = DiscoverSamplesExecutor(config)
    create_dynamic_workflow = CreateConcurrentValidationWorkflowExecutor(config)
    run_dynamic_workflow = RunDynamicValidationWorkflowExecutor()
    generate = GenerateReportExecutor()

    return (
        WorkflowBuilder(start_executor=discover)
        .add_edge(discover, create_dynamic_workflow)
        .add_edge(create_dynamic_workflow, run_dynamic_workflow)
        .add_edge(run_dynamic_workflow, generate)
        .build()
    )


__all__ = ["ValidationConfig", "create_validation_workflow"]
