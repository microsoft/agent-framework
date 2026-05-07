# Copyright (c) Microsoft. All rights reserved.

"""Tests for the channel-neutral envelope types in :mod:`agent_framework_hosting._types`."""

from __future__ import annotations

from agent_framework_hosting import (
    ChannelIdentity,
    ChannelRequest,
    ChannelSession,
    ResponseTarget,
    ResponseTargetKind,
)


class TestResponseTarget:
    def test_originating_default_singleton(self) -> None:
        target = ResponseTarget.originating  # type: ignore[attr-defined]
        assert target.kind is ResponseTargetKind.ORIGINATING
        assert target.targets == ()

    def test_active_singleton(self) -> None:
        target = ResponseTarget.active  # type: ignore[attr-defined]
        assert target.kind is ResponseTargetKind.ACTIVE
        assert target.targets == ()

    def test_all_linked_singleton(self) -> None:
        target = ResponseTarget.all_linked  # type: ignore[attr-defined]
        assert target.kind is ResponseTargetKind.ALL_LINKED

    def test_none_singleton(self) -> None:
        target = ResponseTarget.none  # type: ignore[attr-defined]
        assert target.kind is ResponseTargetKind.NONE

    def test_channel_builder_single(self) -> None:
        target = ResponseTarget.channel("teams")
        assert target.kind is ResponseTargetKind.CHANNELS
        assert target.targets == ("teams",)

    def test_channels_builder_list(self) -> None:
        target = ResponseTarget.channels(["teams", "telegram", "originating"])
        assert target.kind is ResponseTargetKind.CHANNELS
        assert target.targets == ("teams", "telegram", "originating")

    def test_channels_builder_accepts_tuple(self) -> None:
        target = ResponseTarget.channels(("a", "b"))
        assert target.targets == ("a", "b")

    def test_target_is_hashable(self) -> None:
        # Plain class — hashing falls back to identity, which is fine here:
        # the two keys below are different instances (singleton vs builder).
        d = {ResponseTarget.originating: 1, ResponseTarget.channel("t"): 2}  # type: ignore[attr-defined]
        assert len(d) == 2


class TestChannelRequest:
    def test_required_fields_only(self) -> None:
        req = ChannelRequest(channel="responses", operation="message.create", input="hi")
        assert req.channel == "responses"
        assert req.operation == "message.create"
        assert req.input == "hi"
        assert req.session is None
        assert req.options is None
        assert req.session_mode == "auto"
        assert req.metadata == {}
        assert req.attributes == {}
        assert req.stream is False
        assert req.identity is None
        # Default response target is the originating singleton.
        assert req.response_target.kind is ResponseTargetKind.ORIGINATING

    def test_default_response_target_is_originating_singleton(self) -> None:
        # Every new request shares the module-level ``originating`` singleton
        # by default — instances are intended to be treated as immutable, so
        # sharing is safe and avoids per-request allocation.
        a = ChannelRequest(channel="a", operation="op", input="x")
        b = ChannelRequest(channel="b", operation="op", input="y")
        assert a.response_target is ResponseTarget.originating  # type: ignore[attr-defined]
        assert a.response_target is b.response_target

    def test_with_session_and_identity(self) -> None:
        req = ChannelRequest(
            channel="telegram",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="user:42"),
            identity=ChannelIdentity(channel="telegram", native_id="42"),
            response_target=ResponseTarget.active,  # type: ignore[attr-defined]
        )
        assert req.session is not None
        assert req.session.isolation_key == "user:42"
        assert req.identity is not None
        assert req.identity.channel == "telegram"
        assert req.identity.native_id == "42"
        assert req.response_target.kind is ResponseTargetKind.ACTIVE


class TestChannelIdentity:
    def test_attributes_default_empty_mapping(self) -> None:
        ident = ChannelIdentity(channel="teams", native_id="abc")
        assert dict(ident.attributes) == {}

    def test_attributes_passthrough(self) -> None:
        ident = ChannelIdentity(channel="teams", native_id="abc", attributes={"role": "user"})
        assert dict(ident.attributes) == {"role": "user"}
