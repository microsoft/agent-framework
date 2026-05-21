# Copyright (c) Microsoft. All rights reserved.

"""Authorization seam (Wave 1) — :class:`IdentityAllowlist` Protocol and outcomes.

Channels that emit a :class:`ChannelIdentity` compose authorization from
two **orthogonal** parameters set per channel:

- ``require_link: bool`` — "identity must be linked to an IdP claim". Owned
  by the Wave-2 :class:`IdentityLinker` stack; Wave-1 only enforces that
  ``require_link=True`` paired with a host that has no linker is rejected
  at construction (silent-deny-everyone is the worst possible default).
- ``allowlist: IdentityAllowlist | Literal["inherit"] | None`` — "identity
  is on the accept list". The host evaluates the allowlist on every
  inbound message via :func:`AgentFrameworkHost.authorize`.

The two axes compose into the three named profiles **open** (no gate),
**forced-link** (any authenticated identity), and **allowlist** (only
listed identities, keyed either on the channel-native id pre-link or on
a verified IdP claim post-link). See
``docs/specs/002-python-hosting-channels.md`` §
"Authorization profiles and the IdentityAllowlist seam".

This module ships **Wave 1**: the Protocol, the enum, the built-in
allowlists (with :class:`LinkedClaimAllowlist` raising at runtime —
its enforcement lands with the linker), the outcome types, and the
exception the host's startup validator raises. Wave 2 will add the
end-to-end pipeline through the linker; the public types are stable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from ._types import ChannelIdentity


class AllowlistDecision(str, Enum):
    """Tri-state allowlist evaluation outcome.

    ``ABSTAIN`` is **not** a denial — it means "this allowlist has no
    information yet" (typically a claim-based allowlist evaluated at
    ``pre_link``). The host's :meth:`AgentFrameworkHost.authorize`
    pipeline is what turns an all-``ABSTAIN`` outcome into the next
    step (allow when open, escalate to a link ceremony when the config
    calls for one). Boolean composition cannot distinguish "claim
    allowlist denies you" from "claim allowlist hasn't seen any claims
    yet" — a critical distinction for the **Mixed** profile.
    """

    ALLOW = "allow"
    DENY = "deny"
    ABSTAIN = "abstain"


def _empty_str_mapping() -> Mapping[str, str]:
    return {}


def _empty_any_mapping() -> Mapping[str, Any]:
    return {}


@dataclass(frozen=True)
class AuthorizationContext:
    """Inputs to a single :meth:`IdentityAllowlist.evaluate` call."""

    identity: ChannelIdentity
    phase: Literal["pre_link", "post_link"]
    isolation_key: str | None = None
    verified_claims: Mapping[str, str] = field(default_factory=_empty_str_mapping)
    claim_source: Literal["linker", "channel", "none"] = "none"


@runtime_checkable
class IdentityAllowlist(Protocol):
    """Per-channel accept/deny gate evaluated by the host.

    ``requires_linked_claims`` declares that this allowlist's
    :meth:`evaluate` cannot ``ALLOW`` until verified claims are
    available — the host's construction-time validator rejects
    configurations that would silently deny everyone (e.g. a
    :class:`LinkedClaimAllowlist` on a channel that neither has
    ``require_link=True`` nor natively emits verified claims).
    """

    requires_linked_claims: bool

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision: ...


class AllowAll:
    """Explicit "open" sentinel.

    Useful for tests, sample code, and for **overriding** a host-level
    ``default_allowlist`` on a specific channel that should be public
    inside an otherwise locked-down host.
    """

    requires_linked_claims: bool = False

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision:
        return AllowlistDecision.ALLOW


class NativeIdAllowlist:
    """Accept only listed channel-native ids.

    Telegram ``chat_id``, WhatsApp number, Slack user id, etc. The
    list can be a plain collection or an async loader so allowlist
    sources can be config files, secret stores, or feature flags.
    Pre-link and post-link behaviour is identical — native-id
    allowlists do not depend on link state.

    When ``channel`` is set, the allowlist participates in
    :class:`AnyOfAllowlists` composition by returning ``ABSTAIN`` for
    requests from other channels — this lets per-channel native lists
    coexist under a single combinator without one channel's ``DENY``
    masking another channel's ``ALLOW``.

    Keyword Args:
        native_ids: A static collection of ids, or an async loader.
        channel: When set, only requests whose
            ``ChannelIdentity.channel`` matches participate; others
            ``ABSTAIN``.
    """

    requires_linked_claims: bool = False

    def __init__(
        self,
        native_ids: Collection[str] | Callable[[], Awaitable[Collection[str]]],
        *,
        channel: str | None = None,
    ) -> None:
        self._native_ids: Collection[str] | None
        self._loader: Callable[[], Awaitable[Collection[str]]] | None
        if callable(native_ids):
            self._native_ids = None
            self._loader = native_ids
        else:
            self._native_ids = frozenset(native_ids)
            self._loader = None
        self.channel = channel

    async def _resolve(self) -> Collection[str]:
        if self._native_ids is not None:
            return self._native_ids
        loader = self._loader
        if loader is None:  # pragma: no cover - defensive
            raise RuntimeError("NativeIdAllowlist: loader missing after cache miss")
        loaded = await loader()
        # Cache the resolved set so subsequent calls avoid re-loading.
        self._native_ids = frozenset(loaded)
        self._loader = None
        return self._native_ids

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision:
        if self.channel is not None and context.identity.channel != self.channel:
            return AllowlistDecision.ABSTAIN
        ids = await self._resolve()
        if context.identity.native_id in ids:
            return AllowlistDecision.ALLOW
        return AllowlistDecision.DENY


class LinkedClaimAllowlist:
    """Accept only identities whose verified IdP claim is on the list.

    ``evaluate`` returns ``ABSTAIN`` at ``pre_link`` (no claims yet)
    and ``ALLOW``/``DENY`` at ``post_link``. Wave 1 ships the type for
    composition but **raises** :class:`NotImplementedError` at
    runtime because the end-to-end pipeline depends on the
    :class:`IdentityLinker` stack which lands in Wave 2.

    Keyword Args:
        claim: The verified-claim key to inspect (e.g. ``"oid"``,
            ``"tid"``, ``"groups"``).
        values: Accepted values.
    """

    requires_linked_claims: bool = True

    def __init__(self, claim: str, values: Collection[str]) -> None:
        self.claim = claim
        self.values = frozenset(values)

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision:
        # Wave 1 fail-loud: surfacing the unimplemented gap is far
        # better than silently allowing or denying. The host's startup
        # validator should prevent this from being reached in
        # production by requiring a configured linker.
        raise NotImplementedError(
            "LinkedClaimAllowlist is part of Wave 2 (IdentityLinker stack). "
            "Configure a linker before using this allowlist; until then either "
            "use NativeIdAllowlist or pair this with require_link=True on a "
            "channel that natively emits verified claims."
        )


class AnyOfAllowlists:
    """Combinator: any child ``ALLOW`` wins; ``DENY`` only if all children ``DENY``.

    Use this for the **Mixed** profile (native id OR linked claim).
    Returns ``ABSTAIN`` when no child decides.
    """

    def __init__(self, *allowlists: IdentityAllowlist) -> None:
        self._children = allowlists
        self.requires_linked_claims = any(getattr(a, "requires_linked_claims", False) for a in allowlists)

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision:
        any_abstain = False
        all_deny = True
        for child in self._children:
            decision = await child.evaluate(context)
            if decision is AllowlistDecision.ALLOW:
                return AllowlistDecision.ALLOW
            if decision is AllowlistDecision.ABSTAIN:
                any_abstain = True
                all_deny = False
            # DENY contributes to all_deny without short-circuit.
        if all_deny and self._children:
            return AllowlistDecision.DENY
        if any_abstain:
            return AllowlistDecision.ABSTAIN
        # No children — treat as ABSTAIN to avoid surprise DENY.
        return AllowlistDecision.ABSTAIN


class AllOfAllowlists:
    """Combinator: any child ``DENY`` wins; ``ALLOW`` only if all children ``ALLOW``.

    Use this to require multiple conditions (e.g. tenancy
    **and** group membership). Returns ``ABSTAIN`` when no child
    denies but at least one ``ABSTAIN``s.
    """

    def __init__(self, *allowlists: IdentityAllowlist) -> None:
        self._children = allowlists
        self.requires_linked_claims = any(getattr(a, "requires_linked_claims", False) for a in allowlists)

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision:
        any_abstain = False
        for child in self._children:
            decision = await child.evaluate(context)
            if decision is AllowlistDecision.DENY:
                return AllowlistDecision.DENY
            if decision is AllowlistDecision.ABSTAIN:
                any_abstain = True
        if not self._children:
            return AllowlistDecision.ABSTAIN
        if any_abstain:
            return AllowlistDecision.ABSTAIN
        return AllowlistDecision.ALLOW


class CallableAllowlist:
    """Escape hatch: wrap an arbitrary async function as an allowlist.

    Recommended only after exhausting the structured variants —
    composition is harder to reason about with opaque callables.
    """

    def __init__(
        self,
        fn: Callable[[AuthorizationContext], Awaitable[AllowlistDecision]],
        *,
        requires_linked_claims: bool = False,
    ) -> None:
        self._fn = fn
        self.requires_linked_claims = requires_linked_claims

    async def evaluate(self, context: AuthorizationContext) -> AllowlistDecision:
        return await self._fn(context)


# --------------------------------------------------------------------------- #
# Outcome types                                                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Allowed:
    """The identity is authorized; ``isolation_key`` is its stable key."""

    isolation_key: str


@dataclass(frozen=True)
class LinkRequired:
    """The identity must complete the link ceremony before proceeding.

    ``challenge`` carries the Wave-2 ``LinkChallenge`` payload; in
    Wave 1 it is untyped (``Any``) so the public surface can ship
    ahead of the linker. Channels render it through their native UX
    (the same path the ``link`` command already uses).
    """

    challenge: Any


@dataclass(frozen=True)
class Denied:
    """The identity is rejected.

    Attributes:
        reason_code: Stable, machine-readable token (e.g.
            ``"allowlist_denied_pre_link"``). Never echoed to end
            users.
        user_message: Safe to render publicly (group-chat-safe);
            ``None`` falls back to a bland default ("You don't have
            access to this bot.").
        log_details: Structured payload for audit/observability;
            **never** shown to users.
    """

    reason_code: str
    user_message: str | None = None
    log_details: Mapping[str, Any] = field(default_factory=_empty_any_mapping)


AuthorizationOutcome = Allowed | LinkRequired | Denied
"""Result of :func:`AgentFrameworkHost.authorize`. Channels render
each variant through their native UX."""


# --------------------------------------------------------------------------- #
# Configuration error                                                          #
# --------------------------------------------------------------------------- #


class ChannelConfigurationError(ValueError):
    """Raised at host construction for authorization config that would deny all users.

    The host validator runs three rules (see spec §"Configuration
    validation"); any failure is reported here rather than letting
    the misconfigured host start up and reject every request.
    """


__all__ = [
    "AllOfAllowlists",
    "AllowAll",
    "Allowed",
    "AllowlistDecision",
    "AnyOfAllowlists",
    "AuthorizationContext",
    "AuthorizationOutcome",
    "CallableAllowlist",
    "ChannelConfigurationError",
    "Denied",
    "IdentityAllowlist",
    "LinkRequired",
    "LinkedClaimAllowlist",
    "NativeIdAllowlist",
]
