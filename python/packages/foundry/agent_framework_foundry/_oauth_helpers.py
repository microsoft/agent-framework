# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from agent_framework import ChatResponseUpdate, Content

logger = logging.getLogger(__name__)

# Characters allowed in a registered host name, and in the bracketed IPv6 form that
# ``urlparse`` reports with its brackets already stripped.
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9._~%-]+$")
_IPV6_HOST_PATTERN = re.compile(r"^[0-9A-Fa-f:.%-]+$")


def _is_valid_consent_host(hostname: str) -> bool:
    """Return whether *hostname* is syntactically usable by a standard URL client.

    ``urlparse`` does not reject hosts that contain illegal characters, so values such as
    ``exa mple.com`` are reported as a hostname even though no client can resolve them.
    """
    pattern = _IPV6_HOST_PATTERN if ":" in hostname else _HOST_PATTERN
    return bool(pattern.match(hostname))


def _validate_consent_link(consent_link: str, item_id: str) -> str:
    """Validate a consent link is HTTPS with a valid host and port.

    Returns the link unchanged if valid, or an empty string if not. ``urlparse`` raises
    ``ValueError`` for malformed authorities (for example ``https://[broken``) and for
    invalid ports, but only when ``port`` is read, so it is accessed here. A non-empty
    ``netloc`` is not sufficient on its own (``https://@`` has one but no host), and a
    non-empty ``hostname`` is not either (``https://exa mple.com`` reports one).
    """
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in consent_link):
        # ``urlparse`` silently strips tab and newline, which would let a link carrying
        # control characters through even though it is not safe to render or log.
        logger.warning(
            "Skipping oauth_consent_request with whitespace or control characters in consent_link (item id=%s)",
            item_id,
        )
        return ""
    try:
        parsed = urlparse(consent_link)
        hostname = parsed.hostname
        # Reading ``port`` is what validates it; ``https://host:bad`` raises here.
        _ = parsed.port
    except ValueError:
        logger.warning(
            "Skipping oauth_consent_request with malformed consent_link (item id=%s)",
            item_id,
        )
        return ""
    if parsed.scheme.lower() != "https" or not hostname:
        logger.warning(
            "Skipping oauth_consent_request with non-HTTPS consent_link (item id=%s)",
            item_id,
        )
        return ""
    if not _is_valid_consent_host(hostname):
        logger.warning(
            "Skipping oauth_consent_request with an invalid consent_link host (item id=%s)",
            item_id,
        )
        return ""
    return consent_link


def try_parse_oauth_consent_event(event: Any, model: str) -> ChatResponseUpdate | None:
    """Parse an oauth_consent_request from a streaming event, if present.

    Returns a ``ChatResponseUpdate`` when *event* is a
    ``response.output_item.added`` carrying an ``oauth_consent_request`` item
    or a top-level ``response.oauth_consent_requested`` event,
    or ``None`` so the caller can fall through to the base implementation.
    """
    consent_link: str = ""
    raw_item: Any = None

    event_type = getattr(event, "type", None)

    if event_type == "response.output_item.added" and getattr(event.item, "type", None) == "oauth_consent_request":
        raw_item = event.item
        consent_link = getattr(raw_item, "consent_link", None) or ""
    elif event_type == "response.oauth_consent_requested":
        raw_item = event
        consent_link = getattr(event, "consent_link", None) or ""
    else:
        return None

    item_id = getattr(raw_item, "id", "<unknown>")

    if consent_link:
        consent_link = _validate_consent_link(consent_link, item_id)

    contents: list[Content] = []
    if consent_link:
        # ``server_label`` identifies the MCP server that needs consent and is required by
        # downstream Responses output items. It is copied into ``additional_properties``
        # because ``raw_representation`` is provider specific and does not survive a
        # session round trip.
        server_label = getattr(raw_item, "server_label", None)
        additional_properties = (
            {"server_label": server_label} if isinstance(server_label, str) and server_label else None
        )
        contents.append(
            Content.from_oauth_consent_request(
                consent_link=consent_link,
                additional_properties=additional_properties,
                raw_representation=raw_item,
            )
        )
    else:
        logger.warning(
            "Received oauth_consent_request output without valid consent_link (item id=%s)",
            item_id,
        )

    return ChatResponseUpdate(
        contents=contents,
        role="assistant",
        model=model,
        raw_representation=event,
    )
