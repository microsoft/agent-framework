# Copyright (c) Microsoft. All rights reserved.

"""AG-UI protocol integration for Agent Framework."""

import importlib.metadata
from typing import TYPE_CHECKING, Any

from ._agent import AgentFrameworkAgent
from ._client import AGUIChatClient
from ._endpoint import add_agent_framework_fastapi_endpoint
from ._event_converters import AGUIEventConverter
from ._http_service import AGUIHttpService
from ._snapshots import (
    DEFAULT_MAX_THREAD_SNAPSHOTS,
    AGUIThreadID,
    AGUIThreadSnapshot,
    AGUIThreadSnapshotStore,
    InMemoryAGUIThreadSnapshotStore,
    SnapshotScope,
    SnapshotScopeResolver,
)
from ._state import state_update
from ._types import AgentState, AGUIChatOptions, AGUIRequest, PredictStateConfig, RunMetadata
from ._workflow import AgentFrameworkWorkflow, WorkflowFactory

if TYPE_CHECKING:
    from ._a2ui import A2UIAgent, enable_a2ui, plan_a2ui_injection

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

# Default OpenAPI tags for AG-UI endpoints
DEFAULT_TAGS = ["AG-UI"]

__all__ = [
    "AgentFrameworkAgent",
    "AgentFrameworkWorkflow",
    "WorkflowFactory",
    "add_agent_framework_fastapi_endpoint",
    "AGUIChatClient",
    "AGUIChatOptions",
    "AGUIEventConverter",
    "AGUIHttpService",
    "AGUIRequest",
    "AGUIThreadID",
    "AGUIThreadSnapshot",
    "AGUIThreadSnapshotStore",
    "AgentState",
    "InMemoryAGUIThreadSnapshotStore",
    "PredictStateConfig",
    "RunMetadata",
    "SnapshotScope",
    "SnapshotScopeResolver",
    "DEFAULT_MAX_THREAD_SNAPSHOTS",
    "DEFAULT_TAGS",
    "state_update",
    "__version__",
    # A2UI (lazy — require ag-ui-a2ui-toolkit)
    "A2UIAgent",
    "enable_a2ui",
    "plan_a2ui_injection",
]

# A2UI symbols are loaded lazily so importing this package does not require
# ag-ui-a2ui-toolkit unless A2UI is actually used.
_A2UI_LAZY = {"A2UIAgent", "enable_a2ui", "plan_a2ui_injection"}


def __getattr__(name: str) -> Any:
    if name in _A2UI_LAZY:
        import importlib

        return getattr(importlib.import_module("._a2ui", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
