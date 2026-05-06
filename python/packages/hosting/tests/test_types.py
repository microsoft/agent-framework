# Copyright (c) Microsoft. All rights reserved.

"""Tests for the channel-neutral envelope types in :mod:`agent_framework_hosting._types`."""

from __future__ import annotations

from typing import Any

import pytest

from agent_framework_hosting import (
    ChannelIdentity,
    ChannelRequest,
    ChannelSession,
    DeliveryReport,
    ResponseTarget,
    ResponseTargetKind,
    apply_run_hook,
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


class _DummyTarget:
    """Stand-in for the ``SupportsAgentRun | Workflow`` arg `apply_run_hook` forwards.

    `apply_run_hook` doesn't introspect the target — it just forwards
    it as a kwarg to the user's hook — so a bare class is enough.
    """


class TestApplyRunHook:
    """`apply_run_hook` is the channel-side helper that invokes a
    `ChannelRunHook` with the standard kwargs (`request` positional,
    `target` / `protocol_request` keyword). Channels call this rather
    than calling the hook directly so the convention is enforced in
    one place. Cover both branching paths (sync vs async hook return)
    and assert kwargs forwarding so a regression that drops `target`
    or `protocol_request` is caught."""

    @pytest.mark.asyncio
    async def test_sync_hook_returning_modified_request(self) -> None:
        captured: dict[str, Any] = {}

        def hook(request: ChannelRequest, **kwargs: Any) -> ChannelRequest:
            # Snapshot the kwargs for the assertion below, then return a
            # NEW request so we also verify the helper passes the
            # replacement straight through (no merging / mutation).
            captured["target"] = kwargs.get("target")
            captured["protocol_request"] = kwargs.get("protocol_request")
            return ChannelRequest(channel=request.channel, operation="HOOK_TOUCHED", input=request.input)

        original = ChannelRequest(channel="responses", operation="op", input="hi")
        target = _DummyTarget()
        proto = {"raw": "payload"}

        result = await apply_run_hook(hook, original, target=target, protocol_request=proto)

        assert result is not original
        assert result.operation == "HOOK_TOUCHED"
        assert captured["target"] is target
        assert captured["protocol_request"] is proto

    @pytest.mark.asyncio
    async def test_async_hook_returning_modified_request(self) -> None:
        captured: dict[str, Any] = {}

        async def hook(request: ChannelRequest, **kwargs: Any) -> ChannelRequest:
            captured["target"] = kwargs.get("target")
            captured["protocol_request"] = kwargs.get("protocol_request")
            # Return an awaitable result to exercise the async branch
            # (`isinstance(result, Awaitable) → await it`).
            return ChannelRequest(channel=request.channel, operation="ASYNC_HOOK", input=request.input)

        original = ChannelRequest(channel="telegram", operation="op", input="hi")
        target = _DummyTarget()
        proto = {"update_id": 42}

        result = await apply_run_hook(hook, original, target=target, protocol_request=proto)

        assert result.operation == "ASYNC_HOOK"
        assert captured["target"] is target
        assert captured["protocol_request"] is proto

    @pytest.mark.asyncio
    async def test_protocol_request_can_be_none(self) -> None:
        """Channels that don't have a raw protocol payload (e.g. CLI / test
        harness invocations) pass ``protocol_request=None``; the helper
        forwards it as-is so hooks can ``if protocol_request is None`` to
        gate channel-specific logic."""
        captured: dict[str, Any] = {}

        async def hook(request: ChannelRequest, **kwargs: Any) -> ChannelRequest:
            captured["protocol_request"] = kwargs.get("protocol_request")
            captured["protocol_request_in_kwargs"] = "protocol_request" in kwargs
            return request

        await apply_run_hook(
            hook,
            ChannelRequest(channel="x", operation="op", input="hi"),
            target=_DummyTarget(),
            protocol_request=None,
        )

        assert captured["protocol_request"] is None
        assert captured["protocol_request_in_kwargs"] is True


class TestDeliveryReport:
    """`DeliveryReport.failed` distinguishes "push raised" (an outage)
    from "no link recorded" (`skipped`). Assert the field exists,
    defaults empty, accepts the documented shape, and that the original
    `pushed` / `skipped` semantics are preserved."""

    def test_defaults_are_empty_tuples(self) -> None:
        report = DeliveryReport(include_originating=True)
        assert report.include_originating is True
        assert report.pushed == ()
        assert report.skipped == ()
        assert report.failed == ()

    def test_failed_carries_token_and_error_summary(self) -> None:
        # Channels return a (token, summary) tuple per failed push so
        # the originating channel can tell "telegram outage" from
        # "no link" without parsing logs.
        report = DeliveryReport(
            include_originating=False,
            pushed=("teams:42",),
            skipped=("telegram",),
            failed=(("telegram:99", "RuntimeError: rate limited"),),
        )
        assert report.pushed == ("teams:42",)
        assert report.skipped == ("telegram",)
        assert len(report.failed) == 1
        token, summary = report.failed[0]
        assert token == "telegram:99"
        assert "RuntimeError" in summary
        assert "rate limited" in summary
