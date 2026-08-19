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


def test_validate_consent_link_rejects_malformed_authority(caplog: pytest.LogCaptureFixture) -> None:
    """A malformed authority makes urlparse raise ValueError; it must be rejected, not propagated."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link("https://[broken", "item-5")
    assert result == ""
    assert "malformed" in caplog.text
    assert "item-5" in caplog.text


def test_validate_consent_link_rejects_netloc_without_host(caplog: pytest.LogCaptureFixture) -> None:
    """``https://@`` has a netloc but no host, so it is rejected."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link("https://@", "item-6")
    assert result == ""
    assert "non-HTTPS" in caplog.text


@pytest.mark.parametrize(
    "consent_link",
    [
        "https://consent.example.com:bad/obo",
        "https://consent.example.com:99999/obo",
    ],
)
def test_validate_consent_link_rejects_invalid_port(consent_link: str, caplog: pytest.LogCaptureFixture) -> None:
    """``urlparse`` only validates the port when it is read, so an invalid port must be caught."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link(consent_link, "item-7")
    assert result == ""
    assert "malformed" in caplog.text


@pytest.mark.parametrize(
    "consent_link",
    [
        "https://cons|ent.example.com/obo",
        "https://exa^mple.com/obo",
    ],
)
def test_validate_consent_link_rejects_invalid_host_characters(
    consent_link: str, caplog: pytest.LogCaptureFixture
) -> None:
    """``urlparse`` reports a hostname for values that no URL client can resolve."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link(consent_link, "item-8")
    assert result == ""
    assert "invalid consent_link host" in caplog.text


@pytest.mark.parametrize(
    "consent_link",
    [
        "https://cons\tent.example.com/obo",
        "https://consent.example.com/obo\n",
    ],
)
def test_validate_consent_link_rejects_control_characters(consent_link: str, caplog: pytest.LogCaptureFixture) -> None:
    """``urlparse`` strips tab and newline, so they must be rejected before parsing."""
    with caplog.at_level(logging.WARNING):
        result = _validate_consent_link(consent_link, "item-10")
    assert result == ""
    assert "control characters" in caplog.text


@pytest.mark.parametrize(
    "consent_link",
    [
        "https://consent.example.com/obo",
        "https://consent.example.com:8443/obo",
        "https://[2001:db8::1]/obo",
    ],
)
def test_validate_consent_link_accepts_usable_links(consent_link: str) -> None:
    """Valid ports and IPv6 literals stay usable and must not be dropped."""
    assert _validate_consent_link(consent_link, "item-9") == consent_link


# endregion

# region try_parse_oauth_consent_event tests


def _make_output_item_event(
    *,
    item_type: str = "oauth_consent_request",
    consent_link: Any = "https://consent.example.com/auth",
    item_id: str = "oauth-item-1",
    server_label: Any = "obo-mcp",
) -> MagicMock:
    """Create a mock ``response.output_item.added`` event."""
    event = MagicMock()
    event.type = "response.output_item.added"
    item = MagicMock()
    item.type = item_type
    item.consent_link = consent_link
    item.id = item_id
    item.server_label = server_label
    event.item = item
    return event


def _make_top_level_event(
    *,
    consent_link: Any = "https://consent.example.com/authorize",
    event_id: str = "consent-event-1",
    server_label: Any = "obo-mcp",
) -> MagicMock:
    """Create a mock ``response.oauth_consent_requested`` event."""
    event = MagicMock()
    event.type = "response.oauth_consent_requested"
    event.consent_link = consent_link
    event.id = event_id
    event.server_label = server_label
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


@pytest.mark.parametrize(
    ("consent_link", "expected_link", "expected_log"),
    [
        pytest.param("http://bad.example.com/login", "http://bad.example.com/login", "non-HTTPS", id="non-https"),
        pytest.param(None, "", "without valid consent_link", id="missing"),
        pytest.param("", "", "without valid consent_link", id="empty-string"),
        pytest.param("https:///path", "https:///path", "non-HTTPS", id="empty-netloc"),
        pytest.param("https://[broken", "https://[broken", "malformed", id="malformed-authority"),
    ],
)
def test_unusable_consent_link_is_still_surfaced(
    consent_link: str | None,
    expected_link: str,
    expected_log: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unusable link is logged but still surfaced so the host can fail the response.

    Dropping the content here would leave the host with nothing to record, so a turn that
    cannot proceed without consent would be reported as a silent success.
    """
    event = _make_output_item_event(consent_link=consent_link, item_id="item-bad")
    with caplog.at_level(logging.WARNING):
        update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    consent = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert len(consent) == 1
    assert consent[0].consent_link == expected_link
    assert expected_log in caplog.text


def test_server_label_is_preserved_in_additional_properties() -> None:
    """The upstream item's server_label is carried forward so hosting can re-emit it."""
    event = _make_output_item_event(server_label="work-iq-connection")
    update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    consent = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert consent[0].additional_properties["server_label"] == "work-iq-connection"


def test_top_level_event_server_label_is_preserved() -> None:
    """The top-level consent event's server_label is carried forward too."""
    event = _make_top_level_event(server_label="work-iq-connection")
    update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    consent = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert consent[0].additional_properties["server_label"] == "work-iq-connection"


def test_missing_server_label_leaves_additional_properties_empty() -> None:
    """A non-string server_label is ignored rather than stored."""
    event = _make_output_item_event(server_label=None)
    update = try_parse_oauth_consent_event(event, "test-model")

    assert update is not None
    consent = [c for c in update.contents if c.type == "oauth_consent_request"]
    assert "server_label" not in consent[0].additional_properties


# endregion
