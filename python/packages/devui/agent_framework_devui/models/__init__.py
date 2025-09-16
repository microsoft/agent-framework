# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework DevUI Models - OpenAI-compatible types and custom extensions."""

# Import discovery models
from ._discovery_models import DiscoveryResponse, EntityInfo

# Import all OpenAI-compatible types
from ._openai_compat import (
    InputTokensDetails,
    Metadata,
    OpenAIResponse,
    OutputTokensDetails,
    Response,
    ResponseErrorEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseInputParam,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningTextDeltaEvent,
    ResponsesModel,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
    ResponseUsage,
    ToolParam,
)

# Import all custom Agent Framework types
from ._openai_custom import (
    AgentFrameworkRequest,
    OpenAIError,
    ResponseFunctionResultComplete,
    ResponseFunctionResultDelta,
    ResponseTraceEvent,
    ResponseTraceEventComplete,
    ResponseTraceEventDelta,
    ResponseUsageEventComplete,
    ResponseUsageEventDelta,
    ResponseWorkflowEventComplete,
    ResponseWorkflowEventDelta,
)

# Version info: OpenAI types copied from version 1.107.1 (2025-01-15)

# Export all types for easy importing
__all__ = [
    "AgentFrameworkRequest",
    "DiscoveryResponse",
    "EntityInfo",
    "InputTokensDetails",
    "Metadata",
    "OpenAIError",
    "OpenAIResponse",
    "OutputTokensDetails",
    "Response",
    "ResponseErrorEvent",
    "ResponseFunctionCallArgumentsDeltaEvent",
    "ResponseFunctionResultComplete",
    "ResponseFunctionResultDelta",
    "ResponseInputParam",
    "ResponseOutputMessage",
    "ResponseOutputText",
    "ResponseReasoningTextDeltaEvent",
    "ResponseStreamEvent",
    "ResponseTextDeltaEvent",
    "ResponseTraceEvent",
    "ResponseTraceEventComplete",
    "ResponseTraceEventDelta",
    "ResponseUsage",
    "ResponseUsageEventComplete",
    "ResponseUsageEventDelta",
    "ResponseWorkflowEventComplete",
    "ResponseWorkflowEventDelta",
    "ResponsesModel",
    "ToolParam",
]
