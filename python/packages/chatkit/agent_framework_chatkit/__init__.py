# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework and ChatKit Integration.

This package provides an integration layer between Microsoft Agent Framework
and OpenAI ChatKit (Python). It mirrors the Agent SDK integration and provides
helpers to convert between Agent Framework and ChatKit types.
"""

import importlib.metadata

from ._converter import ThreadItemConverter, simple_to_agent_input
from ._streaming import stream_agent_response

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "ThreadItemConverter",
    "__version__",
    "simple_to_agent_input",
    "stream_agent_response",
]
