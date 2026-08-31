# Copyright (c) Microsoft. All rights reserved.

from typing import ClassVar

from agent_framework._telemetry import FeatureIndex as CoreFeatureIndex
from agent_framework._workflows._workflow_builder import WorkflowBuilder


class OrchestrationWorkflowBuilder(WorkflowBuilder):
    """Workflow builder that leaves usage attribution to the orchestration."""

    _FEATURE_USAGE_INDEX: ClassVar[CoreFeatureIndex | None] = None
