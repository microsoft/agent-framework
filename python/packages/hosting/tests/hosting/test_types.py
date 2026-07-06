# Copyright (c) Microsoft. All rights reserved.

"""Tests for the channel-neutral envelope types in :mod:`agent_framework_hosting._types`."""

from __future__ import annotations

from agent_framework_hosting import (
    ChannelIdentity,
    ChannelRequest,
    ChannelSession,
)


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

    def test_with_session_and_identity(self) -> None:
        req = ChannelRequest(
            channel="telegram",
            operation="message.create",
            input="hi",
            session=ChannelSession(isolation_key="user:42"),
            identity=ChannelIdentity(channel="telegram", native_id="42"),
        )
        assert req.session is not None
        assert req.session.isolation_key == "user:42"
        assert req.identity is not None
        assert req.identity.channel == "telegram"
        assert req.identity.native_id == "42"


class TestChannelIdentity:
    def test_attributes_default_empty_mapping(self) -> None:
        ident = ChannelIdentity(channel="teams", native_id="abc")
        assert dict(ident.attributes) == {}

    def test_attributes_passthrough(self) -> None:
        ident = ChannelIdentity(channel="teams", native_id="abc", attributes={"role": "user"})
        assert dict(ident.attributes) == {"role": "user"}
