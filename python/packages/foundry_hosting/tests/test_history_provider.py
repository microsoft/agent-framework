# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for FoundryHostedAgentHistoryProvider."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import Content, HistoryProvider, Message
from azure.ai.agentserver.responses import (
    FoundryStorageProvider,
    InMemoryResponseProvider,
    IsolationContext,
)
from azure.ai.agentserver.responses.models import (
    OutputItem,
    OutputItemOutputMessage,
    OutputMessageContentOutputTextContent,
)
from azure.ai.agentserver.responses.store._foundry_errors import (  # pyright: ignore[reportPrivateUsage]
    FoundryBadRequestError,
)

from agent_framework_foundry_hosting import FoundryHostedAgentHistoryProvider
from agent_framework_foundry_hosting._history_provider import (  # pyright: ignore[reportPrivateUsage]
    get_current_isolation,
    reset_current_isolation,
    set_current_isolation,
)


def _with_backend(prov: FoundryHostedAgentHistoryProvider, backend: Any) -> FoundryHostedAgentHistoryProvider:
    """Inject a fake backend into ``prov`` so ``_resolve_backend`` returns it.

    Replaces the old ``backend=`` constructor parameter that was removed
    when the dual-backend model was collapsed onto ``FoundryStorageProvider``.
    """
    prov._backend = backend  # pyright: ignore[reportPrivateUsage]
    return prov


# region Helpers


def _make_text_item(item_id: str, text: str) -> OutputItemOutputMessage:
    return OutputItemOutputMessage(
        id=item_id,
        type="output_message",
        role="assistant",
        status="completed",
        content=[OutputMessageContentOutputTextContent(type="output_text", text=text, annotations=[])],
    )


def _make_fake_backend(
    *,
    history_ids: list[str] | None = None,
    items: list[OutputItem | None] | None = None,
) -> MagicMock:
    """Build a MagicMock matching the _StorageBackend protocol."""
    backend = MagicMock()

    async def _ids(*args: Any, **kwargs: Any) -> list[str]:
        return list(history_ids or [])

    async def _items(item_ids: Iterable[str], *, isolation: IsolationContext | None = None) -> list[OutputItem | None]:
        return list(items or [])

    backend.get_history_item_ids = AsyncMock(side_effect=_ids)
    backend.get_items = AsyncMock(side_effect=_items)
    backend.create_response = AsyncMock()
    return backend


class _FakeAccessToken:
    def __init__(self, token: str, *, expires_in: float = 3600.0) -> None:
        self.token = token
        self.expires_on = int(time.time() + expires_in)


class _FakeCredential:
    """Minimal AsyncTokenCredential stand-in."""

    def __init__(self, *, token: str = "fake-token", expires_in: float = 3600.0) -> None:
        self._token = token
        self._expires_in = expires_in
        self.calls: list[tuple[str, ...]] = []

    async def get_token(self, *scopes: str) -> _FakeAccessToken:
        self.calls.append(scopes)
        return _FakeAccessToken(self._token, expires_in=self._expires_in)


# region Construction


class TestConstruction:
    """Constructor + class-level invariants."""

    def test_defaults(self) -> None:
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), _make_fake_backend())
        assert isinstance(prov, HistoryProvider)
        assert prov.source_id == FoundryHostedAgentHistoryProvider.DEFAULT_SOURCE_ID
        assert prov.store_inputs is True
        assert prov.store_outputs is True
        assert prov.load_messages is True

    def test_is_hosted_environment_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        assert FoundryHostedAgentHistoryProvider.is_hosted_environment() is False
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
        assert FoundryHostedAgentHistoryProvider.is_hosted_environment() is True

    def test_endpoint_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.foundry.azure.com")
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), _make_fake_backend())
        assert prov._endpoint == "https://example.foundry.azure.com"  # pyright: ignore[reportPrivateUsage]


# region Backend resolution


class TestBackendResolution:
    """Lazy backend construction + local fallback."""

    def test_uses_explicit_backend(self) -> None:
        backend = _make_fake_backend()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        assert prov._resolve_backend() is backend  # pyright: ignore[reportPrivateUsage]

    def test_local_fallback_when_not_hosted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider()
        resolved = prov._resolve_backend()  # pyright: ignore[reportPrivateUsage]
        assert isinstance(resolved, InMemoryResponseProvider)
        # Cached on subsequent calls.
        assert prov._resolve_backend() is resolved  # pyright: ignore[reportPrivateUsage]

    def test_hosted_without_credential_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
        monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x.foundry.azure.com")
        prov = FoundryHostedAgentHistoryProvider()
        with pytest.raises(RuntimeError, match="requires an async credential"):
            prov._resolve_backend()  # pyright: ignore[reportPrivateUsage]

    def test_hosted_without_endpoint_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
        monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(credential=_FakeCredential())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="needs a Foundry project endpoint"):
            prov._resolve_backend()  # pyright: ignore[reportPrivateUsage]

    def test_hosted_builds_http_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
        monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x.foundry.azure.com")
        prov = FoundryHostedAgentHistoryProvider(credential=_FakeCredential())  # type: ignore[arg-type]
        resolved = prov._resolve_backend()  # pyright: ignore[reportPrivateUsage]
        assert isinstance(resolved, FoundryStorageProvider)


# region get_messages


