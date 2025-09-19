# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework DevUI Models - OpenAI-compatible types and custom extensions."""

# Import discovery models
# Import all OpenAI types directly from the openai package
from openai.types.responses import (
    Response,
    ResponseErrorEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseInputParam,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningTextDeltaEvent,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
    ResponseUsage,
    ToolParam,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails
from openai.types.shared import Metadata, ResponsesModel

from ._discovery_models import DiscoveryResponse, EntityInfo
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

# Type alias for compatibility
OpenAIResponse = Response

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
