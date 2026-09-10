# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from ._invocations import InvocationsHostServer
    from ._responses import ResponsesHostServer
    from ._state_store import (
        AgentSessionStoreProvider,
        CheckpointStoreProvider,
        ContextScopedStoreProvider,
        FoundryAgentSessionStore,
        FoundryCheckpointStore,
        FoundryFunctionApprovalStore,
        FunctionApprovalStore,
        FunctionApprovalStoreProvider,
        StoreProvider,
    )
    from ._toolbox import FoundryToolbox

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

_LAZY_EXPORTS: Final[dict[str, str]] = {
    "AgentSessionStoreProvider": "._state_store",
    "CheckpointStoreProvider": "._state_store",
    "ContextScopedStoreProvider": "._state_store",
    "FoundryAgentSessionStore": "._state_store",
    "FoundryCheckpointStore": "._state_store",
    "FoundryFunctionApprovalStore": "._state_store",
    "FoundryToolbox": "._toolbox",
    "FunctionApprovalStore": "._state_store",
    "FunctionApprovalStoreProvider": "._state_store",
    "InvocationsHostServer": "._invocations",
    "ResponsesHostServer": "._responses",
    "StoreProvider": "._state_store",
}

__all__ = [
    "AgentSessionStoreProvider",
    "CheckpointStoreProvider",
    "ContextScopedStoreProvider",
    "FoundryAgentSessionStore",
    "FoundryCheckpointStore",
    "FoundryFunctionApprovalStore",
    "FoundryToolbox",
    "FunctionApprovalStore",
    "FunctionApprovalStoreProvider",
    "InvocationsHostServer",
    "ResponsesHostServer",
    "StoreProvider",
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
