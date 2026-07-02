# Copyright (c) Microsoft. All rights reserved.

"""OpenAI Responses-shaped channel for ``agent-framework-hosting``."""

import importlib.metadata

from ._channel import ResponsesChannel
from ._parsing import (
    create_response_id,
    messages_from_responses_input,
    parse_responses_identity,
    parse_responses_request,
    responses_from_run,
    responses_session_id,
    responses_stream_events_from_run,
    responses_to_run,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "ResponsesChannel",
    "__version__",
    "create_response_id",
    "messages_from_responses_input",
    "parse_responses_identity",
    "parse_responses_request",
    "responses_from_run",
    "responses_session_id",
    "responses_stream_events_from_run",
    "responses_to_run",
]
