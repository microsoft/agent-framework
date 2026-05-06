# Copyright (c) Microsoft. All rights reserved.

"""Foundry Hosted Agent history provider.

A standalone :class:`agent_framework.HistoryProvider` implementation that
sources conversation history from the Foundry Hosted Agent storage backend.

Transport is delegated to the SDK's
:class:`azure.ai.agentserver.responses.FoundryStorageProvider` (when running
inside a Foundry Hosted Agent container) or
:class:`azure.ai.agentserver.responses.InMemoryResponseProvider` (for local
development). Both implement the same read/write surface
(``get_history_item_ids`` / ``get_items`` / ``create_response``), so this
provider's persistence logic stays backend-agnostic.

Allowed dependencies (deliberately narrow):

* :mod:`agent_framework` (core, for ``HistoryProvider`` / ``Message``)
* :mod:`azure.ai.agentserver.responses` (for the storage backends,
  ``IsolationContext`` typing, and ``OutputItem`` deserialization)
* :mod:`azure.core.credentials_async` (typing of token credentials)

It MUST NOT depend on any ``agent_framework_hosting*`` package at module
import time. (The host's isolation contextvar is consulted lazily via an
``import`` inside :func:`_host_isolation` so the dependency stays soft.)

Environment variables read:

* ``FOUNDRY_HOSTING_ENVIRONMENT`` — non-empty marks "running inside Foundry"
  and selects the SDK-backed storage transport.
* ``FOUNDRY_PROJECT_ENDPOINT`` — base URL of the Foundry project; required
  when running hosted unless an explicit ``endpoint=`` is supplied.
* ``FOUNDRY_AGENT_NAME`` / ``FOUNDRY_AGENT_VERSION`` — stamped onto the
  ``agent_reference`` field of every persisted response envelope.
* ``FOUNDRY_AGENT_SESSION_ID`` — used as a chain anchor when the channel
  did not bind a per-request ``previous_response_id``.
* ``MODEL_DEPLOYMENT_NAME`` / ``AZURE_AI_MODEL_DEPLOYMENT_NAME`` — model
  field stamped on the persisted envelope (must match a real deployment).

Local fallback: when ``FOUNDRY_HOSTING_ENVIRONMENT`` is unset, the provider
transparently falls back to :class:`InMemoryResponseProvider` so the same
agent code runs in dev. Pass ``local_storage_root`` to use a persistent
file-based store instead of in-memory; histories are then laid out as
``{root}/{user_key or "~none"}/{chat_key or "~none"}/{session_id}.jsonl``
via :class:`agent_framework.FileHistoryProvider`.
"""

from __future__ import annotations

import logging
import os
import time
from base64 import urlsafe_b64encode
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from agent_framework import FileHistoryProvider, HistoryProvider, Message
from azure.ai.agentserver.responses import (
    FoundryStorageProvider,
    FoundryStorageSettings,
    InMemoryResponseProvider,
    IsolationContext,
)
from azure.ai.agentserver.responses._id_generator import IdGenerator
from azure.ai.agentserver.responses.models import OutputItem, ResponseObject
from azure.ai.agentserver.responses.store._foundry_errors import (  # pyright: ignore[reportPrivateUsage]
    FoundryBadRequestError,
    FoundryResourceNotFoundError,
    FoundryStorageError,
)

