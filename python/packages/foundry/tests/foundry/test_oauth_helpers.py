# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_framework_foundry._oauth_helpers import _validate_consent_link, try_parse_oauth_consent_event

# region _validate_consent_link tests


def test_validate_consent_link_accepts_valid_https() -> None:
    """A valid HTTPS URL with a netloc passes validation."""
    link = "https://consent.example.com/auth?code=123"
    assert _validate_consent_link(link, "item-1") == link


def test_validate_consent_link_rejects_http(caplog: pytest.LogCaptureFixture) -> None:
    """An HTTP link is rejected and a warning is logged."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link("http://insecure.example.com/login", "item-2")
    assert result == ""
    assert "non-HTTPS" in caplog.text
    assert "item-2" in caplog.text


def test_validate_consent_link_rejects_empty_netloc(caplog: pytest.LogCaptureFixture) -> None:
    """An HTTPS URL with an empty netloc (e.g. https:///path) is rejected."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link("https:///path", "item-3")
    assert result == ""
    assert "non-HTTPS" in caplog.text
    assert "item-3" in caplog.text


def test_validate_consent_link_rejects_non_url(caplog: pytest.LogCaptureFixture) -> None:
    """A non-URL string is rejected."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link("not-a-url", "item-4")
    assert result == ""


# endregion

# region try_parse_oauth_consent_event tests


def _make_output_item_event(
    *,
    item_type: str = "oauth_consent_request",
    consent_link: Any = "https://consent.example.com/auth",
    item_id: str = "oauth-item-1",
) -> MagicMock:
    """Create a mock ``response.output_item.added`` event."""
    event = MagicMock()
    event.type = "response.output_item.added"
    item = MagicMock()
    item.type = item_type
    item.consent_link = consent_link
    item.id = item_id
    event.item = item
    return event


def _make_top_level_event(
    *,
    consent_link: Any = "https://consent.example.com/authorize",
    event_id: str = "consent-event-1",
) -> MagicMock:
    """Create a mock ``response.oauth_consent_requested`` event."""
    event = MagicMock()
    event.type = "response.oauth_consent_requested"
    event.consent_link = consent_link
    event.id = event_id
    return event


def test_returns_none_for_unrelated_event() -> None:
    """An event with a non-oauth type returns None."""
    event = MagicMock()
    event.type = "response.output_text.delta"
    assert try_parse_oauth_consent_event(event, "model-x") is None


def test_returns_none_for_event_without_type() -> None:
    """An event object missing a 'type' attribute returns None."""
    event = object()  # no type attribute
    assert try_parse_oauth_consent_event(event, "model-x") is None


def test_parses_output_item_added_with_valid_link() -> None:
    """A response.output_item.added event with a valid HTTPS link produces Content."""
    event = _make_output_item_event()
    update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    assert update.role == "assistant"
    assert update.model == "test-model"
    assert update.raw_representation is event
    consent = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent) == 1
    assert consent[0].consent_link == "https://consent.example.com/auth"


def test_parses_top_level_consent_requested_event() -> None:
    """A response.oauth_consent_requested event produces Content."""
    event = _make_top_level_event()
    update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    consent = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent) == 1
    assert consent[0].consent_link == "https://consent.example.com/authorize"


def test_empty_contents_for_non_https_link(caplog: pytest.LogCaptureFixture) -> None:
    """A non-HTTPS consent_link produces an update with empty contents and logs a warning."""
    event = _make_output_item_event(consent_link="http://bad.example.com/login", item_id="item-http")
    with caplog.at_level(logging.WARNING):
        update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    assert len(update.contents) == 0
    assert "non-HTTPS" in caplog.text


def test_empty_contents_for_missing_consent_link(caplog: pytest.LogCaptureFixture) -> None:
    """A None consent_link produces an update with empty contents and logs a warning."""
    event = _make_output_item_event(consent_link=None, item_id="item-none")
    with caplog.at_level(logging.WARNING):
        update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    assert len(update.contents) == 0
    assert "without valid consent_link" in caplog.text


def test_empty_contents_for_empty_string_consent_link(caplog: pytest.LogCaptureFixture) -> None:
    """An empty-string consent_link produces an update with empty contents and logs a warning."""
    event = _make_output_item_event(consent_link="", item_id="item-empty")
    with caplog.at_level(logging.WARNING):
        update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    assert len(update.contents) == 0
    assert "without valid consent_link" in caplog.text


def test_empty_contents_for_https_empty_netloc(caplog: pytest.LogCaptureFixture) -> None:
    """An HTTPS URL with empty netloc (https:///path) is rejected."""
    event = _make_output_item_event(consent_link="https:///path", item_id="item-no-netloc")
    with caplog.at_level(logging.WARNING):
        update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    assert len(update.contents) == 0
    assert "non-HTTPS" in caplog.text


# endregion
