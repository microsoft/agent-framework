# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :mod:`agent_framework_hosting_teams`.

These tests use small in-process fakes for ``ActivityContext`` and the
SDK's ``HttpStream`` so the channel can be exercised without spinning
up an Azure Bot Service registration. The :class:`microsoft_teams.apps.App`
construction is exercised once via ``skip_auth=True``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from agent_framework_hosting import (
    ChannelRequest,
    HostedRunResult,
)
from microsoft_teams.api.activities.message.message import (
    MessageActivity,
    MessageActivityInput,
)
from microsoft_teams.api.models.entity.citation_entity import CitationEntity

from agent_framework_hosting_teams import (
    TeamsChannel,
    TeamsCitation,
    TeamsFeedbackContext,
    TeamsOutboundContext,
    TeamsOutboundPayload,
    teams_isolation_key,
)
from agent_framework_hosting_teams._channel import (
    _citations_entity,
    _route_for,
    _StarletteCaptureAdapter,
    _update_text,
)

# --------------------------------------------------------------------------- #
# Pure helpers                                                                #
# --------------------------------------------------------------------------- #


def test_teams_isolation_key_uses_teams_prefix() -> None:
    assert teams_isolation_key("conv-123") == "teams:conv-123"


def test_teams_isolation_key_distinct_from_activity_protocol_prefix() -> None:
    """Confirm the prefix does not collide with hosting-activity-protocol's."""
    assert teams_isolation_key("c").split(":", 1)[0] == "teams"


class TestCitationsEntity:
    def test_empty_input_yields_empty_claim_list(self) -> None:
        entity = _citations_entity([])
        assert isinstance(entity, CitationEntity)
        assert entity.citation == []

    def test_single_citation_minimal_fields(self) -> None:
        entity = _citations_entity([TeamsCitation(name="Doc", abstract="One-line summary.")])
        assert entity.citation is not None
        assert len(entity.citation) == 1
        claim = entity.citation[0]
        assert claim.position == 1
        assert claim.appearance.name == "Doc"
        assert claim.appearance.abstract == "One-line summary."
        assert claim.appearance.url is None
        assert claim.appearance.keywords is None

    def test_multiple_citations_get_one_based_positions(self) -> None:
        entity = _citations_entity([
            TeamsCitation(name="A", abstract="a"),
            TeamsCitation(name="B", abstract="b"),
            TeamsCitation(name="C", abstract="c"),
        ])
        assert entity.citation is not None
        assert [c.position for c in entity.citation] == [1, 2, 3]

    def test_optional_fields_are_forwarded(self) -> None:
        entity = _citations_entity([
            TeamsCitation(
                name="N",
                abstract="abs",
                url="https://example.com",
                text="body",
                keywords=("alpha", "beta"),
            )
        ])
        assert entity.citation is not None
        appearance = entity.citation[0].appearance
        assert appearance.url == "https://example.com"
        assert appearance.text == "body"
        assert appearance.keywords == ["alpha", "beta"]


class TestUpdateText:
    def test_collects_text_from_all_text_contents(self) -> None:
        update = MagicMock()
        update.contents = [
            _text_content("hel"),
            _text_content("lo"),
        ]
        assert _update_text(update) == "hello"

    def test_skips_non_text_contents(self) -> None:
        update = MagicMock()
        update.contents = [_text_content("hi"), _non_text_content(), _text_content("!")]
        assert _update_text(update) == "hi!"


def _text_content(text: str) -> Any:
    c = MagicMock()
    c.text = text
    return c


def _non_text_content() -> Any:
    c = MagicMock()
    c.text = None
    return c


# --------------------------------------------------------------------------- #
# Adapter / route wrapper                                                     #
# --------------------------------------------------------------------------- #


class TestStarletteCaptureAdapter:
    def test_register_route_captures_handler(self) -> None:
        adapter = _StarletteCaptureAdapter()

        async def handler(_: Any) -> Any:
            return {"status": 200, "body": None}

        adapter.register_route("POST", "/api/messages", handler)
        assert ("POST", "/api/messages") in adapter.handlers
        assert adapter.handlers[("POST", "/api/messages")] is handler

    def test_register_route_normalizes_method_case(self) -> None:
        adapter = _StarletteCaptureAdapter()

        async def handler(_: Any) -> Any:
            return {"status": 200}

        adapter.register_route("post", "/api/messages", handler)  # type: ignore[arg-type]
        assert ("POST", "/api/messages") in adapter.handlers


