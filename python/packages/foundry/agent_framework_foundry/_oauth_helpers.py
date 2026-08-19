# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from typing import Any

from agent_framework import ChatResponseUpdate, Content
from agent_framework._oauth import validate_oauth_consent_link

logger = logging.getLogger(__name__)


def _validate_consent_link(consent_link: str, item_id: str) -> str:
    """Validate a consent link is HTTPS with a valid host and port.

    Thin wrapper over the shared core validator that keeps this module's empty-string
    contract. The rules live in ``agent_framework._oauth`` so the parser here and the
    Foundry hosting layer that re-emits the link cannot drift apart.
    """
    return validate_oauth_consent_link(consent_link, item_id=item_id) or ""


def try_parse_oauth_consent_event(event: Any, model: str) -> ChatResponseUpdate | None:
    """Parse an oauth_consent_request from a streaming event, if present.

    Returns a ``ChatResponseUpdate`` when *event* is a
    ``response.output_item.added`` carrying an ``oauth_consent_request`` item
    or a top-level ``response.oauth_consent_requested`` event,
    or ``None`` so the caller can fall through to the base implementation.

    The consent request is surfaced even when its link is missing or unusable, so that a
    turn which cannot proceed is never reported as a silent success. Link validation is
    applied for diagnostics here and enforced by the host that renders the link.
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
        # Validation here is diagnostic only. The provider has signalled that the turn
        # cannot proceed without consent, so the request is always surfaced: dropping it
        # would let a blocked turn finish as a silent success. The host re-validates and
        # is the single authority on whether a link is renderable, failing the response
        # when it is not.
        _validate_consent_link(consent_link, item_id)
    else:
        logger.warning(
            "Received oauth_consent_request output without valid consent_link (item id=%s)",
            item_id,
        )

    # ``server_label`` identifies the MCP server that needs consent and is required by
    # downstream Responses output items. It is copied into ``additional_properties``
    # because ``raw_representation`` is provider specific and does not survive a
    # session round trip.
    server_label = getattr(raw_item, "server_label", None)
    additional_properties = {"server_label": server_label} if isinstance(server_label, str) and server_label else None
    contents: list[Content] = [
        Content.from_oauth_consent_request(
            consent_link=consent_link,
            additional_properties=additional_properties,
            raw_representation=raw_item,
        )
    ]

    return ChatResponseUpdate(
        contents=contents,
        role="assistant",
        model=model,
        raw_representation=event,
    )
