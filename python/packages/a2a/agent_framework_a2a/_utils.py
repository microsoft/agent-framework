# Copyright (c) Microsoft. All rights reserved.

import re

URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$")


def get_uri_data(uri: str) -> str:
    """Extracts the base64-encoded data from a data URI.

    Args:
        uri: The data URI to parse.

    Returns:
        The base64-encoded data part of the URI.

    Raises:
        ValueError: If the URI format is invalid.
    """
    match = URI_PATTERN.match(uri)
    if not match:
        raise ValueError(f"Invalid data URI format: {uri}")

    return match.group("base64_data")