class TestGetMessages:
    async def test_no_session_id_returns_empty(self) -> None:
        backend = _make_fake_backend(history_ids=["x"], items=[_make_text_item("x", "hi")])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        assert await prov.get_messages(None) == []
        assert await prov.get_messages("") == []
        backend.get_history_item_ids.assert_not_called()

    async def test_no_history_returns_empty(self) -> None:
        backend = _make_fake_backend(history_ids=[])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        assert await prov.get_messages("resp_123") == []
        backend.get_items.assert_not_called()

    async def test_loads_and_converts(self) -> None:
        items: list[OutputItem | None] = [_make_text_item("itm_1", "hello"), _make_text_item("itm_2", "world")]
        backend = _make_fake_backend(history_ids=["itm_1", "itm_2"], items=items)
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)

        messages = await prov.get_messages("resp_123")
        assert len(messages) == 2
        assert all(isinstance(m, Message) for m in messages)
        assert messages[0].text == "hello"
        assert messages[1].text == "world"

        backend.get_history_item_ids.assert_awaited_once()
        call = backend.get_history_item_ids.await_args
        assert call.args[0] == "resp_123"
        assert call.args[1] is None  # conversation_id
        assert call.args[2] == 100  # default history_limit

    async def test_drops_missing_items(self) -> None:
        backend = _make_fake_backend(
            history_ids=["a", "b", "c"],
            items=[_make_text_item("a", "first"), None, _make_text_item("c", "third")],
        )
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        messages = await prov.get_messages("resp_x")
        assert [m.text for m in messages] == ["first", "third"]

    async def test_history_limit_propagates(self) -> None:
        backend = _make_fake_backend(history_ids=[])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(history_limit=7), backend)
        # ``resp_*``-shaped session anchors directly; we expect a single
        # backend call carrying the configured limit.
        await prov.get_messages("resp_s")
        assert backend.get_history_item_ids.await_count == 1
        assert backend.get_history_item_ids.await_args.args[2] == 7

    async def test_non_resp_session_skips_storage_probe(self) -> None:
        """Non-``resp_*`` session ids (e.g. opaque chat-isolation keys)
        are not valid storage anchors — the provider must skip the
        backend probe entirely so we don't hit "Malformed identifier"
        HTTP 400s, returning an empty history instead.
        """
        backend = _make_fake_backend(history_ids=[])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        messages = await prov.get_messages("5leZSsJ3m1UtB-JW3m3iowFd5_zqP30SE0MmGUEkcGQ")
        assert messages == []
        backend.get_history_item_ids.assert_not_awaited()

    async def test_resp_probe_tolerates_400(self) -> None:
        """A 400 on the storage probe must not abort ``get_messages`` —
        the provider falls through to an empty history."""
        backend = _make_fake_backend()
        backend.get_history_item_ids.side_effect = FoundryBadRequestError("malformed", response_body=None)
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        messages = await prov.get_messages("resp_x")
        assert messages == []


# region IsolationContext


class TestIsolationContext:
    async def test_explicit_isolation_kwarg_wins(self) -> None:
        backend = _make_fake_backend(history_ids=[])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        explicit = IsolationContext(user_key="u-explicit", chat_key="c-explicit")
        await prov.get_messages("resp_s", isolation=explicit)
        assert backend.get_history_item_ids.await_args.kwargs["isolation"] is explicit

    async def test_contextvar_picked_up(self) -> None:
        backend = _make_fake_backend(history_ids=["a"], items=[_make_text_item("a", "x")])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        ctx = IsolationContext(user_key="u-1", chat_key="c-1")
        token = set_current_isolation(ctx)
        try:
            assert get_current_isolation() is ctx
            await prov.get_messages("resp_s")
        finally:
            reset_current_isolation(token)
        assert backend.get_history_item_ids.await_args.kwargs["isolation"] is ctx
        assert backend.get_items.await_args.kwargs["isolation"] is ctx

    async def test_no_isolation_when_unset(self) -> None:
        backend = _make_fake_backend(history_ids=[])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        await prov.get_messages("resp_s")
        assert backend.get_history_item_ids.await_args.kwargs["isolation"] is None

    async def test_host_isolation_keys_picked_up(self) -> None:
        """The host's ASGI middleware lifts the
        ``x-agent-{user,chat}-isolation-key`` headers into a contextvar
        exposed by ``agent_framework_hosting``. The provider lifts that
        into its own ``IsolationContext`` so the storage call carries
        the platform partition keys without channels having to forward
        anything (or even know the headers exist)."""
        pytest.importorskip("agent_framework_hosting")
        from agent_framework_hosting import (
            IsolationKeys,
            reset_current_isolation_keys,
            set_current_isolation_keys,
        )

        backend = _make_fake_backend(history_ids=["a"], items=[_make_text_item("a", "x")])
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        token = set_current_isolation_keys(IsolationKeys(user_key="u-3", chat_key="c-3"))
        try:
            await prov.get_messages("resp_s")
        finally:
            reset_current_isolation_keys(token)
        applied = backend.get_history_item_ids.await_args.kwargs["isolation"]
        assert applied is not None
        assert applied.user_key == "u-3"
        assert applied.chat_key == "c-3"


# region save_messages


