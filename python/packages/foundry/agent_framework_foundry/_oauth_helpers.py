# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from agent_framework import ChatResponseUpdate, Content

logger = logging.getLogger(__name__)


def try_parse_oauth_consent_event(event: Any, model: str) -> ChatResponseUpdate | None:
    """Parse an oauth_consent_request from a streaming event, if present.

    Returns a ``ChatResponseUpdate`` when *event* is a
    ``response.output_item.added`` carrying an ``oauth_consent_request`` item,
    or ``None`` so the caller can fall through to the base implementation.
    """
    if event.type != "response.output_item.added" or getattr(event.item, "type", None) != "oauth_consent_request":
        return None

    item = event.item
    consent_link = getattr(item, "consent_link", None) or ""

    if consent_link:
        parsed = urlparse(consent_link)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            logger.warning(
                "Skipping oauth_consent_request with non-HTTPS consent_link (item id=%s)",
                getattr(item, "id", "<unknown>"),
            )
            consent_link = ""

    contents: list[Content] = []
    if consent_link:
        contents.append(
            Content.from_oauth_consent_request(
                consent_link=consent_link,
                raw_representation=item,
            )
        )
    else:
        logger.warning(
            "Received oauth_consent_request output without valid consent_link (item id=%s)",
            getattr(item, "id", "<unknown>"),
        )

    return ChatResponseUpdate(
        contents=contents,
        role="assistant",
        model=model,
        raw_representation=event,
    )