class TestRouteFor:
    async def test_translates_json_body_and_status(self) -> None:
        captured: dict[str, Any] = {}

        async def handler(req: Any) -> Any:
            captured["body"] = req["body"]
            captured["headers"] = req["headers"]
            return {"status": 201, "body": {"echoed": req["body"]["x"]}}

        route = _route_for(handler, "/teams/messages", "POST")
        from starlette.applications import Starlette
        from starlette.testclient import TestClient

        app = Starlette(routes=[route])
        client = TestClient(app)
        resp = client.post("/teams/messages", json={"x": "hi"}, headers={"X-Test": "yes"})
        assert resp.status_code == 201
        assert resp.json() == {"echoed": "hi"}
        assert captured["body"] == {"x": "hi"}
        assert captured["headers"]["x-test"] == "yes"

    async def test_empty_body_yields_empty_dict(self) -> None:
        captured: dict[str, Any] = {}

        async def handler(req: Any) -> Any:
            captured["body"] = req["body"]
            return {"status": 200}

        route = _route_for(handler, "/teams/messages", "POST")
        from starlette.applications import Starlette
        from starlette.testclient import TestClient

        client = TestClient(Starlette(routes=[route]))
        resp = client.post("/teams/messages")
        assert resp.status_code == 200
        assert captured["body"] == {}

    async def test_invalid_json_returns_400(self) -> None:
        async def handler(_: Any) -> Any:  # pragma: no cover - never reached
            raise AssertionError("handler must not be called for invalid json")

        route = _route_for(handler, "/teams/messages", "POST")
        from starlette.applications import Starlette
        from starlette.testclient import TestClient

        client = TestClient(Starlette(routes=[route]))
        resp = client.post("/teams/messages", content=b"not-json", headers={"content-type": "application/json"})
        assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Channel construction                                                        #
# --------------------------------------------------------------------------- #


def _make_channel(**kwargs: Any) -> TeamsChannel:
    """Build a TeamsChannel with auth bypassed for tests."""
    return TeamsChannel(skip_auth=True, **kwargs)


def test_default_path_is_teams_messages() -> None:
    channel = _make_channel()
    assert channel.path == "/teams/messages"
    assert channel.name == "teams"


def test_contribute_returns_routes_lifecycle_hooks() -> None:
    channel = _make_channel()
    contribution = channel.contribute(_FakeChannelContext())
    assert len(contribution.routes) == 1
    assert len(contribution.on_startup) == 1
    assert len(contribution.on_shutdown) == 1


def test_constructor_does_not_register_feedback_when_handler_omitted() -> None:
    channel = _make_channel()
    # Internal handler set: only on_message wired
    assert channel._handlers.on_feedback is None  # pyright: ignore[reportPrivateUsage]


def test_constructor_registers_feedback_when_handler_supplied() -> None:
    async def cb(_: TeamsFeedbackContext) -> None:
        pass

    channel = _make_channel(feedback_handler=cb)
    assert channel._handlers.on_feedback is not None  # pyright: ignore[reportPrivateUsage]


# --------------------------------------------------------------------------- #
# End-to-end inbound message dispatch                                         #
# --------------------------------------------------------------------------- #


@dataclass
class _FakeChannelContext:
    """Stand-in for the real :class:`ChannelContext`.

    Records the requests passed to ``run`` / ``deliver_response`` so tests
    can assert the channel built the right :class:`ChannelRequest`.
    """

    runs: list[ChannelRequest] = field(default_factory=list)
    delivered: list[tuple[ChannelRequest, HostedRunResult]] = field(default_factory=list)
    streamed: list[ChannelRequest] = field(default_factory=list)
    target: Any = None
    response_text: str = "agent-reply"

    async def run(self, request: ChannelRequest) -> HostedRunResult:
        self.runs.append(request)
        return HostedRunResult(text=self.response_text)

    def run_stream(self, request: ChannelRequest) -> Any:
        self.streamed.append(request)

        async def _gen() -> Any:
            for chunk in ("hel", "lo"):
                update = MagicMock()
                update.contents = [_text_content(chunk)]
                yield update

        return _gen()

    async def deliver_response(self, request: ChannelRequest, payload: HostedRunResult) -> Any:
        self.delivered.append((request, payload))
        return None


