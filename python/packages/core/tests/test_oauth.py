# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework._oauth import validate_oauth_consent_link


@pytest.mark.parametrize(
    "link",
    [
        "https://login.example.com/consent",
        "https://login.example.com:8443/consent?state=abc#frag",
        "https://192.0.2.10/consent",
        "https://[2001:db8::1]:8443/consent",
        "HTTPS://login.example.com/consent",
    ],
)
def test_usable_links_are_returned_unchanged(link: str) -> None:
    assert validate_oauth_consent_link(link) == link


@pytest.mark.parametrize(
    ("link", "reason"),
    [
        (None, "missing"),
        ("", "empty"),
        ("   ", "whitespace only"),
        ("http://login.example.com/consent", "non-HTTPS scheme"),
        ("ftp://login.example.com/consent", "non-HTTPS scheme"),
        ("/consent", "relative, so no scheme or host"),
        ("https://", "no host"),
        ("https://@", "netloc present but no host"),
        ("https://[broken", "malformed authority, urlparse raises"),
        ("https://login.example.com:bad/consent", "port only validated when read"),
        ("https://login.example.com:99999/consent", "port out of range"),
        ("https://exa mple.com/consent", "space in host, unresolvable"),
        ("https://cons|ent.example.com/", "illegal character in host"),
        ("https://login.example.com/consent\n", "trailing newline, silently stripped by urlparse"),
        ("https://login.example.com/\tconsent", "embedded tab, silently stripped by urlparse"),
    ],
)
def test_unusable_links_are_rejected(link: str | None, reason: str) -> None:
    assert validate_oauth_consent_link(link) is None, reason


def test_rejection_is_logged_with_the_item_id(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert validate_oauth_consent_link("http://login.example.com", item_id="item-5") is None
    assert "non-HTTPS" in caplog.text
    assert "item-5" in caplog.text


def test_rejection_without_an_item_id_still_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert validate_oauth_consent_link("http://login.example.com") is None
    assert "non-HTTPS" in caplog.text
