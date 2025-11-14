# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework DevUI Models - OpenAI-compatible types and custom extensions."""

# Import discovery models
# Import all OpenAI types directly from the openai package
from openai.types.conversations import Conversation, ConversationDeletedResource
from openai.types.conversations.conversation_item import ConversationItem
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionToolCall,
    ResponseFunctionToolCallOutputItem,
    ResponseInputParam,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
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

from ._discovery_models import Deployment, DeploymentConfig, DeploymentEvent, DiscoveryResponse, EntityInfo
from ._openai_custom import (
    AgentFrameworkRequest,
    CustomResponseOutputItemAddedEvent,
    CustomResponseOutputItemDoneEvent,
    ExecutorActionItem,
    MetaResponse,
    OpenAIError,
    ResponseFunctionResultComplete,
    ResponseOutputData,
    ResponseOutputFile,
    ResponseOutputImage,
    ResponseTraceEvent,
    ResponseTraceEventComplete,
    ResponseWorkflowEventComplete,
)

# Type alias for compatibility
OpenAIResponse = Response

# Export all types for easy importing
__all__ = [
    "AgentFrameworkRequest",
    "Conversation",
    "ConversationDeletedResource",
    "ConversationItem",
    "CustomResponseOutputItemAddedEvent",
    "CustomResponseOutputItemDoneEvent",
    "Deployment",
    "DeploymentConfig",
    "DeploymentEvent",
    "DiscoveryResponse",
    "EntityInfo",
    "ExecutorActionItem",
    "InputTokensDetails",
    "MetaResponse",
    "Metadata",
    "OpenAIError",
    "OpenAIResponse",
    "OutputTokensDetails",
    "Response",
    "ResponseCompletedEvent",
    "ResponseErrorEvent",
    "ResponseFunctionCallArgumentsDeltaEvent",
    "ResponseFunctionResultComplete",
    "ResponseFunctionToolCall",
    "ResponseFunctionToolCallOutputItem",
    "ResponseInputParam",
    "ResponseOutputData",
    "ResponseOutputFile",
    "ResponseOutputImage",
    "ResponseOutputItemAddedEvent",
    "ResponseOutputItemDoneEvent",
    "ResponseOutputMessage",
    "ResponseOutputText",
    "ResponseReasoningTextDeltaEvent",
    "ResponseStreamEvent",
    "ResponseTextDeltaEvent",
    "ResponseTraceEvent",
    "ResponseTraceEventComplete",
    "ResponseUsage",
    "ResponseWorkflowEventComplete",
    "ResponsesModel",
    "ToolParam",
]