class _FakeStream:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.closed = False

    def emit(self, value: Any) -> None:
        self.chunks.append(value)

    async def close(self) -> None:
        self.closed = True


class _FakeActivityContext:
    """Subset of :class:`ActivityContext` the channel actually touches."""

    def __init__(self, activity: Any) -> None:
        self.activity = activity
        self.sent: list[Any] = []
        self.stream = _FakeStream()

    async def send(self, message: Any) -> Any:
        self.sent.append(message)
        return MagicMock()


def _make_message_activity(text: str = "hello") -> MessageActivity:
    return MessageActivity.model_validate({
        "type": "message",
        "id": "act-1",
        "text": text,
        "channelId": "msteams",
        "serviceUrl": "https://smba.example/",
        "from": {"id": "user-1", "name": "Test User", "aadObjectId": "aad-xyz"},
        "conversation": {"id": "conv-99"},
        "recipient": {"id": "bot-1"},
    })


async def test_on_message_runs_target_and_sends_text() -> None:
    channel = _make_channel()
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity("ping"))
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    # Channel ran the host once and delivered the result.
    assert len(ctx.runs) == 1
    request = ctx.runs[0]
    assert request.channel == "teams"
    assert request.operation == "message.create"
    assert request.input == "ping"
    assert request.session is not None
    assert request.session.isolation_key == "teams:conv-99"
    assert request.identity is not None
    assert request.identity.native_id == "user-1"
    assert request.identity.attributes["aad_object_id"] == "aad-xyz"
    assert request.metadata["service_url"] == "https://smba.example/"

    # Outbound message: plain text.
    assert activity_ctx.sent == ["agent-reply"]
    assert ctx.delivered[0][1].text == "agent-reply"


async def test_on_message_invokes_run_hook_with_protocol_request() -> None:
    seen: dict[str, Any] = {}

    def hook(request: ChannelRequest, **kwargs: Any) -> ChannelRequest:
        seen["protocol_type"] = type(kwargs["protocol_request"]).__name__
        seen["target_passed"] = "target" in kwargs
        return request

    channel = _make_channel(run_hook=hook)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert seen["protocol_type"] == "MessageActivity"
    assert seen["target_passed"] is True


async def test_outbound_transform_can_return_card() -> None:
    from microsoft_teams.cards.core import AdaptiveCard

    card = AdaptiveCard()

    async def to_card(_: TeamsOutboundContext) -> TeamsOutboundPayload:
        return TeamsOutboundPayload(card=card)

    channel = _make_channel(outbound_transform=to_card)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert activity_ctx.sent == [card]


async def test_outbound_transform_with_citations_sends_message_input_with_entities() -> None:
    def with_citations(_: TeamsOutboundContext) -> TeamsOutboundPayload:
        return TeamsOutboundPayload(
            text="see [1]",
            citations=[TeamsCitation(name="Doc", abstract="abs", url="https://x")],
        )

    channel = _make_channel(outbound_transform=with_citations)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert len(activity_ctx.sent) == 1
    sent = activity_ctx.sent[0]
    assert isinstance(sent, MessageActivityInput)
    assert sent.text == "see [1]"
    assert sent.entities is not None
    assert len(sent.entities) == 1
    assert isinstance(sent.entities[0], CitationEntity)


async def test_outbound_transform_returning_text_only_skips_message_input() -> None:
    def to_text(_: TeamsOutboundContext) -> TeamsOutboundPayload:
        return TeamsOutboundPayload(text="custom text")

    channel = _make_channel(outbound_transform=to_text)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert activity_ctx.sent == ["custom text"]


async def test_outbound_transform_drops_send_when_text_none_and_no_card() -> None:
    def to_nothing(_: TeamsOutboundContext) -> TeamsOutboundPayload:
        return TeamsOutboundPayload()

    channel = _make_channel(outbound_transform=to_nothing)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert activity_ctx.sent == []


# --------------------------------------------------------------------------- #
# Streaming                                                                   #
# --------------------------------------------------------------------------- #


async def test_streaming_emits_chunks_through_stream_and_closes() -> None:
    channel = _make_channel(streaming=True)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert activity_ctx.stream.chunks == ["hel", "lo"]
    assert activity_ctx.stream.closed is True
    # delivery still ran with the accumulated text
    assert ctx.delivered[0][1].text == "hello"


