# Copyright (c) Microsoft. All rights reserved.

import importlib
import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

_IMPORTS = {
    "get_logger": "._logging",
    "AITool": "._tools",
    "ai_function": "._tools",
    "AIContent": "._types",
    "AIContents": "._types",
    "TextContent": "._types",
    "TextReasoningContent": "._types",
    "DataContent": "._types",
    "UriContent": "._types",
    "UsageContent": "._types",
    "UsageDetails": "._types",
    "FunctionCallContent": "._types",
    "FunctionResultContent": "._types",
    "ChatFinishReason": "._types",
    "ChatMessage": "._types",
    "ChatResponse": "._types",
    "StructuredResponse": "._types",
    "ChatResponseUpdate": "._types",
    "ChatRole": "._types",
    "ErrorContent": "._types",
    "GeneratedEmbeddings": "._types",
    "ChatOptions": "._types",
    "ChatToolMode": "._types",
    "ChatClient": "._clients",
    "EmbeddingGenerator": "._clients",
    "InputGuardrail": ".guard_rails",
    "OutputGuardrail": ".guard_rails",
}


def __getattr__(name: str):
    if name == "__version__":
        return __version__
    if name in _IMPORTS:
        submod_name = _IMPORTS[name]
        module = importlib.import_module(submod_name, package=__name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__} has no attribute {name}")


def __dir__():
    return [*list(_IMPORTS.keys()), "__version__"]
