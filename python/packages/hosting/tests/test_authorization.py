# Copyright (c) Microsoft. All rights reserved.

"""Tests for the Wave-1 authorization seam."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import pytest

from agent_framework_hosting import (
    AgentFrameworkHost,
    AllOfAllowlists,
    AllowAll,
    Allowed,
    AllowlistDecision,
    AnyOfAllowlists,
    AuthorizationContext,
    CallableAllowlist,
    ChannelConfigurationError,
    ChannelContext,
    ChannelContribution,
    ChannelIdentity,
    Denied,
    LinkedClaimAllowlist,
    NativeIdAllowlist,
)

# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #


class _ChannelStub:
    name: str = "stub"
    path: str = "/stub"
    require_link: bool = False
    allowlist: Any = "inherit"
    emits_verified_claims: bool = False

    def __init__(
        self,
        *,
        name: str = "stub",
        require_link: bool = False,
        allowlist: Any = "inherit",
        emits_verified_claims: bool = False,
    ) -> None:
        self.name = name
        self.path = f"/{name}"
        self.require_link = require_link
        self.allowlist = allowlist
        self.emits_verified_claims = emits_verified_claims

    def contribute(self, context: ChannelContext) -> ChannelContribution:
        return ChannelContribution(routes=[])


class _AgentStub:
    """Bare minimum target — the validators run during ``__init__``,
    not on first request, so the target is never actually invoked."""

    async def run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def _ctx_pre_link(channel: str = "telegram", native_id: str = "42") -> AuthorizationContext:
    return AuthorizationContext(
        identity=ChannelIdentity(channel=channel, native_id=native_id),
        phase="pre_link",
    )


def _ctx_post_link(claims: dict[str, str] | None = None) -> AuthorizationContext:
    return AuthorizationContext(
        identity=ChannelIdentity(channel="telegram", native_id="42"),
        phase="post_link",
        isolation_key="alice",
        verified_claims=claims or {},
        claim_source="linker",
    )


# --------------------------------------------------------------------------- #
# Built-in allowlists                                                          #
# --------------------------------------------------------------------------- #


class TestAllowAll:
    async def test_allows_both_phases(self) -> None:
        a = AllowAll()
        assert await a.evaluate(_ctx_pre_link()) is AllowlistDecision.ALLOW
        assert await a.evaluate(_ctx_post_link()) is AllowlistDecision.ALLOW

    def test_does_not_require_linked_claims(self) -> None:
        assert AllowAll().requires_linked_claims is False


class TestNativeIdAllowlist:
    async def test_allows_listed_id(self) -> None:
        a = NativeIdAllowlist({"42", "99"})
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.ALLOW

    async def test_denies_unlisted_id(self) -> None:
        a = NativeIdAllowlist({"42"})
        assert await a.evaluate(_ctx_pre_link(native_id="99")) is AllowlistDecision.DENY

    async def test_channel_filter_abstains_for_other_channels(self) -> None:
        # The native-id list is scoped to "telegram" — a request from
        # another channel should ABSTAIN so a combinator can give a
        # parallel allowlist a chance to ALLOW.
        a = NativeIdAllowlist({"42"}, channel="telegram")
        assert await a.evaluate(_ctx_pre_link(channel="slack", native_id="42")) is AllowlistDecision.ABSTAIN

    async def test_channel_filter_evaluates_matching_channel(self) -> None:
        a = NativeIdAllowlist({"42"}, channel="telegram")
        assert await a.evaluate(_ctx_pre_link(channel="telegram", native_id="42")) is AllowlistDecision.ALLOW
        assert await a.evaluate(_ctx_pre_link(channel="telegram", native_id="99")) is AllowlistDecision.DENY

    async def test_async_loader_caches_after_first_call(self) -> None:
        # The loader should run once; subsequent ``evaluate`` calls hit
        # the cache so a slow / costly source isn't re-queried per
        # message.
        calls = {"n": 0}

        async def loader() -> Collection[str]:
            calls["n"] += 1
            return {"42"}

        a = NativeIdAllowlist(loader)
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.ALLOW
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.ALLOW
        assert calls["n"] == 1


class TestLinkedClaimAllowlist:
    """Wave 1 ships the type for composition but its ``evaluate``
    raises ``NotImplementedError`` — the host's startup validator
    must catch the misconfig before runtime."""

    def test_declares_requires_linked_claims(self) -> None:
        a = LinkedClaimAllowlist("oid", ["abc"])
        assert a.requires_linked_claims is True

    async def test_evaluate_raises_not_implemented(self) -> None:
        a = LinkedClaimAllowlist("oid", ["abc"])
        with pytest.raises(NotImplementedError, match="Wave 2"):
            await a.evaluate(_ctx_pre_link())


class TestAnyOfAllowlists:
    async def test_any_allow_wins(self) -> None:
        a = AnyOfAllowlists(NativeIdAllowlist({"42"}), NativeIdAllowlist({"99"}))
        # native_id=42 → first ALLOWs, short-circuit.
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.ALLOW

    async def test_all_deny_yields_deny(self) -> None:
        # Both lists deny native_id=7.
        a = AnyOfAllowlists(NativeIdAllowlist({"42"}), NativeIdAllowlist({"99"}))
        assert await a.evaluate(_ctx_pre_link(native_id="7")) is AllowlistDecision.DENY

    async def test_abstain_when_no_decision(self) -> None:
        # Channel-scoped lists both ABSTAIN on a "slack" request.
        a = AnyOfAllowlists(
            NativeIdAllowlist({"42"}, channel="telegram"),
            NativeIdAllowlist({"99"}, channel="teams"),
        )
        assert await a.evaluate(_ctx_pre_link(channel="slack", native_id="42")) is AllowlistDecision.ABSTAIN

    async def test_empty_is_abstain(self) -> None:
        # No children → ABSTAIN (not DENY) to avoid silent deny-all.
        a = AnyOfAllowlists()
        assert await a.evaluate(_ctx_pre_link()) is AllowlistDecision.ABSTAIN

    def test_propagates_requires_linked_claims(self) -> None:
        a = AnyOfAllowlists(NativeIdAllowlist({"42"}), LinkedClaimAllowlist("oid", []))
        assert a.requires_linked_claims is True


class TestAllOfAllowlists:
    async def test_any_deny_short_circuits(self) -> None:
        a = AllOfAllowlists(NativeIdAllowlist({"42"}), NativeIdAllowlist({"99"}))
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.DENY

    async def test_all_allow_yields_allow(self) -> None:
        a = AllOfAllowlists(NativeIdAllowlist({"42"}), NativeIdAllowlist({"42", "99"}))
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.ALLOW

    async def test_abstain_when_no_deny_but_no_unanimous_allow(self) -> None:
        a = AllOfAllowlists(
            NativeIdAllowlist({"42"}, channel="telegram"),
            NativeIdAllowlist({"42"}, channel="teams"),
        )
        # ABSTAIN from teams (different channel), ALLOW from telegram → ABSTAIN.
        assert await a.evaluate(_ctx_pre_link(channel="telegram", native_id="42")) is AllowlistDecision.ABSTAIN

    async def test_empty_is_abstain(self) -> None:
        a = AllOfAllowlists()
        assert await a.evaluate(_ctx_pre_link()) is AllowlistDecision.ABSTAIN


class TestCallableAllowlist:
    async def test_wraps_async_fn(self) -> None:
        async def fn(ctx: AuthorizationContext) -> AllowlistDecision:
            if ctx.identity.native_id == "42":
                return AllowlistDecision.ALLOW
            return AllowlistDecision.DENY

        a = CallableAllowlist(fn)
        assert await a.evaluate(_ctx_pre_link(native_id="42")) is AllowlistDecision.ALLOW
        assert await a.evaluate(_ctx_pre_link(native_id="99")) is AllowlistDecision.DENY

    def test_requires_linked_claims_passthrough(self) -> None:
        async def fn(_: AuthorizationContext) -> AllowlistDecision:  # pragma: no cover
            return AllowlistDecision.ALLOW

        a = CallableAllowlist(fn, requires_linked_claims=True)
        assert a.requires_linked_claims is True


# --------------------------------------------------------------------------- #
# Host configuration validator                                                 #
# --------------------------------------------------------------------------- #


class TestChannelAuthorizationValidator:
    """The host's startup validator catches three classes of misconfig
    so they fail at construction rather than silently denying every
    user at runtime."""

    def test_require_link_without_linker_raises(self) -> None:
        # ``require_link=True`` with no linker would silently reject
        # every request — caught at construction.
        with pytest.raises(ChannelConfigurationError, match="identity_linker"):
            AgentFrameworkHost(
                target=_AgentStub(),
                channels=[_ChannelStub(require_link=True)],
            )

    def test_linked_claim_allowlist_without_claim_source_raises(self) -> None:
        # The channel has no ``require_link=True`` AND doesn't emit
        # claims natively → the allowlist would always DENY / ABSTAIN.
        with pytest.raises(ChannelConfigurationError, match="verified IdP claims"):
            AgentFrameworkHost(
                target=_AgentStub(),
                channels=[_ChannelStub(allowlist=LinkedClaimAllowlist("oid", []))],
            )

    def test_linked_claim_allowlist_with_native_claim_source_passes(self) -> None:
        # When the channel declares ``emits_verified_claims=True``
        # (e.g. Activity Protocol with AAD bearer) the validator
        # accepts the LinkedClaimAllowlist without needing a linker.
        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[
                _ChannelStub(
                    allowlist=LinkedClaimAllowlist("oid", ["abc"]),
                    emits_verified_claims=True,
                )
            ],
        )
        assert host.default_allowlist is None

    def test_native_id_allowlist_unknown_channel_raises(self) -> None:
        with pytest.raises(ChannelConfigurationError, match="unknown channel 'mystery'"):
            AgentFrameworkHost(
                target=_AgentStub(),
                channels=[_ChannelStub(allowlist=NativeIdAllowlist({"42"}, channel="mystery"))],
            )

    def test_native_id_allowlist_known_channel_passes(self) -> None:
        # A channel-scoped native list pointing at a peer channel is
        # the supported way to compose per-channel allowlists.
        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[
                _ChannelStub(name="telegram", allowlist=NativeIdAllowlist({"42"}, channel="telegram")),
                _ChannelStub(name="slack"),
            ],
        )
        assert host.runtime_mode == "long_running"

    def test_default_allowlist_applies_to_inheriting_channel(self) -> None:
        # ``allowlist="inherit"`` (the default) picks up the host-level
        # ``default_allowlist``. This is the "lock down a whole bot in
        # one place" ergonomic.
        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub(name="telegram")],
            default_allowlist=NativeIdAllowlist({"42"}),
        )
        # The default flowed through; channel sees the host's allowlist.
        assert host.default_allowlist is not None

    def test_explicit_none_carve_out_overrides_default(self) -> None:
        # ``allowlist=None`` on a channel explicitly opts out of the
        # host default — useful for a public endpoint inside an
        # otherwise locked-down host.
        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub(name="public", allowlist=None)],
            default_allowlist=NativeIdAllowlist({"42"}),
        )
        # Construction succeeded; the validator did not raise.
        assert host.default_allowlist is not None

    def test_combinator_with_unknown_nested_channel_raises(self) -> None:
        # The validator walks ``AnyOfAllowlists`` / ``AllOfAllowlists``
        # so a typo'd channel name nested under a combinator is still
        # caught at construction.
        with pytest.raises(ChannelConfigurationError, match="unknown channel 'typo'"):
            AgentFrameworkHost(
                target=_AgentStub(),
                channels=[
                    _ChannelStub(
                        allowlist=AnyOfAllowlists(
                            NativeIdAllowlist({"42"}, channel="stub"),
                            NativeIdAllowlist({"99"}, channel="typo"),
                        )
                    )
                ],
            )


# --------------------------------------------------------------------------- #
# host.authorize pipeline                                                      #
# --------------------------------------------------------------------------- #


class TestHostAuthorize:
    """Wave-1 pipeline: open / native-allowlist end-to-end; claim-based
    allowlist returns ``Denied(reason_code="allowlist_requires_link")``
    in the absence of a linker."""

    def _host(self) -> AgentFrameworkHost:
        return AgentFrameworkHost(target=_AgentStub(), channels=[_ChannelStub()])

    async def test_open_profile_returns_allowed_with_auto_isolation_key(self) -> None:
        host = self._host()
        outcome = await host.authorize(ChannelIdentity(channel="telegram", native_id="42"))
        assert isinstance(outcome, Allowed)
        assert outcome.isolation_key == "telegram:42"

    async def test_native_allowlist_allows_listed_id(self) -> None:
        host = self._host()
        outcome = await host.authorize(
            ChannelIdentity(channel="telegram", native_id="42"),
            allowlist=NativeIdAllowlist({"42"}),
        )
        assert isinstance(outcome, Allowed)
        assert outcome.isolation_key == "telegram:42"

    async def test_native_allowlist_denies_unlisted_id(self) -> None:
        host = self._host()
        outcome = await host.authorize(
            ChannelIdentity(channel="telegram", native_id="99"),
            allowlist=NativeIdAllowlist({"42"}),
        )
        assert isinstance(outcome, Denied)
        assert outcome.reason_code == "allowlist_denied_pre_link"
        assert outcome.user_message is not None
        # The bland default leaks neither tenant nor list size.
        assert "telegram" not in (outcome.user_message or "")

    async def test_abstain_with_claim_requirement_yields_link_required_message(self) -> None:
        # ``LinkedClaimAllowlist.evaluate`` raises in Wave 1, but the
        # host should reject the configuration earlier — when wrapped
        # in ``AnyOf`` with a claim source, the validator passes and
        # the abstain branch is exercised at runtime. We synthesise
        # this by using ``AllowAll`` combined with a
        # ``requires_linked_claims=True`` callable that ABSTAINs.
        async def abstain(_: AuthorizationContext) -> AllowlistDecision:
            return AllowlistDecision.ABSTAIN

        host = AgentFrameworkHost(
            target=_AgentStub(),
            channels=[_ChannelStub(emits_verified_claims=True)],
        )
        outcome = await host.authorize(
            ChannelIdentity(channel="telegram", native_id="42"),
            allowlist=CallableAllowlist(abstain, requires_linked_claims=True),
        )
        # Wave-1 maps "claim-required allowlist abstaining without a
        # linker" to a Denied(reason_code="allowlist_requires_link").
        assert isinstance(outcome, Denied)
        assert outcome.reason_code == "allowlist_requires_link"

    async def test_abstain_without_claim_requirement_falls_through_to_allowed(self) -> None:
        async def abstain(_: AuthorizationContext) -> AllowlistDecision:
            return AllowlistDecision.ABSTAIN

        host = self._host()
        outcome = await host.authorize(
            ChannelIdentity(channel="telegram", native_id="42"),
            allowlist=CallableAllowlist(abstain),
        )
        assert isinstance(outcome, Allowed)

    async def test_auto_issue_returns_existing_key_when_known(self) -> None:
        # When an identity has already been observed, the auto-issued
        # key matches the existing one rather than coining a fresh
        # token. This is the linker-free Wave-1 equivalent of identity
        # resolution.
        host = self._host()
        host._identities["alice"] = {"telegram": ChannelIdentity(channel="telegram", native_id="42")}
        outcome = await host.authorize(ChannelIdentity(channel="telegram", native_id="42"))
        assert isinstance(outcome, Allowed)
        assert outcome.isolation_key == "alice"

    async def test_verified_claims_propagate_to_context(self) -> None:
        # Channels that natively carry verified claims (e.g. Activity
        # Protocol bearer with AAD oid) pass them through to
        # ``authorize`` — the allowlist sees them on the
        # ``AuthorizationContext``.
        seen: list[AuthorizationContext] = []

        async def capture(ctx: AuthorizationContext) -> AllowlistDecision:
            seen.append(ctx)
            return AllowlistDecision.ALLOW

        host = self._host()
        await host.authorize(
            ChannelIdentity(channel="telegram", native_id="42"),
            allowlist=CallableAllowlist(capture),
            verified_claims={"oid": "abc"},
        )
        assert len(seen) == 1
        assert seen[0].claim_source == "channel"
        assert dict(seen[0].verified_claims) == {"oid": "abc"}
