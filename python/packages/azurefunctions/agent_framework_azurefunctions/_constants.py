# Copyright (c) Microsoft. All rights reserved.

"""Constants for Azure Functions Agent Framework integration."""

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
