# Copyright (c) Microsoft. All rights reserved.

"""Constants used across the Azure Functions agent framework."""

# Response format constants
RESPONSE_FORMAT_JSON: str = "json"
RESPONSE_FORMAT_TEXT: str = "text"

# Field and header names
THREAD_ID_FIELD: str = "thread_id"
WAIT_FOR_RESPONSE_FIELD: str = "wait_for_response"
WAIT_FOR_RESPONSE_HEADER: str = "x-ms-wait-for-response"

# Polling configuration
DEFAULT_MAX_POLL_RETRIES: int = 30
DEFAULT_POLL_INTERVAL_SECONDS: float = 1.0
