# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from agent_framework import ChatResponseUpdate, Content

logger = logging.getLogger(__name__)


def _validate_consent_link(consent_link: str, item_id: str) -> str:
    """Validate a consent link is HTTPS with a valid netloc.

    Returns the link unchanged if valid, or an empty string if not.
    """
    parsed = urlparse(consent_link)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        logger.warning(
            "Skipping oauth_consent_request with non-HTTPS consent_link (item id=%s)",
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
        contents.append(
            Content.from_oauth_consent_request(
                consent_link=consent_link,
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
