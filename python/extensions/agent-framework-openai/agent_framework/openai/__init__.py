# Copyright (c) Microsoft. All rights reserved.
import importlib.metadata

from ._openai_chat_completion_base import OpenAIChatCompletionBase
from ._openai_chat_completion import OpenAIChatCompletion

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode
    
__all__ = [
    "OpenAIChatCompletionBase",
    "OpenAIChatCompletion",
]