class TestSaveMessages:
    async def test_save_messages_writes_to_backend_when_bound(self) -> None:
        """``save_messages`` writes a ``create_response`` envelope using
        the host-bound response_id when present.

        The host's ``_bind_request_context`` plumbs the channel-minted
        ``response_id`` (and prior turn's ``previous_response_id``) into
        the provider via :func:`bind_request_context`, so the channel
        envelope and the storage write share a single id per turn —
        which is what makes the next turn's ``previous_response_id``
        walkable.
        """
        from agent_framework_foundry_hosting import bind_request_context

        backend = _make_fake_backend()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        msg = Message(role="assistant", contents=[Content.from_text("hello")])
        with bind_request_context(response_id="resp_bound_1", previous_response_id=None):
            await prov.save_messages("session-x", [msg])

        backend.create_response.assert_awaited_once()
        call = backend.create_response.await_args
        response = call.args[0]
        assert response.id == "resp_bound_1"
        # Conversation is intentionally omitted — Foundry isolation
        # headers handle partitioning; cross-turn chaining is via the
        # response-id chain only.
        assert response.conversation is None
        # Assistant outputs go on ``response.output``, not ``input_items``
        # — mirrors the agentserver runtime split (see
        # ``_resolve_input_items_for_persistence``).
        assert call.kwargs["input_items"] == []
        output = response.output or []
        assert len(output) == 1
        assert output[0]["type"] == "output_message"

    async def test_save_messages_falls_back_to_session_id_when_unbound(self) -> None:
        """Without a host binding (e.g. local dev), ``save_messages``
        mints a fresh ``resp_*`` envelope and only chains when the
        ``session_id`` is itself ``resp_*``-shaped."""
        backend = _make_fake_backend()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        msg = Message(role="user", contents=[Content.from_text("hi")])
        await prov.save_messages("resp_prev", [msg])

        backend.create_response.assert_awaited_once()
        call = backend.create_response.await_args
        response = call.args[0]
        assert response.id.startswith("caresp_")
        # Provider walked the prior chain to seed history_item_ids; the
        # fake backend returns ``[]`` so this stays empty but the call
        # was made.
        assert backend.get_history_item_ids.await_count == 1
        assert backend.get_history_item_ids.await_args.args[0] == "resp_prev"

    async def test_save_messages_empty_short_circuits(self) -> None:
        backend = _make_fake_backend()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        await prov.save_messages("s", [])
        backend.create_response.assert_not_called()

    async def test_save_messages_no_session_short_circuits(self) -> None:
        """No session id and no host binding → nothing to anchor against,
        skip the write."""
        backend = _make_fake_backend()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        await prov.save_messages(None, [Message(role="user", contents=[Content.from_text("hi")])])
        backend.create_response.assert_not_called()

    async def test_save_messages_swallows_backend_errors(self) -> None:
        """Persistence is best-effort — backend failures must NOT propagate.

        A successful agent turn that hits a transient storage error
        (RBAC propagation lag, throttling, …) should still return a 2xx
        to the caller; we only log so operators can spot systematic
        failures.
        """
        backend = _make_fake_backend()
        backend.create_response.side_effect = RuntimeError("simulated 500 from storage")
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        # Must not raise.
        await prov.save_messages("resp_session_x", [Message(role="user", contents=[Content.from_text("hi")])])
        backend.create_response.assert_awaited_once()

    async def test_save_then_get_round_trip_via_in_memory_backend(self) -> None:
        """End-to-end save→get round-trip through ``InMemoryResponseProvider``.

        Mirrors the host-bound multi-turn flow: turn 1 binds a fresh
        response id; turn 2 binds a new response id with the prior id
        as ``previous_response_id``. ``get_messages`` on turn 2 is
        called with the prior anchor and must return both turns.
        """
        from agent_framework_foundry_hosting import bind_request_context

        backend = InMemoryResponseProvider()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)

        with bind_request_context(response_id="resp_turn1", previous_response_id=None):
            await prov.save_messages(
                "resp_turn1",
                [Message(role="user", contents=[Content.from_text("ping")])],
            )

        with bind_request_context(response_id="resp_turn2", previous_response_id="resp_turn1"):
            history = await prov.get_messages("resp_turn1")
            assert [m.text for m in history] == ["ping"]
            await prov.save_messages(
                "resp_turn2",
                [Message(role="assistant", contents=[Content.from_text("pong")])],
            )

        # Final read for turn 3: walking turn 2 must reveal both turns.
        with bind_request_context(response_id="resp_turn3", previous_response_id="resp_turn2"):
            messages = await prov.get_messages("resp_turn2")
        assert [m.text for m in messages] == ["ping", "pong"]
        roles = [getattr(m.role, "value", m.role) for m in messages]
        assert roles == ["user", "assistant"]


# region aclose


class TestAclose:
    async def test_closes_backend_with_aclose(self) -> None:
        # Provider always closes whatever backend is currently bound;
        # the dual-mode (external vs owned) distinction was dropped
        # along with the ``backend=`` constructor param.
        backend = _make_fake_backend()
        backend.aclose = AsyncMock()
        prov = _with_backend(FoundryHostedAgentHistoryProvider(), backend)
        prov._resolve_backend()  # pyright: ignore[reportPrivateUsage]
        await prov.aclose()
        backend.aclose.assert_awaited_once()

    async def test_aclose_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider()
        prov._resolve_backend()  # pyright: ignore[reportPrivateUsage]
        await prov.aclose()
        await prov.aclose()  # idempotent — second call is a no-op


