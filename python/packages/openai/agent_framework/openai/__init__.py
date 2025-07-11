# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_completion import OpenAIChatCompletion, OpenAIChatCompletionBase

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "OpenAIChatCompletion",
    "OpenAIChatCompletionBase",
    "__version__",
]
