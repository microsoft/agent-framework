# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from collections.abc import Iterable
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

    return ChatResponseUpdate(
        contents=_oauth_consent_contents(raw_item, consent_link),
        role="assistant",
        model=model,
        raw_representation=event,
    )


def parse_oauth_consent_output_items(output: Iterable[Any] | None) -> list[Content]:
    """Parse ``oauth_consent_request`` items from a non-streaming response's ``output``.

    Non-streaming responses carry the consent request as an output item instead of
    a stream event, so it has to be surfaced from the completed response as well.
    """
    contents: list[Content] = []
    for item in output or ():
        if getattr(item, "type", None) == "oauth_consent_request":
            contents.extend(_oauth_consent_contents(item, getattr(item, "consent_link", None) or ""))
    return contents


def _oauth_consent_contents(raw_item: Any, consent_link: str) -> list[Content]:
    """Build the consent content for an oauth_consent_request item, validating its link."""
    item_id = getattr(raw_item, "id", "<unknown>")

    if consent_link:
        consent_link = _validate_consent_link(consent_link, item_id)

    if consent_link:
        return [
            Content.from_oauth_consent_request(
                consent_link=consent_link,
                raw_representation=raw_item,
            )
        ]
    logger.warning(
        "Received oauth_consent_request output without valid consent_link (item id=%s)",
        item_id,
    )
    return []
