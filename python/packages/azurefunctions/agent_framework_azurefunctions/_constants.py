# Copyright (c) Microsoft. All rights reserved.

"""Constants for Azure Functions Agent Framework integration.

This module contains runtime configuration constants (polling, MIME types, headers)
and API response field names.
"""

from typing import Final

# Supported request/response formats and MIME types
REQUEST_RESPONSE_FORMAT_JSON: str = "json"
REQUEST_RESPONSE_FORMAT_TEXT: str = "text"
MIMETYPE_APPLICATION_JSON: str = "application/json"
MIMETYPE_TEXT_PLAIN: str = "text/plain"

# Field and header names
THREAD_ID_FIELD: str = "thread_id"
THREAD_ID_HEADER: str = "x-ms-thread-id"
WAIT_FOR_RESPONSE_FIELD: str = "wait_for_response"
WAIT_FOR_RESPONSE_HEADER: str = "x-ms-wait-for-response"

# Polling configuration
DEFAULT_MAX_POLL_RETRIES: int = 30
DEFAULT_POLL_INTERVAL_SECONDS: float = 1.0


class ApiResponseFields:
    """Field names for HTTP API responses (not part of persisted schema).

    These are used in try_get_agent_response() for backward compatibility
    with the HTTP API response format.
    """

    CONTENT: Final[str] = "content"
    MESSAGE_COUNT: Final[str] = "message_count"
    CORRELATION_ID: Final[str] = "correlationId"
