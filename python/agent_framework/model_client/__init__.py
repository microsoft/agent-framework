# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from ._chat_content import (
    AIContent,
    DataContent,
    ErrorContent,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
    TextReasoningContent,
    UsageContent,
    UsageDetails,
)
from ._chat_message import (
    ChatFinishReason,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    CreatedAtT,
    StructuredResponse,
)
from ._chat_options import (
    AITool,
    AutoChatToolMode,
    ChatOptions,
    ChatResponseFormat,  # noqa: F401
    ChatResponseFormatJson,
    ChatResponseFormatText,
    ChatToolMode,  # noqa: F401
    NoneChatToolMode,
    RequiredChatToolMode,
)
from ._model_client import ModelClient

__ALL__ = [
    export.__name__
    for export in (
        AIContent,
        DataContent,
        ErrorContent,
        FunctionCallContent,
        FunctionResultContent,
        TextContent,
        TextReasoningContent,
        UsageContent,
        UsageDetails,
        ChatFinishReason,
        ChatMessage,
        ChatResponse,
        ChatResponseUpdate,
        ChatRole,
        CreatedAtT,
        StructuredResponse,
        AITool,
        AutoChatToolMode,
        ChatOptions,
        # ChatResponseFormat,
        ChatResponseFormatJson,
        ChatResponseFormatText,
        # ChatToolMode,
        NoneChatToolMode,
        RequiredChatToolMode,
        ChatOptions,
        ChatResponseFormatJson,
        ChatResponseFormatText,
        ModelClient,
    )
] + [
    "ChatResponseFormat",  # Alias for the union of response formats
    "ChatToolMode",  # Alias for the union of tool modes
]
