# Copyright (c) Microsoft. All rights reserved.

"""Workflow Execution for Durable Functions.

This module provides the Azure Functions entry point for workflow orchestration.
The actual orchestration logic lives in the shared module
``agent_framework_durabletask._workflows.orchestrator`` and is host-agnostic.
This module re-exports the public API and provides the AF-specific
``run_workflow_orchestrator`` wrapper that creates an
:class:`AzureFunctionsWorkflowContext` before delegating.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from agent_framework import Workflow
from agent_framework_durabletask._workflows.orchestrator import (
    SOURCE_HITL_RESPONSE,
    SOURCE_ORCHESTRATOR,
    SOURCE_WORKFLOW_START,
    ExecutorResult,
    PendingHITLRequest,
    TaskMetadata,
    TaskType,
    _extract_message_content,  # pyright: ignore[reportPrivateUsage]
    build_agent_executor_response,
    execute_hitl_response_handler,
    route_message_through_edge_groups,
)
from agent_framework_durabletask._workflows.orchestrator import (
    run_workflow_orchestrator as _run_workflow_orchestrator_shared,
)
from azure.durable_functions import DurableOrchestrationContext

from ._workflow_af_context import AzureFunctionsWorkflowContext

logger = logging.getLogger(__name__)

# Re-export shared symbols for backward compatibility
__all__ = [
    "SOURCE_HITL_RESPONSE",
    "SOURCE_ORCHESTRATOR",
    "SOURCE_WORKFLOW_START",
    "ExecutorResult",
    "PendingHITLRequest",
    "TaskMetadata",
    "TaskType",
    "_extract_message_content",
    "build_agent_executor_response",
    "execute_hitl_response_handler",
    "route_message_through_edge_groups",
    "run_workflow_orchestrator",
]


def run_workflow_orchestrator(
    context: DurableOrchestrationContext,
    workflow: Workflow,
    initial_message: Any,
    shared_state: dict[str, Any] | None = None,
) -> Generator[Any, Any, list[Any]]:
    """Azure Functions wrapper around the shared workflow orchestrator.

    Creates an :class:`AzureFunctionsWorkflowContext` and delegates to the
    host-agnostic :func:`run_workflow_orchestrator` in the durabletask package.

    Args:
        context: The Azure Functions ``DurableOrchestrationContext``.
        workflow: The MAF Workflow instance to execute.
        initial_message: Initial message to send to the start executor.
        shared_state: Optional dict for cross-executor state sharing.

    Returns:
        List of workflow outputs collected from executor activities.
    """
    af_ctx = AzureFunctionsWorkflowContext(context)
    return _run_workflow_orchestrator_shared(af_ctx, workflow, initial_message, shared_state)
