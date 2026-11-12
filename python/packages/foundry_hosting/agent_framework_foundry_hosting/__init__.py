# Copyright (c) Microsoft. All rights reserved.

"""Expose Foundry agent hosts, native workflow hosts, and scoped storage integrations."""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from ._invocations_agent import InvocationsHostServer
    from ._invocations_workflow import InvocationsWorkflowHostServer
    from ._responses_agent import ResponsesHostServer
    from ._responses_workflow import ResponsesWorkflowHostServer
    from ._scope import FoundryRequestScope
    from ._shared import (
        AgentSessionStoreProvider,
        CheckpointStoreProvider,
        ContextScopedStoreProvider,
        FoundryAgentSessionStore,
        FoundryCheckpointStore,
        InvocationRun,
        ResponsesRequest,
        StoreProvider,
        WorkflowSource,
        WorkflowTurn,
        response_input_messages,
    )
    from ._toolbox import FoundryToolbox

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

_LAZY_EXPORTS: Final[dict[str, str]] = {
    "AgentSessionStoreProvider": "._shared",
    "CheckpointStoreProvider": "._shared",
    "ContextScopedStoreProvider": "._shared",
    "FoundryAgentSessionStore": "._shared",
    "FoundryCheckpointStore": "._shared",
    "FoundryRequestScope": "._scope",
    "FoundryToolbox": "._toolbox",
    "InvocationRun": "._shared",
    "InvocationsHostServer": "._invocations_agent",
    "InvocationsWorkflowHostServer": "._invocations_workflow",
    "ResponsesHostServer": "._responses_agent",
    "ResponsesRequest": "._shared",
    "ResponsesWorkflowHostServer": "._responses_workflow",
    "StoreProvider": "._shared",
    "WorkflowSource": "._shared",
    "WorkflowTurn": "._shared",
    "response_input_messages": "._shared",
}

__all__ = [
    "AgentSessionStoreProvider",
    "CheckpointStoreProvider",
    "ContextScopedStoreProvider",
    "FoundryAgentSessionStore",
    "FoundryCheckpointStore",
    "FoundryRequestScope",
    "FoundryToolbox",
    "InvocationRun",
    "InvocationsHostServer",
    "InvocationsWorkflowHostServer",
    "ResponsesHostServer",
    "ResponsesRequest",
    "ResponsesWorkflowHostServer",
    "StoreProvider",
    "WorkflowSource",
    "WorkflowTurn",
    "response_input_messages",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve public Foundry Hosting exports."""
    if module_name := _LAZY_EXPORTS.get(name):
        value = getattr(importlib.import_module(module_name, __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return public names for interactive discovery."""
    return sorted(set(globals()) | set(__all__))
