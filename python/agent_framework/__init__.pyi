# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._logging import get_logger
from ._tools import AITool
from ._types import (
    AIContent,
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
    ModelClient,
    TextContent,
    TextReasoningContent,
    UriContent,
)
from .guard_rails import InputGuardrail, OutputGuardrail

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AIContent",
    "AITool",
    "ChatFinishReason",
    "ChatMessage",
    "ChatOptions",
    "ChatResponse",
    "ChatResponseUpdate",
    "ChatRole",
    "ChatToolMode",
    "DataContent",
    "ErrorContent",
    "FunctionCallContent",
    "FunctionResultContent",
    "InputGuardrail",
    "ModelClient",
    "OutputGuardrail",
    "TextContent",
    "TextReasoningContent",
    "UriContent",
    "__version__",
    "get_logger",
]
