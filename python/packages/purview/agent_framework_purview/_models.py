# Copyright (c) Microsoft. All rights reserved.

"""Public re-export surface for Purview models.

Concrete implementations live under `agent_framework_purview.models`. This shim preserves
backward compatibility for existing imports while allowing internal package structure.
"""

from __future__ import annotations

from .models.content import (
    ContentBase,
    ContentToProcess,
    GraphDataTypeBase,
    ProcessConversationMetadata,
    PurviewBinaryContent,
    PurviewTextContent,
)
from .models.enums import (
    Activity,
    DlpAction,
    ExecutionMode,
    PolicyPivotProperty,
    ProtectionScopeActivities,
    ProtectionScopeState,
    RestrictionAction,
    translate_activity,
)
from .models.requests import (
    ContentActivitiesRequest,
    ProcessContentRequest,
    ProtectionScopesRequest,
)
from .models.responses import (
    ContentActivitiesResponse,
    PolicyScope,
    ProcessContentResponse,
    ProcessingError,
    ProtectionScopesResponse,
)
from .models.simples import (
    AccessedResourceDetails,
    ActivityMetadata,
    AiAgentInfo,
    AiInteractionPlugin,
    DeviceMetadata,
    DlpActionInfo,
    IntegratedAppMetadata,
    OperatingSystemSpecifications,
    PolicyLocation,
    ProtectedAppMetadata,
)

__all__ = [
    "AccessedResourceDetails",
    "Activity",
    "ActivityMetadata",
    "AiAgentInfo",
    "AiInteractionPlugin",
    "ContentActivitiesRequest",
    "ContentActivitiesResponse",
    "ContentBase",
    "ContentToProcess",
    "DeviceMetadata",
    "DlpAction",
    "DlpActionInfo",
    "ExecutionMode",
    "GraphDataTypeBase",
    "IntegratedAppMetadata",
    "OperatingSystemSpecifications",
    "PolicyLocation",
    "PolicyPivotProperty",
    "PolicyScope",
    "ProcessContentRequest",
    "ProcessContentResponse",
    "ProcessConversationMetadata",
    "ProcessingError",
    "ProtectedAppMetadata",
    "ProtectionScopeActivities",
    "ProtectionScopeState",
    "ProtectionScopesRequest",
    "ProtectionScopesResponse",
    "PurviewBinaryContent",
    "PurviewTextContent",
    "RestrictionAction",
    "translate_activity",
]
