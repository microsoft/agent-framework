# Copyright (c) Microsoft. All rights reserved.

"""OpenAI Responses-shaped helpers for app-owned Agent Framework hosting."""

import importlib.metadata

from ._parsing import (
    create_response_id,
    messages_from_responses_input,
    responses_from_run,
    responses_from_streaming_run,
    responses_session_id,
    responses_to_run,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "create_response_id",
    "messages_from_responses_input",
    "responses_from_run",
    "responses_from_streaming_run",
    "responses_session_id",
    "responses_to_run",
]
