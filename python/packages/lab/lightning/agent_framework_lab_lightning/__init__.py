# Copyright (c) Microsoft. All rights reserved.

"""RL Module for Microsoft Agent Framework."""

import importlib.metadata

from agent_framework.observability import enable_instrumentation
from agentlightning import AgentOpsTracer  # type: ignore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


class AgentFrameworkTracer(AgentOpsTracer):  # type: ignore
    """Tracer for Agent-framework.

    Tracer that enables OpenTelemetry observability for the Agent-framework,
    so that the traces are visible to Agent-lightning.
    """

    def init(self) -> None:
        """Initialize the agent-framework-lab-lightning for training."""
        enable_instrumentation()
        super().init()

    def teardown(self) -> None:
        """Teardown the agent-framework-lab-lightning for training."""
        super().teardown()


__all__: list[str] = ["AgentFrameworkTracer"]
