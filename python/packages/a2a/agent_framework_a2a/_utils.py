# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import re
from urllib.parse import unquote

# Key in ``SendMessageRequest.metadata`` that carries forwarded ``function_invocation_kwargs`` and
# ``client_kwargs``.
AGENT_FRAMEWORK_METADATA_KEY = "agent_framework"

URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;,]+(?:;[^;,=]+=[^;,]+)*);base64,(?P<base64_data>[A-Za-z0-9+/=]*)\Z")


def get_uri_data(uri: str) -> str:
    """Extracts the base64-encoded data from a data URI.

    Args:
        uri: The data URI to parse.

    Returns:
        The base64-encoded data part of the URI.

    Raises:
        ValueError: If the URI format is invalid.
    """
    metadata, separator, payload = uri.partition(",")
    if not separator or not URI_PATTERN.match(f"{metadata},"):
        raise ValueError(f"Invalid data URI format: {uri}")

    match = URI_PATTERN.match(f"{metadata},{unquote(payload)}")
    if not match:
        raise ValueError(f"Invalid data URI format: {uri}")

    return match.group("base64_data")