# region Local file storage option


class TestLocalFileStorage:
    """`local_storage_root` swaps the in-memory local fallback for a
    per-isolation :class:`FileHistoryProvider` so dev runs persist
    across process restarts."""

    async def test_unset_keeps_in_memory_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider()
        assert prov._resolve_local_file_provider(None) is None  # pyright: ignore[reportPrivateUsage]
        assert isinstance(
            prov._resolve_backend(),  # pyright: ignore[reportPrivateUsage]
            InMemoryResponseProvider,
        )

    async def test_creates_per_isolation_provider(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
        iso = IsolationContext(user_key="alice", chat_key="chat-1")

        fp = prov._resolve_local_file_provider(iso)  # pyright: ignore[reportPrivateUsage]
        assert fp is not None
        # Cached on subsequent calls for the same (user, chat).
        assert prov._resolve_local_file_provider(iso) is fp  # pyright: ignore[reportPrivateUsage]
        # Different isolation → different provider rooted at a different dir.
        other = prov._resolve_local_file_provider(  # pyright: ignore[reportPrivateUsage]
            IsolationContext(user_key="bob", chat_key="chat-1"),
        )
        assert other is not None and other is not fp
        assert fp.storage_path != other.storage_path
        assert fp.storage_path == (tmp_path / "alice" / "chat-1").resolve()

    async def test_missing_isolation_uses_sentinel_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
        fp = prov._resolve_local_file_provider(None)  # pyright: ignore[reportPrivateUsage]
        assert fp is not None
        assert fp.storage_path == (tmp_path / "~none" / "~none").resolve()

    async def test_unsafe_isolation_segments_are_encoded(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
        iso = IsolationContext(user_key="../escape", chat_key="ok-chat")
        fp = prov._resolve_local_file_provider(iso)  # pyright: ignore[reportPrivateUsage]
        assert fp is not None
        # Encoded segment never contains a ``/`` and never escapes the root.
        assert fp.storage_path.is_relative_to(tmp_path.resolve())
        assert "../" not in str(fp.storage_path)
        # Encoded segments use the reserved ``~iso-`` prefix.
        parts = fp.storage_path.relative_to(tmp_path.resolve()).parts
        assert parts[0].startswith("~iso-")
        assert parts[1] == "ok-chat"

    async def test_hosted_mode_ignores_local_storage_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "1")
        with caplog.at_level("INFO", logger="agent_framework_foundry_hosting._history_provider"):
            prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
            # File provider is never resolved when hosted.
            assert prov._resolve_local_file_provider(None) is None  # pyright: ignore[reportPrivateUsage]
        assert any("ignored local_storage_root" in record.message for record in caplog.records)

    async def test_get_and_save_round_trip_via_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
        iso = IsolationContext(user_key="alice", chat_key="chat-1")

        msgs = [
            Message(role="user", contents=["hello"]),
            Message(role="assistant", contents=["hi back"]),
        ]
        await prov.save_messages("conv-1", msgs, isolation=iso)

        # File exists at the expected nested path with session_id as stem.
        expected_path = tmp_path / "alice" / "chat-1" / "conv-1.jsonl"
        assert expected_path.exists()
        # Two JSONL records (one per message).
        assert len([line for line in expected_path.read_text().splitlines() if line.strip()]) == 2

        loaded = await prov.get_messages("conv-1", isolation=iso)
        assert [m.text for m in loaded] == ["hello", "hi back"]

        # Different isolation → different file → independent history.
        bob_loaded = await prov.get_messages(
            "conv-1",
            isolation=IsolationContext(user_key="bob", chat_key="chat-1"),
        )
        assert bob_loaded == []

    async def test_session_id_with_special_chars_is_sanitised_by_file_provider(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        # The wrapper passes ``session_id`` through unchanged; the
        # delegate ``FileHistoryProvider`` is responsible for sanitising
        # it. This test just confirms the delegation works for a
        # non-trivial id without raising.
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
        msgs = [Message(role="user", contents=["hi"])]
        await prov.save_messages("conv:with:colons", msgs)
        loaded = await prov.get_messages("conv:with:colons")
        assert [m.text for m in loaded] == ["hi"]

    async def test_aclose_clears_file_provider_cache(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
        prov = FoundryHostedAgentHistoryProvider(local_storage_root=tmp_path)
        prov._resolve_local_file_provider(IsolationContext(user_key="alice"))  # pyright: ignore[reportPrivateUsage]
        assert prov._file_providers  # pyright: ignore[reportPrivateUsage]
        await prov.aclose()
        assert not prov._file_providers  # pyright: ignore[reportPrivateUsage]


# region Shared module re-exports


class TestSharedReExports:
    """`_responses.py` must re-export the conversion helpers so tests and
    downstream code that historically imported them keep working."""

    def test_responses_re_exports_helpers(self) -> None:
        # All of these used to live in ``_responses``; after the
        # refactor they live in ``_shared`` but are re-exported.
        from agent_framework_foundry_hosting import (
            _responses,  # pyright: ignore[reportPrivateUsage]
            _shared,  # pyright: ignore[reportPrivateUsage]
        )

        for name in (
            "_arguments_to_str",
            "_convert_message_content",
            "_convert_output_message_content",
            "_item_to_message",
            "_items_to_messages",
            "_output_item_to_message",
            "_output_items_to_messages",
        ):
            assert getattr(_responses, name) is getattr(_shared, name), (
                f"{name} should be re-exported from _responses for backwards compat"
            )


# region Full AF ↔ Foundry round-trip via InMemoryResponseProvider


class TestAfFoundryRoundTrip:
    """Round-trip two AF :class:`Message` instances through the Foundry SDK
    types and back via the real :class:`InMemoryResponseProvider` backend.

    This is the same backend the provider uses in its local-fallback path
    (i.e. the one that runs whenever ``FOUNDRY_HOSTING_ENVIRONMENT`` is
    unset), so this test gives us coverage of the
    "AF → Foundry SDK shape → storage → Foundry SDK shape → AF" pipeline
    using exactly the production conversion code in :mod:`._shared`.
    """

    @staticmethod
    def _af_message(text: str, item_id: str) -> tuple[Message, OutputItem]:
        """Build an AF ``Message`` and the matching Foundry ``OutputItem``.

        Both messages are assistant ``output_message`` items because that's
        the only OutputItem variant we round-trip through here — this test
        exercises the conversion path, not every input/output shape.
        """
        from agent_framework import Content

        af_message = Message(role="assistant", contents=[Content.from_text(text)])
        foundry_item = OutputItemOutputMessage(
            id=item_id,
            type="output_message",
            role="assistant",
            status="completed",
            content=[OutputMessageContentOutputTextContent(type="output_text", text=text, annotations=[])],
        )
        return af_message, foundry_item

    async def test_two_messages_round_trip_through_in_memory_backend(self) -> None:
        from azure.ai.agentserver.responses.models import ResponseObject

        # 1. Start from two AF Messages (the "outside world" shape).
        original_first, foundry_first = self._af_message("First message: 2 + 2 equals 4.", "itm_1")
        original_second, foundry_second = self._af_message("Second message: 3 + 5 equals 8.", "itm_2")

        # 2. Hand the Foundry items to the real in-memory storage backend
        #    via the same ``create_response`` API the agent-server runtime
        #    uses on every successful turn. Passing them as ``input_items``
        #    is enough — the in-memory backend records each item under its
        #    own id and exposes it via ``get_history_item_ids``.
        backend = InMemoryResponseProvider()
        response = ResponseObject(
            id="resp_round_trip",
            object="response",
            status="completed",
            model="test-model",
            created_at=0,
        )
        await backend.create_response(
            response,
            input_items=[foundry_first, foundry_second],
            history_item_ids=None,
        )

        # 3. Wire the provider to the seeded backend (no HTTP, no
        #    credential needed — this exercises the local-mode contract).
        provider = _with_backend(FoundryHostedAgentHistoryProvider(), backend)

        # 4. Retrieve via the public API. Internally this fans out:
        #    backend.get_history_item_ids → backend.get_items
        #    → ``_output_items_to_messages`` from ``_shared`` → AF Messages.
        retrieved = await provider.get_messages("resp_round_trip")

        # 5. Round-trip preserves role + text content for both messages.
        assert len(retrieved) == 2
        assert all(isinstance(m, Message) for m in retrieved)

        assert retrieved[0].role == original_first.role
        assert retrieved[0].text == original_first.text == "First message: 2 + 2 equals 4."

        assert retrieved[1].role == original_second.role
        assert retrieved[1].text == original_second.text == "Second message: 3 + 5 equals 8."

    async def test_additional_properties_round_trip_through_in_memory_backend(self) -> None:
        """End-to-end audit/replay verification via the public provider API.

        Seeds the in-memory backend with an :class:`OutputItemOutputMessage`
        carrying:

        * a non-default item id;
        * declared content fields (``output_text`` with annotations);
        * a non-default ``status``;
        * an arbitrary, undeclared top-level key
          (``"audit_trace_id": "..."``) — i.e. the kind of opaque field
          Foundry might layer on for audit/replay;
        * an undeclared key on a content child
          (``"vendor_metadata": {...}``).

        Reads the items back through ``get_messages`` (which captures the
        :data:`RAW_KEY` snapshot), then writes them via ``save_messages``
        (which re-emits via the snapshot), then reads again and asserts
        every field above survives the storage → AF → storage hop. Without
        the raw-snapshot path, the second read would see synthesised
        text-only items with newly-minted ids and lose every audit field.
        """
        from azure.ai.agentserver.responses.models import ResponseObject

        from agent_framework_foundry_hosting._shared import EXTRAS_KEY, RAW_KEY  # pyright: ignore[reportPrivateUsage]

        backend = InMemoryResponseProvider()
        original_id = "itm_audit_001"
        seed_item = OutputItemOutputMessage(
            id=original_id,
            type="output_message",
            role="assistant",
            status="completed",
            content=[
                OutputMessageContentOutputTextContent(
                    type="output_text",
                    text="The final answer is 42.",
                    annotations=[],
                )
            ],
        )
        # Layer audit fields onto the SDK model directly — these are the
        # "extras" that pyright would warn about but the runtime
        # round-trips faithfully via as_dict().
        seed_item["audit_trace_id"] = "trace-abc-123"
        seed_item.content[0]["vendor_metadata"] = {"score": 0.97, "model": "gpt-x"}

        seed_response = ResponseObject(
            id="resp_audit",
            object="response",
            status="completed",
            model="test-model",
            created_at=0,
        )
        await backend.create_response(seed_response, input_items=[seed_item], history_item_ids=None)

        provider = _with_backend(FoundryHostedAgentHistoryProvider(), backend)

        # 1. Read back — provider stamps the RAW_KEY snapshot onto the
        #    AF Message's additional_properties.
        first_read = await provider.get_messages("resp_audit")
        assert len(first_read) == 1
        msg = first_read[0]
        raw = msg.additional_properties[EXTRAS_KEY][RAW_KEY]
        assert raw["id"] == original_id
        assert raw["type"] == "output_message"
        assert raw["audit_trace_id"] == "trace-abc-123"
        assert raw["content"][0]["text"] == "The final answer is 42."
        assert raw["content"][0]["vendor_metadata"] == {"score": 0.97, "model": "gpt-x"}

        # 2. Write back — this is where the snapshot-driven write path
        #    matters: save_messages mints a new response_id but must
        #    re-emit the SDK item from the captured raw shape.
        from agent_framework_foundry_hosting import bind_request_context

        with bind_request_context(response_id="resp_audit_replay", previous_response_id="resp_audit"):
            await provider.save_messages("resp_audit_replay", [msg])

        # 3. Inspect what was stored. We walk the new response id and
        #    expect to see the prior history seeded plus the replayed
        #    message — proof the snapshot survived storage→AF→storage.
        item_ids = await backend.get_history_item_ids(
            previous_response_id="resp_audit_replay", conversation_id=None, limit=20
        )
        assert len(item_ids) >= 1
        stored_items = await backend.get_items(item_ids)
        # Find the replayed item (its content text matches).
        replay = next(
            dict(it)
            for it in stored_items
            if it is not None
            and dict(it).get("type") == "output_message"
            and dict(it).get("audit_trace_id") == "trace-abc-123"
            and dict(it).get("id") != original_id
        )
        stored_dict = replay
        assert stored_dict["type"] == "output_message"
        assert stored_dict["status"] == "completed"
        assert stored_dict["audit_trace_id"] == "trace-abc-123"
        assert stored_dict["content"][0]["text"] == "The final answer is 42."
        assert stored_dict["content"][0]["vendor_metadata"] == {"score": 0.97, "model": "gpt-x"}
        # The replay item id is regenerated per write turn (caller
        # supplies it), so it must NOT equal the original — that's how
        # we know the snapshot path didn't naively echo back the seed.
        assert stored_dict["id"] != original_id

        # 4. Final read confirms the entire chain is observable through
        #    the public AF surface. Walking the new response id returns
        #    both the seeded prior item and the replayed one.
        second_read = await provider.get_messages("resp_audit_replay")
        assert len(second_read) >= 1
        # Find the replayed message (matches the seed text + audit field).
        replayed_msg = next(
            m
            for m in second_read
            if EXTRAS_KEY in m.additional_properties
            and m.additional_properties[EXTRAS_KEY].get(RAW_KEY, {}).get("audit_trace_id") == "trace-abc-123"
        )
        replayed_raw = replayed_msg.additional_properties[EXTRAS_KEY][RAW_KEY]
        assert replayed_raw["content"][0]["vendor_metadata"] == {"score": 0.97, "model": "gpt-x"}


# region Integration tests against a real Foundry project
#
# Required environment variables:
#
# * ``FOUNDRY_PROJECT_ENDPOINT`` — base URL of a real Foundry project,
#   e.g. ``https://my-proj.services.ai.azure.com``.
# * Azure auth (any one of):
#   - ``az login`` (recommended for local dev)
#   - ``AZURE_CLIENT_ID`` + ``AZURE_CLIENT_SECRET`` + ``AZURE_TENANT_ID``
#   - Managed identity when on Azure
#   The identity needs at least the ``Azure AI User`` role on the project.
#
# Optional (enables the seeded-history test):
#
# * ``FOUNDRY_HOSTING_PREVIOUS_RESPONSE_ID`` — a real response id with attached items.
# * ``FOUNDRY_HOSTING_CONVERSATION_ID`` — alternative.
# * ``FOUNDRY_HOSTING_USER_ISOLATION_KEY`` /
#   ``FOUNDRY_HOSTING_CHAT_ISOLATION_KEY`` — set if your project enforces isolation.
#
# Run with: ``uv run pytest -m integration packages/foundry_hosting/tests/test_history_provider.py``


_FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")

_skip_if_no_foundry_endpoint = pytest.mark.skipif(
    not _FOUNDRY_PROJECT_ENDPOINT or _FOUNDRY_PROJECT_ENDPOINT == "https://test-project.services.ai.azure.com/",
    reason=(
        "FOUNDRY_PROJECT_ENDPOINT not set to a real Foundry project; "
        "skipping FoundryHostedAgentHistoryProvider integration tests."
    ),
)


def _isolation_from_env() -> IsolationContext | None:
    user_key = os.getenv("FOUNDRY_HOSTING_USER_ISOLATION_KEY")
    chat_key = os.getenv("FOUNDRY_HOSTING_CHAT_ISOLATION_KEY")
    if not user_key and not chat_key:
        return None
    return IsolationContext(user_key=user_key, chat_key=chat_key)


@pytest.fixture
async def _live_credential() -> object:
    """Yield a :class:`AzureCliCredential` and close it afterwards."""
    # Imported lazily so collection still works in environments without
    # ``azure-identity`` available (e.g. minimal CI matrices).
    from azure.identity.aio import AzureCliCredential

    cred = AzureCliCredential()
    try:
        yield cred
    finally:
        await cred.close()


class TestLiveFoundryStorage:
    """End-to-end tests against a real Foundry project's storage HTTP API.

    These tests are gated behind ``@pytest.mark.integration`` so the
    default ``pytest -m 'not integration'`` run skips them; they are
    additionally skipped unless ``FOUNDRY_PROJECT_ENDPOINT`` points at a
    real project.
    """

    @pytest.mark.flaky
    @pytest.mark.integration
    @_skip_if_no_foundry_endpoint
    async def test_get_messages_unknown_response_id_returns_empty(self, _live_credential: object) -> None:
        """A brand-new previous_response_id should yield an empty history.

        The native HTTP backend treats a 404 from the storage ``item_ids``
        endpoint as "no prior history" rather than raising, so a freshly
        bootstrapped client never crashes on its first request. This test
        proves that contract end-to-end against the live service.
        """
        isolation = _isolation_from_env()
        provider = FoundryHostedAgentHistoryProvider(
            endpoint=_FOUNDRY_PROJECT_ENDPOINT,
            credential=_live_credential,  # type: ignore[arg-type]
        )
        try:
            messages = await provider.get_messages(
                "resp_does_not_exist_integration_smoke",
                isolation=isolation,
            )
        finally:
            await provider.aclose()

        assert messages == []

    @pytest.mark.flaky
    @pytest.mark.integration
    @_skip_if_no_foundry_endpoint
    @pytest.mark.skipif(
        not os.getenv("FOUNDRY_HOSTING_PREVIOUS_RESPONSE_ID") and not os.getenv("FOUNDRY_HOSTING_CONVERSATION_ID"),
        reason=(
            "Set FOUNDRY_HOSTING_PREVIOUS_RESPONSE_ID or "
            "FOUNDRY_HOSTING_CONVERSATION_ID to a real seeded conversation to "
            "enable this test."
        ),
    )
    async def test_get_messages_returns_real_history(self, _live_credential: object) -> None:
        """When pointed at a real seeded conversation we should get Messages back."""
        previous_response_id = os.getenv("FOUNDRY_HOSTING_PREVIOUS_RESPONSE_ID") or ""
        conversation_id = os.getenv("FOUNDRY_HOSTING_CONVERSATION_ID")
        isolation = _isolation_from_env()

        provider = FoundryHostedAgentHistoryProvider(
            endpoint=_FOUNDRY_PROJECT_ENDPOINT,
            credential=_live_credential,  # type: ignore[arg-type]
            history_limit=20,
        )
        try:
            # ``get_messages`` is keyed on ``session_id`` (== previous_response_id)
            # so we pass that as the primary lookup; conversation_id is the
            # fallback when only a conversation id is configured.
            messages = await provider.get_messages(
                previous_response_id or (conversation_id or ""),
                isolation=isolation,
            )
        finally:
            await provider.aclose()

        assert isinstance(messages, list)
        assert messages, "Expected at least one message in the seeded history"
        assert all(isinstance(m, Message) for m in messages)

    @pytest.mark.flaky
    @pytest.mark.integration
    @_skip_if_no_foundry_endpoint
    async def test_invoke_then_read_and_write_with_isolation(self, _live_credential: object) -> None:
        """Invoke a deployed Foundry hosted agent, then round-trip via storage.

        This test exercises the realistic, fully-permissioned path:

        1. Use :class:`FoundryAgent` to invoke the deployed
           ``agent-framework-hosting-sample`` (version 10) hosted agent
           with an explicit ``isolation_key``. The Foundry runtime
           creates the response + history items inside the storage
           backend on the user's behalf.
        2. Read the resulting history back through our own native HTTP
           :class:`FoundryHostedAgentHistoryProvider` using the matching
           :class:`IsolationContext`. This is the production read path
           that DevUI / external clients use to render conversation
           transcripts.
        3. Best-effort: try to APPEND two more items to the same
           response via :class:`FoundryStorageProvider` write API. The
           storage write path is normally callable only from inside the
           agent-server container's runtime identity (Foundry strips
           the user's bearer token at the runtime boundary), so a 403
           here is expected for ordinary user principals; we skip the
           write-side assertions in that case rather than failing.
        """
        from agent_framework_foundry import FoundryAgent
        from azure.ai.agentserver.responses import (
            FoundryStorageProvider,
            FoundryStorageSettings,
        )
        from azure.ai.agentserver.responses.store._foundry_errors import (  # pyright: ignore[reportPrivateImportUsage]
            FoundryApiError,
        )

        # Per-run-unique isolation key keeps each test run in its own
        # tenant partition so concurrent runs (CI matrix, retries) don't
        # collide.
        isolation_key = f"af-hosting-roundtrip-{int(time.time())}"
        isolation = IsolationContext(user_key=isolation_key, chat_key=isolation_key)

        # 1. Invoke the deployed hosted agent.
        agent = FoundryAgent(
            project_endpoint=_FOUNDRY_PROJECT_ENDPOINT,
            agent_name="agent-framework-hosting-sample",
            agent_version="10",
            credential=_live_credential,  # type: ignore[arg-type]
            allow_preview=True,
            default_options={"isolation_key": isolation_key},
        )
        # ``create_session()`` makes a fresh local session with no
        # ``service_session_id`` set; the FoundryAgent's
        # ``_prepare_run_context`` will lazily call
        # ``project_client.beta.agents.create_session`` under our
        # isolation key on first run.
        session = agent.create_session()
        prompt = "Please reply with exactly: 'Round-trip ack.'"
        result = await agent.run(prompt, session=session)

        assert result.text, "FoundryAgent.run returned an empty response"
        response_id = result.response_id
        assert isinstance(response_id, str) and response_id, "Expected a non-empty response_id from FoundryAgent.run"

        # 2. Read history back via the native HTTP provider with the
        #    same isolation context. Try both the response_id and the
        #    service_session_id Foundry created on our behalf — depending
        #    on the runtime's storage layout, history may be anchored to
        #    either.
        service_session_id = session.service_session_id
        candidates = [c for c in (response_id, service_session_id) if c]

        reader = FoundryHostedAgentHistoryProvider(
            endpoint=_FOUNDRY_PROJECT_ENDPOINT,
            credential=_live_credential,  # type: ignore[arg-type]
            history_limit=20,
        )
        try:
            messages_after_invoke: list[Message] = []
            for cand in candidates:
                msgs = await reader.get_messages(cand, isolation=isolation)
                if msgs:
                    messages_after_invoke = msgs
                    break
        finally:
            await reader.aclose()

        # The read path returning a well-typed list (possibly empty if
        # Foundry compacts items out of the response chain we queried)
        # is enough to confirm the isolation header path works end-to-end.
        assert all(isinstance(m, Message) for m in messages_after_invoke)

        # If we got messages back, every one should carry the lossless
        # raw-snapshot under additional_properties[EXTRAS_KEY][RAW_KEY] —
        # this is what guarantees audit/replay round-trip through the
        # storage backend. Without it, a write-back would synthesise a
        # text-only item and lose every audit field.
        if messages_after_invoke:
            from agent_framework_foundry_hosting._shared import (  # pyright: ignore[reportPrivateUsage]
                EXTRAS_KEY,
                RAW_KEY,
            )

            for m in messages_after_invoke:
                extras = m.additional_properties.get(EXTRAS_KEY) or {}
                assert RAW_KEY in extras, f"Live read message missing raw snapshot: {m!r}"
                raw = extras[RAW_KEY]
                # Snapshot must carry the discriminator + id — the two
                # fields save_messages relies on to rebuild the SDK item.
                assert isinstance(raw, dict)
                assert "type" in raw and "id" in raw

        # 3. Best-effort write: create a fresh response under the same
        #    isolation key carrying two known items, then read it back
        #    via the native HTTP provider. Skip the write-side
        #    assertions if Foundry rejects the call with 403 (expected
        #    when the runtime is the only authorised writer).
        from azure.ai.agentserver.responses.models import ResponseObject

        write_response_id = f"resp_af_write_{int(time.time())}"
        _, foundry_first = TestAfFoundryRoundTrip._af_message(
            "Appended message 1: 2 + 2 equals 4.", f"{write_response_id}_itm_1"
        )
        _, foundry_second = TestAfFoundryRoundTrip._af_message(
            "Appended message 2: 3 + 5 equals 8.", f"{write_response_id}_itm_2"
        )

        write_succeeded = False
        writer = FoundryStorageProvider(
            credential=_live_credential,  # type: ignore[arg-type]
            settings=FoundryStorageSettings.from_endpoint(_FOUNDRY_PROJECT_ENDPOINT),
        )
        try:
            await writer.create_response(
                ResponseObject(
                    id=write_response_id,
                    object="response",
                    status="completed",
                    model="agent",
                    created_at=int(time.time()),
                ),
                input_items=[foundry_first, foundry_second],
                history_item_ids=None,
                isolation=isolation,
            )
            write_succeeded = True
        except FoundryApiError as exc:
            if "403" not in str(exc):
                raise
            # Foundry strips the user bearer token at the runtime
            # boundary, so external principals can't write directly to
            # storage. The container's MSI is the authorised writer.
            pytest.skip("Foundry rejected external storage write with 403 (expected outside container).")
        finally:
            await writer.aclose()

        # Re-read and verify our two appended items now show up.
        if not write_succeeded:  # pragma: no cover — defensive; pytest.skip already raised
            return
        reader2 = FoundryHostedAgentHistoryProvider(
            endpoint=_FOUNDRY_PROJECT_ENDPOINT,
            credential=_live_credential,  # type: ignore[arg-type]
            history_limit=20,
        )
        try:
            messages_after_write = await reader2.get_messages(write_response_id, isolation=isolation)
        finally:
            await reader2.aclose()

        appended_texts = {m.text for m in messages_after_write}
        assert "Appended message 1: 2 + 2 equals 4." in appended_texts
        assert "Appended message 2: 3 + 5 equals 8." in appended_texts