async def test_streaming_transform_hook_can_drop_updates() -> None:
    def drop_first(_update: Any) -> Any:
        # First time returns None, then yields the update unchanged
        if not getattr(drop_first, "called", False):
            drop_first.called = True  # type: ignore[attr-defined]
            return None
        return _update

    channel = _make_channel(streaming=True, stream_transform_hook=drop_first)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    activity_ctx = _FakeActivityContext(_make_message_activity())
    await channel._on_message_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    # First chunk dropped → only "lo" emitted
    assert activity_ctx.stream.chunks == ["lo"]


# --------------------------------------------------------------------------- #
# Feedback handler                                                            #
# --------------------------------------------------------------------------- #


async def test_feedback_handler_receives_typed_context() -> None:
    received: list[TeamsFeedbackContext] = []

    async def handler(c: TeamsFeedbackContext) -> None:
        received.append(c)

    channel = _make_channel(feedback_handler=handler)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    invoke = MagicMock()
    invoke.from_ = MagicMock(id="user-1", name="Tester", aad_object_id="aad-1")
    invoke.conversation = MagicMock(id="conv-1")
    invoke.channel_id = "msteams"
    invoke.reply_to_id = "msg-42"
    invoke.value.action_value.reaction = "like"
    invoke.value.action_value.feedback = "great answer"

    activity_ctx = _FakeActivityContext(invoke)
    await channel._on_feedback_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert len(received) == 1
    fb = received[0]
    assert fb.rating == "like"
    assert fb.feedback == "great answer"
    assert fb.reply_to_id == "msg-42"
    assert fb.identity.native_id == "user-1"
    assert fb.identity.attributes["aad_object_id"] == "aad-1"


async def test_feedback_handler_supports_sync_callable() -> None:
    received: list[TeamsFeedbackContext] = []

    def sync_handler(c: TeamsFeedbackContext) -> None:
        received.append(c)

    channel = _make_channel(feedback_handler=sync_handler)
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    invoke = MagicMock()
    invoke.from_ = MagicMock(id="user-2", name="X", aad_object_id=None)
    invoke.conversation = MagicMock(id="c")
    invoke.channel_id = "msteams"
    invoke.reply_to_id = None
    invoke.value.action_value.reaction = "dislike"
    invoke.value.action_value.feedback = None

    activity_ctx = _FakeActivityContext(invoke)
    await channel._on_feedback_activity(activity_ctx)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]

    assert len(received) == 1
    assert received[0].rating == "dislike"
    assert received[0].feedback is None


# --------------------------------------------------------------------------- #
# Identity                                                                    #
# --------------------------------------------------------------------------- #


def test_identity_from_activity_drops_none_attributes() -> None:
    channel = _make_channel()
    activity = _make_message_activity()
    identity = channel._identity_from_activity(activity)  # pyright: ignore[reportPrivateUsage]
    assert identity.channel == "teams"
    assert identity.native_id == "user-1"
    # All present fields kept; the helper drops None values.
    assert "name" in identity.attributes
    assert "aad_object_id" in identity.attributes
    assert "conversation_id" in identity.attributes
    assert "channel_id" in identity.attributes


# --------------------------------------------------------------------------- #
# Lifecycle                                                                   #
# --------------------------------------------------------------------------- #


async def test_on_startup_calls_app_initialize_idempotently() -> None:
    channel = _make_channel()
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    # Patch app.initialize to count calls
    initialize_mock = AsyncMock()
    channel._app.initialize = initialize_mock  # type: ignore[method-assign]
    # Force not-initialized so startup would call it
    channel._app._initialized = False  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]

    await channel._on_startup()  # pyright: ignore[reportPrivateUsage]
    initialize_mock.assert_awaited_once()


async def test_on_startup_skips_initialize_when_already_initialized() -> None:
    channel = _make_channel()
    ctx = _FakeChannelContext()
    channel.contribute(ctx)  # type: ignore[arg-type]

    initialize_mock = AsyncMock()
    channel._app.initialize = initialize_mock  # type: ignore[method-assign]
    channel._app._initialized = True  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]

    await channel._on_startup()  # pyright: ignore[reportPrivateUsage]
    initialize_mock.assert_not_awaited()
