# Copyright (c) Microsoft. All rights reserved.

import importlib
import importlib.metadata
from typing import Any

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

_IMPORTS = {
    "AFBaseModel": "._pydantic",
    "AFBaseSettings": "._pydantic",
    "Agent": "._agents",
    "AgentRunResponse": "._types",
    "AgentRunResponseUpdate": "._types",
    "AgentThread": "._agents",
    "AITool": "._tools",
    "AIFunction": "._tools",
    "AIContent": "._types",
    "AIContents": "._types",
    "ChatClient": "._clients",
    "ChatClientAgent": "._agents",
    "ChatClientAgentThread": "._agents",
    "ChatClientAgentThreadType": "._agents",
    "ChatClientBase": "._clients",
    "ChatFinishReason": "._types",
    "ChatMessage": "._types",
    "ChatOptions": "._types",
    "ChatResponse": "._types",
    "ChatResponseUpdate": "._types",
    "ChatRole": "._types",
    "ChatToolMode": "._types",
    "DataContent": "._types",
    "EmbeddingGenerator": "._clients",
    "ErrorContent": "._types",
    "FunctionCallContent": "._types",
    "FunctionResultContent": "._types",
    "GeneratedEmbeddings": "._types",
    "HttpsUrl": "._pydantic",
    "InputGuardrail": ".guard_rails",
    "OutputGuardrail": ".guard_rails",
    "SpeechToTextOptions": "._types",
    "StructuredResponse": "._types",
    "TextContent": "._types",
    "TextReasoningContent": "._types",
    "TextToSpeechOptions": "._types",
    "UriContent": "._types",
    "UsageContent": "._types",
    "UsageDetails": "._types",
    "ai_function": "._tools",
    "get_logger": "._logging",
    "use_tool_calling": "._clients",
}


def __getattr__(name: str) -> Any:
    if name == "__version__":
        return __version__
    if name in _IMPORTS:
        submod_name = _IMPORTS[name]
        module = importlib.import_module(submod_name, package=__name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__} has no attribute {name}")


def __dir__() -> list[str]:
    return [*list(_IMPORTS.keys()), "__version__"]
