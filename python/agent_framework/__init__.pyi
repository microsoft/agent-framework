# Copyright (c) Microsoft. All rights reserved.

from . import __version__  # type: ignore[attr-defined]
from ._agents import Agent, AgentThread
from ._ai_service_client_base import AIServiceClientBase
from ._clients import ChatClient, EmbeddingGenerator
from ._logging import get_logger

# TODO(peterychang): remove this once all connectors have migrated to the new options
from ._prompt_execution_settings import PromptExecutionSettings
from ._pydantic import AFBaseModel, AFBaseSettings
from ._tools import AITool, ai_function
from ._types import (
    AIContent,
    AIContents,
    ChatFinishReason,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    ChatToolMode,
    DataContent,
    ErrorContent,
    FunctionCallContent,
    FunctionResultContent,
    GeneratedEmbeddings,
    SpeechToTextOptions,
    StructuredResponse,
    TextContent,
    TextReasoningContent,
    TextToSpeechOptions,
    UriContent,
    UsageContent,
    UsageDetails,
)
from .guard_rails import InputGuardrail, OutputGuardrail

__all__ = [
    "AFBaseModel",
    "AFBaseSettings",
    "AIContent",
    "AIContents",
    "AIServiceClientBase",
    "AITool",
    "Agent",
    "AgentThread",
    "ChatClient",
    "ChatFinishReason",
    "ChatMessage",
    "ChatOptions",
    "ChatResponse",
    "ChatResponseUpdate",
    "ChatRole",
    "ChatToolMode",
    "DataContent",
    "EmbeddingGenerator",
    "ErrorContent",
    "FunctionCallContent",
    "FunctionResultContent",
    "GeneratedEmbeddings",
    "InputGuardrail",
    "OutputGuardrail",
    "PromptExecutionSettings",
    "SpeechToTextOptions",
    "StructuredResponse",
    "TextContent",
    "TextReasoningContent",
    "TextToSpeechOptions",
    "UriContent",
    "UsageContent",
    "UsageDetails",
    "__version__",
    "ai_function",
    "get_logger",
]
