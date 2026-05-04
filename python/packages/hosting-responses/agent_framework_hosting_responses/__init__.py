# Copyright (c) Microsoft. All rights reserved.

"""OpenAI Responses-shaped channel for ``agent-framework-hosting``."""

import importlib.metadata

from ._channel import ResponsesChannel
from ._parsing import (
    messages_from_responses_input,
    parse_response_target,
    parse_responses_identity,
    parse_responses_request,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "ResponsesChannel",
    "__version__",
    "messages_from_responses_input",
    "parse_response_target",
    "parse_responses_identity",
    "parse_responses_request",
]
