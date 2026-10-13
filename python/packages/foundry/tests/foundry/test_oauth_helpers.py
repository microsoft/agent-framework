# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from collections.abc import AsyncIterable, Awaitable
from typing import Any, Literal, overload
from unittest.mock import MagicMock

import pytest
from agent_framework import (
    AgentExecutor,
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
    WorkflowBuilder,
)

from agent_framework_foundry._oauth_helpers import (
    _validate_consent_link,
    parse_oauth_consent_output_items,
    try_parse_oauth_consent_event,
)

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


# region consent request id


def _make_output_item(*, item_id: Any = "oauth-item-1", consent_link: str = "https://consent.example.com/auth") -> Any:
    """Create a mock non-streaming ``oauth_consent_request`` output item."""
    item = MagicMock()
    item.type = "oauth_consent_request"
    item.consent_link = consent_link
    item.id = item_id
    return item


def test_output_item_added_keeps_provider_item_id() -> None:
    """The consent content carries the provider item id, as user-input requests need one."""
    update = try_parse_oauth_consent_event(_make_output_item_event(item_id="oauth-item-42"), "test-model")

    assert update is not None
    assert [c.id for c in update.contents if c.type == "oauth_consent_request"] == ["oauth-item-42"]


def test_top_level_consent_requested_event_keeps_event_id() -> None:
    """A top-level ``response.oauth_consent_requested`` event keeps its id on the content."""
    update = try_parse_oauth_consent_event(_make_top_level_event(event_id="consent-event-7"), "test-model")

    assert update is not None
    assert [c.id for c in update.contents if c.type == "oauth_consent_request"] == ["consent-event-7"]


def test_non_streaming_output_item_keeps_provider_item_id() -> None:
    """Non-streaming output items keep the provider item id on the consent content."""
    contents = parse_oauth_consent_output_items([_make_output_item(item_id="oauth-item-9")])

    assert len(contents) == 1
    assert contents[0].type == "oauth_consent_request"
    assert contents[0].user_input_request is True
    assert contents[0].id == "oauth-item-9"


def test_consent_content_without_string_id_has_no_id() -> None:
    """A provider item without a usable id does not get a made-up one."""
    contents = parse_oauth_consent_output_items([_make_output_item(item_id=None)])

    assert len(contents) == 1
    assert contents[0].id is None


class _ConsentEmittingAgent(BaseAgent):
    """Agent that returns the consent content parsed from a Foundry output item."""

    def __init__(self, *, item_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._item_id = item_id

    def _consent_contents(self) -> list[Content]:
        return parse_oauth_consent_output_items([_make_output_item(item_id=self._item_id)])

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        contents = self._consent_contents()

        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=contents, role="assistant")

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", contents)])

        return _run()


@pytest.mark.parametrize("stream", [False, True])
async def test_workflow_pauses_for_oauth_consent_request(stream: bool) -> None:
    """In a workflow, the consent request becomes a ``request_info`` event keyed by the provider item id."""
    agent = _ConsentEmittingAgent(item_id="oauth-item-wf", id="consent_agent", name="ConsentAgent")
    workflow = WorkflowBuilder(start_executor=AgentExecutor(agent, id="consent_exec")).build()

    if stream:
        events = [event async for event in workflow.run("connect my calendar", stream=True)]
    else:
        events = list(await workflow.run("connect my calendar"))

    request_info_events = [event for event in events if event.type == "request_info"]
    assert len(request_info_events) == 1
    assert request_info_events[0].request_id == "oauth-item-wf"


# endregion