from ._shared import (
    _messages_to_output_items,  # pyright: ignore[reportPrivateUsage]
    _output_items_to_messages,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from azure.core.credentials_async import AsyncTokenCredential

logger = logging.getLogger(__name__)

# Environment variable names — re-declared (not imported) so this module
# stays decoupled from the private ``azure.ai.agentserver.core._config``
# constants while still matching them exactly.
_ENV_FOUNDRY_HOSTING_ENVIRONMENT = "FOUNDRY_HOSTING_ENVIRONMENT"
_ENV_FOUNDRY_PROJECT_ENDPOINT = "FOUNDRY_PROJECT_ENDPOINT"

# Per-request isolation context.  The owning Channel is expected to set this
# from the inbound request (e.g. user / tenant headers) for the duration of
# an ``agent.run(...)`` call.  When unset, requests are made without
# isolation headers (matches how ``ResponseContext`` behaves with no
# ``IsolationContext``).
_isolation_var: ContextVar[IsolationContext | None] = ContextVar(
    "agent_framework_foundry_hosting_isolation",
    default=None,
)


def set_current_isolation(isolation: IsolationContext | None) -> Any:
    """Set the per-request isolation context for downstream history calls.

    Channels that drive an agent backed by :class:`FoundryHostedAgentHistoryProvider`
    should call this before invoking ``agent.run(...)`` and reset the token
    afterwards.

    Args:
        isolation: The isolation context to associate with the current
            ``contextvars`` context, or ``None`` to clear it.

    Returns:
        A token suitable for :func:`reset_current_isolation` that restores
        the previous value.
    """
    return _isolation_var.set(isolation)


def reset_current_isolation(token: Any) -> None:
    """Restore a previously-saved isolation context.

    Args:
        token: A token returned by :func:`set_current_isolation`.
    """
    _isolation_var.reset(token)


def get_current_isolation() -> IsolationContext | None:
    """Return the isolation context bound to the current async context, if any.

    Returns:
        The :class:`IsolationContext` for the current request, or ``None``
        when no channel has set one.
    """
    return _isolation_var.get()


@dataclass(frozen=True)
class _RequestContext:
    """Per-request anchors the host binds before invoking the agent.

    ``response_id`` is the id this provider's :meth:`save_messages` call
    will write under, so the channel and the storage backend agree on
    one stable handle per turn (the channel surfaces the same id on the
    response envelope, the next turn arrives with this value as
    ``previous_response_id`` and the chain walks).

    ``previous_response_id`` is the prior turn's anchor (``None`` on
    first turn). Used to seed ``history_item_ids`` on the new write so
    the storage chain stays connected, and to load history without
    needing to know the channel's session minting convention.

    Per-request Foundry isolation keys (the
    ``x-agent-{user,chat}-isolation-key`` headers) are *not* carried
    here; the host's own ASGI middleware lifts them off every inbound
    HTTP request into a contextvar
    (:func:`agent_framework_hosting.get_current_isolation_keys`) which
    this provider consults at storage-call time. Keeping the headers
    out of the per-request bind means channels never have to import
    Foundry-specific types and the host owns the (intentional) coupling
    to those two well-known headers.
    """

    response_id: str
    previous_response_id: str | None


_request_var: ContextVar[_RequestContext | None] = ContextVar(
    "agent_framework_foundry_hosting_request",
    default=None,
)


@contextmanager
def bind_request_context(
    *,
    response_id: str,
    previous_response_id: str | None = None,
    **_unused: Any,
) -> Iterator[None]:
    """Bind the per-request response-chain anchors for this provider.

    Intended for the host (or any caller orchestrating an
    ``agent.run(...)``) to call immediately before invocation, so the
    provider's :meth:`save_messages` writes under a known, stable
    ``response_id`` (the same one the channel surfaces to the client)
    and walks ``previous_response_id`` for history continuity. Unknown
    keyword arguments are accepted and ignored so the host can extend
    the ``ChannelRequest.attributes`` contract without breaking existing
    providers. Foundry isolation keys flow through a separate
    host-installed contextvar; see the class docstring on
    :class:`_RequestContext`.

    The binding is scoped to the current ``contextvars.Context``, so
    concurrent requests in the same process do not interfere.
    """
    token = _request_var.set(
        _RequestContext(
            response_id=response_id,
            previous_response_id=previous_response_id,
        )
    )
    try:
        yield
    finally:
        _request_var.reset(token)


def get_current_request_context() -> _RequestContext | None:
    """Return the per-request response chain anchors, if bound."""
    return _request_var.get()


def _host_isolation() -> IsolationContext | None:
    """Lift the host-bound isolation contextvar into our local type.

    The host installs an ASGI middleware that reads
    ``x-agent-{user,chat}-isolation-key`` off every inbound HTTP request
    and stores them in a generic ``IsolationKeys`` slot on a contextvar
    we import from :mod:`agent_framework_hosting`. We translate it into
    our :class:`IsolationContext` shape on demand so the provider stays
    in charge of the storage-side type while the host stays free of any
    Foundry-specific dependencies.
    """
    # Soft dep: ``agent_framework_hosting`` may not be installed (this
    # provider is also usable standalone). The whole block is wrapped in
    # ``# pyright: ignore`` so the optional import does not block type
    # checking when the package isn't on sys.path; when it is, pyright
    # picks up the real types automatically.
    try:
        from agent_framework_hosting import (  # pyright: ignore[reportMissingImports]
            get_current_isolation_keys,  # pyright: ignore[reportUnknownVariableType]
        )
    except ImportError:  # pragma: no cover - hosting is a soft dep
        return None
    keys = get_current_isolation_keys()  # pyright: ignore[reportUnknownVariableType]
    if keys is None or keys.is_empty:  # pyright: ignore[reportUnknownMemberType]
        return None
    return IsolationContext(
        user_key=keys.user_key,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        chat_key=keys.chat_key,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    )


# Type alias for the storage backend surface this provider depends on.
# Both ``FoundryStorageProvider`` and ``InMemoryResponseProvider`` from
# ``azure.ai.agentserver.responses`` expose the same
# ``get_history_item_ids`` / ``get_items`` / ``create_response`` methods.
_StorageBackend = "FoundryStorageProvider | InMemoryResponseProvider"


# Sentinel directory name used in place of a missing ``user_key`` /
# ``chat_key`` when laying out file-based local history. The tilde
# prefix is reserved (``_is_safe_isolation_segment`` rejects keys that
# start with one) so a real isolation key can never collide with the
# sentinel after sanitisation.
_ISOLATION_NONE_MARKER = "~none"
_ISOLATION_ENCODED_PREFIX = "~iso-"

# Windows reserved file/directory stems. Mirrors
# ``FileHistoryProvider._WINDOWS_RESERVED_FILE_STEMS`` so the directory
# layer enforces the same portability constraints the file layer does.
_WINDOWS_RESERVED_STEMS = frozenset({
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def _is_safe_isolation_segment(value: str) -> bool:
    """Return whether ``value`` is safe to use directly as a directory name.

    Rules mirror :meth:`FileHistoryProvider._is_literal_session_file_stem_safe`,
    with the additional rule that a leading tilde is reserved for our
    sentinel/encoded prefixes so real keys can never collide with them.
    """
    if (
        not value
        or value.startswith((".", "~"))
        or value.endswith((" ", "."))
        or value.upper() in _WINDOWS_RESERVED_STEMS
    ):
        return False
    if any(ord(character) < 32 for character in value):
        return False
    return all(character.isalnum() or character in "._-" for character in value)


def _encode_isolation_segment(value: str | None) -> str:
    """Encode an isolation key into a filesystem-safe directory name.

    * ``None`` / empty → ``"~none"`` sentinel.
    * Already-safe values pass through unchanged.
    * Anything else is base64-url-encoded and prefixed with ``"~iso-"``
      so it is unambiguous and never collides with a real (safe) key.
    """
    if value is None or value == "":
        return _ISOLATION_NONE_MARKER
    if _is_safe_isolation_segment(value):
        return value
    encoded = urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_ISOLATION_ENCODED_PREFIX}{encoded}"


class FoundryHostedAgentHistoryProvider(HistoryProvider):
    """``HistoryProvider`` backed by Foundry Hosted Agent storage.

    Wraps :class:`azure.ai.agentserver.responses.FoundryStorageProvider`
    when running inside a Foundry Hosted Agent container, or
    :class:`InMemoryResponseProvider` for local development. The
    selection is driven by the ``FOUNDRY_HOSTING_ENVIRONMENT``
    environment variable.

    For local runs that need to *persist* history across process
    restarts, pass ``local_storage_root``: the provider then writes
    each conversation to
    ``{root}/{user_key or "~none"}/{chat_key or "~none"}/{session_id}.jsonl``
    via :class:`agent_framework.FileHistoryProvider`. The Foundry
    response-chain semantics (``previous_response_id`` walking,
    ``caresp_*`` id stamping, ``ResponseObject`` envelopes) are
    bypassed in file mode — the on-disk format is plain JSONL of
    :class:`Message` payloads, identical to ``FileHistoryProvider``
    standalone usage. ``local_storage_root`` is ignored when running
    hosted (Foundry storage always wins).

    ``session_id`` semantics: in hosted / in-memory mode the value
    passed to :meth:`get_messages` and :meth:`save_messages` is treated
    as the Responses ``previous_response_id`` (or ``conversation_id``)
    whose chain to load. When omitted (and no host-bound chain anchor
    is set), :meth:`get_messages` returns an empty list (a fresh
    conversation). In file mode ``session_id`` is used as the literal
    filename stem (``FileHistoryProvider`` sanitises unsafe values).
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "foundry_hosted_agent"

    def __init__(
        self,
        *,
        credential: AsyncTokenCredential | None = None,
        endpoint: str | None = None,
        history_limit: int = 100,
        source_id: str = DEFAULT_SOURCE_ID,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        store_outputs: bool = True,
        local_storage_root: str | Path | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            credential: Async token credential used to authenticate against
                the Foundry storage API. Required when running hosted
                (``FOUNDRY_HOSTING_ENVIRONMENT`` is set). Ignored in
                local-mode (the in-memory / file backends need no auth).
            endpoint: Foundry project endpoint URL. Defaults to the value
                of the ``FOUNDRY_PROJECT_ENDPOINT`` environment variable.
                Required when running hosted.
            history_limit: Maximum number of history items to fetch per
                ``get_messages`` call. Mirrors the agent-server runtime's
                ``ResponseContext._history_limit``. Default ``100``.
                Ignored in file mode (``FileHistoryProvider`` returns the
                full session file each call).
            source_id: Unique identifier for this provider instance, as
                required by ``HistoryProvider``.
            load_messages: Whether to load messages before invocation.
                Default ``True``.
            store_inputs: Whether to mirror input messages into Foundry
                storage. Default ``True`` — the Foundry Hosted Agents
                runtime does not persist Responses turns automatically, so
                without this the chain would never be visible to subsequent
                requests. Set ``False`` only if you know an external writer
                is populating storage on your behalf.
            store_context_messages: Whether to mirror context-provider
                messages. Default ``False``.
            store_context_from: If set, only mirror context messages from
                these source IDs.
            store_outputs: Whether to mirror response messages into Foundry
                storage. Default ``True`` for the same reason as
                ``store_inputs``.
            local_storage_root: When set, *and* the provider is running
                outside a Foundry Hosted Agent container, persist history
                to JSONL files under
                ``{root}/{user_key or "~none"}/{chat_key or "~none"}/{session_id}.jsonl``
                instead of using the in-memory backend. Ignored when
                hosted (with a one-time INFO log). Defaults to ``None``
                (in-memory local fallback).
        """
        super().__init__(
            source_id=source_id,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
            store_outputs=store_outputs,
        )

        self._history_limit = history_limit
        self._credential = credential
        self._endpoint = endpoint or os.environ.get(_ENV_FOUNDRY_PROJECT_ENDPOINT) or None
        self._backend: FoundryStorageProvider | InMemoryResponseProvider | None = None

        self._local_storage_root: Path | None = (
            Path(local_storage_root).resolve() if local_storage_root is not None else None
        )
        # Cache one ``FileHistoryProvider`` per (user_key, chat_key)
        # tuple. Bounded by the number of distinct isolation scopes the
        # process sees; cleared on ``aclose``.
        self._file_providers: dict[tuple[str, str], FileHistoryProvider] = {}
        self._hosted_local_root_warned = False
        if self._local_storage_root is not None and self.is_hosted_environment():
            self._warn_hosted_local_root_ignored()

        # Observability: number of ``save_messages`` calls dropped by
        # :class:`FoundryStorageError` from ``backend.create_response``.
        # Operators / health probes can read this attribute directly to
        # detect silent persistence loss; never decremented.
        self.failed_writes: int = 0

    @staticmethod
    def is_hosted_environment() -> bool:
        """Return ``True`` when running inside a Foundry Hosted Agent container.

        Detection uses the ``FOUNDRY_HOSTING_ENVIRONMENT`` environment
        variable, the same signal :class:`ResponsesAgentServerHost` uses to
        switch between hosted and local storage backends.
        """
        return bool(os.environ.get(_ENV_FOUNDRY_HOSTING_ENVIRONMENT))

    def _resolve_backend(self) -> FoundryStorageProvider | InMemoryResponseProvider:
        """Return the storage backend, constructing it lazily on first use.

        * If ``FOUNDRY_HOSTING_ENVIRONMENT`` is set, build a
          :class:`FoundryStorageProvider` (requires ``credential`` and a
          resolved ``endpoint``).
        * Otherwise, fall back to a process-local
          :class:`InMemoryResponseProvider` so dev/local runs work without
          additional configuration.
        """
        if self._backend is not None:
            return self._backend

        if self.is_hosted_environment():
            if self._credential is None:
                raise RuntimeError(
                    "FoundryHostedAgentHistoryProvider requires an async credential when running "
                    "inside a Foundry Hosted Agent container. Pass credential=... ."
                )
            if not self._endpoint:
                raise RuntimeError(
                    "FoundryHostedAgentHistoryProvider needs a Foundry project endpoint. Pass "
                    "endpoint=... or set the FOUNDRY_PROJECT_ENDPOINT environment variable."
                )
            self._backend = FoundryStorageProvider(
                credential=self._credential,
                settings=FoundryStorageSettings.from_endpoint(self._endpoint),
            )
            logger.debug(
                "FoundryHostedAgentHistoryProvider using FoundryStorageProvider against %s",
                self._endpoint,
            )
            return self._backend

        logger.info(
            "FOUNDRY_HOSTING_ENVIRONMENT is unset — FoundryHostedAgentHistoryProvider falling "
            "back to InMemoryResponseProvider for local development.",
        )
        self._backend = InMemoryResponseProvider()
        return self._backend

    async def aclose(self) -> None:
        """Release storage resources held by this provider.

        Safe to call multiple times. Closes the lazily-constructed
        backend if one was created and drops any cached file-history
        providers. ``InMemoryResponseProvider`` and
        ``FileHistoryProvider`` have no ``aclose`` and are closed
        implicitly on garbage collection.
        """
        self._file_providers.clear()
        if self._backend is None:
            return
        aclose = getattr(self._backend, "aclose", None)
        if aclose is not None:
            await aclose()
        self._backend = None

    def _warn_hosted_local_root_ignored(self) -> None:
        """Log (once) that ``local_storage_root`` is being ignored under hosted mode."""
        if self._hosted_local_root_warned:
            return
        self._hosted_local_root_warned = True
        logger.info(
            "FoundryHostedAgentHistoryProvider ignored local_storage_root=%s because "
            "FOUNDRY_HOSTING_ENVIRONMENT is set; Foundry storage takes precedence "
            "when hosted.",
            self._local_storage_root,
        )

    def _resolve_local_file_provider(
        self,
        isolation: IsolationContext | None,
    ) -> FileHistoryProvider | None:
        """Return a ``FileHistoryProvider`` for the current isolation, or ``None``.

        Returns ``None`` when ``local_storage_root`` is unset *or* the
        provider is running in hosted mode (in which case Foundry
        storage handles persistence). Otherwise builds — and caches —
        one provider per (user_key, chat_key) tuple, rooted at the
        sanitised ``{root}/{user_segment}/{chat_segment}`` directory.

        Raises:
            ValueError: If the resolved isolation directory escapes
                ``local_storage_root`` (defence in depth — the
                sanitisation should already prevent this).
        """
        if self._local_storage_root is None:
            return None
        if self.is_hosted_environment():
            self._warn_hosted_local_root_ignored()
            return None

        user_key = isolation.user_key if isolation is not None else None
        chat_key = isolation.chat_key if isolation is not None else None
        cache_key = (user_key or "", chat_key or "")
        cached = self._file_providers.get(cache_key)
        if cached is not None:
            return cached

        user_segment = _encode_isolation_segment(user_key)
        chat_segment = _encode_isolation_segment(chat_key)
        target_dir = (self._local_storage_root / user_segment / chat_segment).resolve()
        if not target_dir.is_relative_to(self._local_storage_root):
            raise ValueError(
                "Isolation segments resolved outside of local_storage_root: "
                f"user_key={user_key!r} chat_key={chat_key!r}"
            )

        provider = FileHistoryProvider(
            target_dir,
            source_id=f"{self.source_id}__file__{user_segment}__{chat_segment}",
            load_messages=self.load_messages,
            store_inputs=self.store_inputs,
            store_context_messages=self.store_context_messages,
            store_context_from=self.store_context_from,
            store_outputs=self.store_outputs,
        )
        self._file_providers[cache_key] = provider
        logger.debug(
            "FoundryHostedAgentHistoryProvider created file backend for isolation (user=%s, chat=%s) at %s",
            user_key,
            chat_key,
            target_dir,
        )
        return provider

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Load conversation history for the given Foundry response chain.

        Args:
            session_id: The Responses ``previous_response_id`` /
                ``conversation_id`` to anchor history on. When ``None`` /
                empty, an empty history is returned (fresh conversation).
            state: Unused — kept for ``HistoryProvider`` compatibility.
            **kwargs: Extensibility hook; ``isolation`` may be supplied
                explicitly to override the contextvar.

        Returns:
            The conversation history materialised as a list of
            :class:`agent_framework.Message`, oldest-first.

        Notes:
            History anchoring follows the Foundry response-id chain. The
            preferred anchor is the per-request ``previous_response_id``
            bound by the host via :func:`bind_request_context` — that's
            the prior turn's resp id, written by *this* provider's
            previous :meth:`save_messages` call, so the chain is
            guaranteed walkable. When unbound (e.g. local dev calling
            the provider directly), we fall back to the ``session_id``
            argument as long as it's ``resp_*``-shaped; opaque tokens
            (such as chat-isolation-key values) are skipped because the
            storage backend rejects them with HTTP 400 "Malformed
            identifier".

            When ``local_storage_root`` is configured (and the provider
            is running outside a Foundry Hosted Agent container), this
            method instead delegates to a per-isolation
            :class:`FileHistoryProvider` and ``session_id`` is used as
            the literal file stem.
        """
        isolation = kwargs.get("isolation") or _host_isolation() or get_current_isolation()
        file_provider = self._resolve_local_file_provider(isolation)
        if file_provider is not None:
            return await file_provider.get_messages(session_id, state=state, **kwargs)

        bound = get_current_request_context()
        # Prefer the host-bound previous_response_id over the session_id
        # the framework feeds in: the bound value is the id we ourselves
        # wrote on the previous turn, so we know it's storage-valid.
        anchor = bound.previous_response_id if bound is not None else None
        if anchor is None and session_id and session_id.startswith(("caresp_", "resp_")):
            anchor = session_id
        if anchor is None:
            # The Foundry Hosted Agent runtime stamps the previous turn's
            # response id into ``FOUNDRY_AGENT_SESSION_ID`` for the
            # following turn's container, so we can walk back from it
            # directly without keeping any cross-request state ourselves.
            env_session = os.environ.get("FOUNDRY_AGENT_SESSION_ID") or None
            if env_session and env_session.startswith(("caresp_", "resp_")):
                anchor = env_session
        if anchor is None:
            # No walkable anchor → fresh conversation, nothing to load.
            return []

        backend = self._resolve_backend()

        try:
            item_ids = await backend.get_history_item_ids(
                anchor,
                None,
                self._history_limit,
                isolation=isolation,
            )
        except (FoundryBadRequestError, FoundryResourceNotFoundError) as err:
            # 400 / 404 here means the anchor isn't storage-valid — treat
            # it as an empty history rather than failing the whole request.
            logger.debug(
                "get_messages: anchor %r rejected by storage (%s); returning empty history",
                anchor,
                type(err).__name__,
            )
            return []
        if not item_ids:
            return []

        items = await backend.get_items(item_ids, isolation=isolation)
        # ``get_items`` may return ``None`` placeholders for missing IDs.
        resolved = [item for item in items if item is not None]
        return _output_items_to_messages(resolved)

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Persist messages for ``session_id`` into Foundry storage.

        Unlike the standalone ``azure.ai.agentserver`` runtime — which
        owns response orchestration end-to-end and writes turns
        authoritatively — the Agent Framework hosting stack treats
        ``HistoryProvider`` as the *only* persistence path. Without this
        method actively writing, a deployed hosted agent would silently
        drop every turn.

        Strategy:

        * Use the host-bound ``response_id`` as the envelope id (mints
          a fresh ``caresp_*`` id when unbound, e.g. local dev).
        * Anchor the new write to the previous turn via
          ``previous_response_id``, walking the prior turn's history
          item ids forward so the full transcript stays visible.
        * Split items by role: ``"message"`` (user/system inputs) into
          ``input_items``, everything else (assistant outputs, tool
          calls, reasoning, ...) into ``response.output``.

        Args:
            session_id: The Responses ``previous_response_id`` /
                ``conversation_id`` the messages belong to.
            messages: The messages selected for persistence by the base
                ``HistoryProvider`` after-run hook.
            state: Unused — kept for ``HistoryProvider`` compatibility.
            **kwargs: Extensibility hook; ``isolation`` may be supplied
                explicitly to override the contextvar.

        Notes:
            When ``local_storage_root`` is configured (and the provider
            is running outside a Foundry Hosted Agent container), this
            method instead delegates to a per-isolation
            :class:`FileHistoryProvider` and ``session_id`` is used as
            the literal file stem. The Foundry response-chain stamping
            described above is bypassed entirely in that mode.
        """
        if not messages:
            return

        isolation = kwargs.get("isolation") or _host_isolation() or get_current_isolation()
        file_provider = self._resolve_local_file_provider(isolation)
        if file_provider is not None:
            await file_provider.save_messages(session_id, messages, state=state, **kwargs)
            return

        bound = get_current_request_context()
        # Prefer the host-bound response_id so the channel envelope and
        # the storage write agree on a single id per turn — which is
        # what makes the next turn's ``previous_response_id`` walkable.
        # Without a binding (e.g. local dev calling ``save_messages``
        # directly), fall back to a fresh Foundry-format response id.
        # Free-form ``resp_<uuid>`` ids carry no embedded partition key
        # and the storage backend rejects writes with a server error;
        # ``IdGenerator.new_response_id()`` mints a ``caresp_*`` id with
        # the partition-key segment the backend expects. The chain
        # walks only when ``session_id`` is itself a ``caresp_*``-shaped
        # value (i.e. a previous response id), matching the prefix the
        # ``ResponsesChannel`` factory uses.
        if bound is not None:
            response_id = bound.response_id
            previous_response_id = bound.previous_response_id
        else:
            if not session_id:
                return
            response_id = IdGenerator.new_response_id()
            previous_response_id = session_id if session_id.startswith(("caresp_", "resp_")) else None

        # Foundry session-bound containers: when ``FOUNDRY_AGENT_SESSION_ID``
        # is set the runtime stamps it to the previous turn's response id
        # so each new container can chain back to it directly. We don't
        # need to maintain any cross-request map ourselves.
        env_session = os.environ.get("FOUNDRY_AGENT_SESSION_ID") or None
        if previous_response_id is None and env_session and env_session.startswith(("caresp_", "resp_")):
            previous_response_id = env_session

        logger.debug(
            "save_messages: response_id=%r previous_response_id=%r isolation=%s",
            response_id,
            previous_response_id,
            "<set>" if isolation else "<None>",
        )
        backend = self._resolve_backend()

        # The agentserver runtime puts INBOUND items (user/system messages
        # the request sent in) in the envelope's ``input_items`` axis and
        # OUTBOUND items (assistant outputs, tool calls, reasoning) in
        # ``response.output``. See
        # ``_resolve_input_items_for_persistence`` (orchestrator.py:61) +
        # ``_extract_response_snapshot_from_events`` in
        # ``azure.ai.agentserver.responses``: ``input_items`` comes from
        # ``ctx.input_items`` (request inputs only); ``response.output``
        # is populated from the lifecycle event stream.
        #
        # Putting everything in ``input_items`` with ``response.output: []``
        # is a schema violation that the storage backend rejects with an
        # opaque HTTP 500. Split by role to mirror the runtime.
        all_items = _messages_to_output_items(list(messages), id_prefix=response_id)

        # Re-stamp every item id via ``IdGenerator`` so each carries a
        # Foundry-format ``{type-prefix}_<partitionKey><entropy>``
        # identifier, with the response_id as the partition-key hint
        # (co-locates each item with the response record). Free-form
        # ``{response_id}_itm_N`` ids are rejected by the storage
        # backend with an opaque HTTP 500 because the partition-key
        # extractor cannot parse them. ``IdGenerator.new_item_id``
        # dispatches by *Item* (input) type and returns ``None`` for
        # our *OutputItem* (storage) instances, so we dispatch by the
        # ``type`` discriminator string instead.
        ITEM_ID_FACTORY: dict[str, Any] = {
            "message": IdGenerator.new_message_item_id,
            "output_message": IdGenerator.new_output_message_item_id,
            "function_call": IdGenerator.new_function_call_item_id,
            "function_call_output": IdGenerator.new_function_call_output_item_id,
            "reasoning": IdGenerator.new_reasoning_item_id,
            "file_search_call": IdGenerator.new_file_search_call_item_id,
            "web_search_call": IdGenerator.new_web_search_call_item_id,
            "image_generation_call": IdGenerator.new_image_gen_call_item_id,
            "code_interpreter_call": IdGenerator.new_code_interpreter_call_item_id,
            "computer_call": IdGenerator.new_computer_call_item_id,
            "computer_call_output": IdGenerator.new_computer_call_output_item_id,
            "local_shell_call": IdGenerator.new_local_shell_call_item_id,
            "local_shell_call_output": IdGenerator.new_local_shell_call_output_item_id,
            "mcp_call": IdGenerator.new_mcp_call_item_id,
            "mcp_list_tools": IdGenerator.new_mcp_list_tools_item_id,
            "mcp_approval_request": IdGenerator.new_mcp_approval_request_item_id,
            "mcp_approval_response": IdGenerator.new_mcp_approval_response_item_id,
            "custom_tool_call": IdGenerator.new_custom_tool_call_item_id,
            "custom_tool_call_output": IdGenerator.new_custom_tool_call_output_item_id,
        }
        for item in all_items:
            factory = ITEM_ID_FACTORY.get(getattr(item, "type", "") or "")
            if factory is None:
                continue
            new_id = factory(response_id)
            # Plain attribute assignment — the SDK ``OutputItem`` models
            # are ``MutableMapping``s with ``__setattr__`` wired to dict
            # set, so this is expected to succeed for every type listed
            # above. The previous ``contextlib.suppress`` masked SDK
            # contract changes (next save would silently retain the
            # synthetic prefix-based id and the storage backend would
            # reject the entire ``create_response`` with HTTP 500).
            # Letting it raise surfaces those breakages to the test
            # suite instead.
            item.id = new_id  # type: ignore[attr-defined]

        input_items: list[Any] = []
        output_items: list[Any] = []
        for item in all_items:
            item_type = getattr(item, "type", None)
            if item_type == "message":
                input_items.append(item)
            else:
                # ``output_message``, tool calls, reasoning, etc. all
                # belong to the response output stream.
                output_items.append(item)

        # Walk the previous response's history chain so the new write
        # carries the full transcript forward. Without this, each turn
        # would only see the messages saved on that very turn.
        history_item_ids: list[str] | None = None
        if previous_response_id is not None:
            try:
                history_item_ids = await backend.get_history_item_ids(
                    previous_response_id,
                    None,
                    self._history_limit,
                    isolation=isolation,
                )
            except (FoundryBadRequestError, FoundryResourceNotFoundError) as err:
                # Don't let history fetch failures torpedo the write —
                # we still want to persist the new turn even if the
                # chain seed is unreachable for some reason.
                logger.warning(
                    "save_messages: failed to walk previous_response_id=%r (%s); writing new turn without history seed",
                    previous_response_id,
                    type(err).__name__,
                )

        # Mirror what the agentserver runtime serialises onto the wire
        # (see ``_extract_response_snapshot_from_events`` +
        # ``strip_nulls`` in
        # ``azure.ai.agentserver.responses.streaming._helpers``):
        #
        # * ``agent_reference`` (Required on the response envelope) —
        #   built from ``FOUNDRY_AGENT_NAME`` / ``FOUNDRY_AGENT_VERSION``,
        #   which the hosted platform sets per-deploy (sentinel fallback
        #   for local dev so the envelope stays well-formed).
        # * ``agent_session_id`` (S-038) — forcibly stamped by the
        #   runtime; sourced from ``FOUNDRY_AGENT_SESSION_ID``.
        # * ``conversation`` is intentionally omitted: the (user, chat)
        #   isolation headers are the Foundry storage partition key,
        #   and the chat-isolation-key value is opaque (the API
        #   returns "Malformed identifier"/HTTP 400 if used as a
        #   body-level ``conversation_id``).
        # * Per-item ``response_id`` / ``agent_reference`` are NOT
        #   stamped here — those B20/B21 defaults only apply to items
        #   inside ``response.output_item.added/done`` *events* (see
        #   ``_coerce_handler_event``); items inside ``input_items``
        #   and ``response.output`` go through ``to_output_item`` which
        #   never sets these fields, and the storage validator returns
        #   HTTP 400 ``invalid_payload`` when extras leak in.
        agent_name = os.environ.get("FOUNDRY_AGENT_NAME") or "agent-framework-host"
        agent_version = os.environ.get("FOUNDRY_AGENT_VERSION") or None
        agent_reference: dict[str, Any] = {"type": "agent_reference", "name": agent_name}
        if agent_version:
            agent_reference["version"] = agent_version

        agent_session_id = os.environ.get("FOUNDRY_AGENT_SESSION_ID") or None
        # ``model`` must be a real deployed model name — the storage
        # validator rejects arbitrary strings. Pull it from the
        # platform-provided ``MODEL_DEPLOYMENT_NAME`` (set in agent.yaml)
        # and fall back to ``AZURE_AI_MODEL_DEPLOYMENT_NAME`` for local
        # dev. When neither is set we omit the field entirely (it is
        # ``Optional[str]`` per the ResponseObject schema).
        model_deployment = (
            os.environ.get("MODEL_DEPLOYMENT_NAME") or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME") or None
        )

        # Build the wire payload to match exactly what the agentserver
        # runtime emits via ``_extract_response_snapshot_from_events``
        # for a synthetic ``status=completed`` snapshot:
        #
        #   {id, object, output, created_at, [model], agent_reference,
        #    status, completed_at, [agent_session_id]}
        #
        # ``previous_response_id`` is appended when chaining; the runtime
        # threads it through the same code path.
        now = int(time.time())
        response_body: dict[str, Any] = {
            "id": response_id,
            # SDK mirror: ``streaming/_helpers.py:244`` always stamps
            # ``response_id`` alongside ``id`` on the snapshot before it
            # reaches ``serialize_create_request``.
            "response_id": response_id,
            "object": "response",
            # S-040 auto-stamp: the orchestrator (``_orchestrator.py:1706``)
            # echoes ``background`` from the request to every response
            # envelope; storage rejects payloads that omit it.
            "background": False,
            # ``ResponseObject`` schema (``_models.py:13995``) declares
            # ``parallel_tool_calls: bool`` as REQUIRED. The SDK's synthetic
            # fallback path (``_build_events``) never sets it because it's
            # only invoked for failure recovery; real handler events carry
            # it through. Storage rejects payloads that omit it.
            "parallel_tool_calls": False,
            # Same story for ``instructions`` (``_models.py:13989``) —
            # required ``str | list[Item]`` field.
            "instructions": "",
            "output": [item.as_dict() for item in output_items],
            "created_at": now,
            "agent_reference": agent_reference,
            "status": "completed",
            "completed_at": now,
        }
        if model_deployment is not None:
            response_body["model"] = model_deployment
        if agent_session_id is not None:
            response_body["agent_session_id"] = agent_session_id
        if previous_response_id is not None:
            response_body["previous_response_id"] = previous_response_id
        response = ResponseObject(response_body)

        try:
            await backend.create_response(
                response,
                input_items=input_items,
                history_item_ids=history_item_ids,
                isolation=isolation,
            )
        except FoundryStorageError as exc:
            # Storage-validation failures (4xx ``invalid_payload`` /
            # ``not_found``, opaque 5xx) are best-effort losses: the
            # caller's run already produced output and we don't want to
            # crash the whole turn over a chain-write the user can't
            # recover from. They are still observable: every drop bumps
            # ``failed_writes`` (operators can poll it / surface in
            # health probes) and the full traceback + ``response_body``
            # is logged.
            #
            # Network / TLS / DNS errors, expired-credential 401/403s,
            # and bugs in the wire-payload builder above (e.g. a
            # required-field regression) deliberately propagate so they
            # surface to the caller and trigger retry / alerting paths
            # instead of being silently dropped here.
            self.failed_writes += 1
            err_body = getattr(exc, "response_body", None)
            logger.exception(
                "FoundryHostedAgentHistoryProvider.save_messages: storage rejected "
                "%d message(s) (response_id=%s, previous_response_id=%s, error_body=%s, "
                "failed_writes=%d).",
                len(messages),
                response_id,
                previous_response_id,
                err_body,
                self.failed_writes,
            )
            return
        logger.debug(
            "FoundryHostedAgentHistoryProvider.save_messages: persisted %d message(s) "
            "(response_id=%s, previous_response_id=%s).",
            len(messages),
            response_id,
            previous_response_id,
        )


# Re-export ``OutputItem`` for callers that want to construct test items
# without reaching into the SDK's ``models`` namespace directly.
__all__ = [
    "FoundryHostedAgentHistoryProvider",
    "OutputItem",
    "bind_request_context",
    "get_current_isolation",
    "get_current_request_context",
    "reset_current_isolation",
    "set_current_isolation",
]
