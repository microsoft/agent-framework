# Copyright (c) Microsoft. All rights reserved.

import importlib
import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

_IMPORTS = {
    "get_logger": "._logging",
    "BaseContent": ".contents.base_content",
    "TextContent": ".contents.text_content",
    "FunctionCallContent": ".contents.function_call_content",
    "FunctionResultContent": ".contents.function_result_content",
    "StreamingContentMixin": ".contents.streaming_content_mixin",
    "StreamingTextContent": ".contents.streaming_text_content",
    "Status": ".contents.status",
    "FinishReason": ".contents.finish_reason",
    "AuthorRole": ".contents.author_role",
    "ContentTypes": ".contents.const",
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
