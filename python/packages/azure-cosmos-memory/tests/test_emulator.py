# Copyright (c) Microsoft. All rights reserved.

"""Emulator-backed integration tests for CosmosMemoryContextProvider.

These run against a local Azure Cosmos DB emulator and exercise REAL Cosmos vector
search using a ``quantizedFlat`` index (the emulator-compatible index type). Embeddings
and chat are provided by deterministic in-memory fakes injected into the toolkit client,
so no Azure AI Foundry account is required. The suite is marked ``integration`` (not
``azure``): it needs an external Cosmos backend but no live Azure account.

Prerequisites:
- A running Cosmos DB emulator reachable at ``COSMOS_EMULATOR_ENDPOINT``
  (default ``https://localhost:8081``) authenticated with ``COSMOS_EMULATOR_KEY``
  (default: the well-known public emulator key). The emulator must have vector search
  enabled.

Run with: pytest -m "integration and not azure" tests/test_emulator.py
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

# The Agent Memory Toolkit requires Python 3.11+, so it is not installed on the 3.10 CI
# leg. Skip this module there (mirrors the github_copilot package's importorskip guard).
pytest.importorskip("azure.cosmos.agent_memory")

from agent_framework import Message  # noqa: E402
from agent_framework._sessions import AgentSession, SessionContext  # noqa: E402
from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient  # noqa: E402

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider  # noqa: E402

pytestmark = pytest.mark.integration

# The provider methods accept an ``agent`` implementing ``SupportsAgentRun`` but never
# use it in these tests, so a typed ``None`` stub keeps the call sites clean.
_STUB_AGENT: Any = None

# The well-known Cosmos DB emulator key is a fixed, publicly documented value (not a secret).
_WELL_KNOWN_EMULATOR_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
_EMULATOR_ENDPOINT = os.getenv("COSMOS_EMULATOR_ENDPOINT", "https://localhost:8081")
_EMULATOR_KEY = os.getenv("COSMOS_EMULATOR_KEY", _WELL_KNOWN_EMULATOR_KEY)
_EMBED_DIM = 8


class _FakeEmbeddings:
    """Deterministic stand-in for the toolkit's embeddings client.

    Maps text to a fixed-dimension vector so tests are repeatable and require no Azure AI
    Foundry account. The vectors are not semantically meaningful; the tests assert retrieval
    of specific seeded records rather than semantic ranking quality.
    """

    def __init__(self, dim: int = _EMBED_DIM) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for i, ch in enumerate(text):
            vec[i % self._dim] += (ord(ch) % 17) / 17.0
        return vec

    async def generate(self, text: str) -> list[float]:
        return self._vector(text)

    async def generate_batch(self, texts: list[str], *, batch_size: int = 16) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def close(self) -> None:
        return None


class _FakeChat:
    """Deterministic stand-in for the toolkit's chat client.

    Records each call so tests can assert the extraction pipeline was invoked, and returns an
    empty extraction result so the pipeline never depends on a real LLM.
    """

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict | None = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        **extra: object,
    ) -> str:
        self.calls.append(messages)
        return '{"memories": []}'

    async def close(self) -> None:
        return None


def _build_emulator_client(monkeypatch: pytest.MonkeyPatch, chat_client: _FakeChat) -> AsyncCosmosMemoryClient:
    """Build a toolkit client pointed at the local emulator with injected fakes.

    Forces the emulator-compatible quantizedFlat vector index and strips the toolkit's
    full-text index (the provider only does pure vector search), so the suite runs on a stock
    emulator without the Full Text Search preview feature. Uses provisioned autoscale
    throughput (the emulator rejects serverless).

    Reuses a single fixed database rather than a per-run one: the emulator has a finite
    partition budget, and creating a fresh database on every run exhausts it (ServiceUnavailable
    "high demand"). Tests isolate themselves via unique ``user_id``/``thread_id`` values instead.
    """
    monkeypatch.setenv("AI_FOUNDRY_EMBEDDING_VECTOR_INDEX_TYPE", "quantizedFlat")

    from azure.cosmos.agent_memory.aio import cosmos_memory_client as _aio_client_mod

    _orig_policies = _aio_client_mod._container_policies

    def _vector_only_policies(**kwargs: Any) -> tuple[dict, dict, dict | None]:
        vec_policy, idx_policy, _ft_policy = _orig_policies(**kwargs)
        idx_policy = {k: v for k, v in idx_policy.items() if k != "fullTextIndexes"}
        return vec_policy, idx_policy, None

    monkeypatch.setattr(_aio_client_mod, "_container_policies", _vector_only_policies)

    return AsyncCosmosMemoryClient(
        cosmos_endpoint=_EMULATOR_ENDPOINT,
        cosmos_key=_EMULATOR_KEY,
        cosmos_database="test_af_mem",
        embedding_dimensions=_EMBED_DIM,
        embeddings_client=_FakeEmbeddings(),
        chat_client=chat_client,
        use_default_credential=False,
        cosmos_throughput_mode="autoscale",
        cosmos_autoscale_max_ru=1000,
    )


@pytest.fixture
async def emulator_provider(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[CosmosMemoryContextProvider]:
    """Provider wired to the emulator with quantizedFlat vectors and injected fakes.

    Tests isolate themselves via unique ``user_id``/``thread_id`` values (see
    ``_build_emulator_client`` for why a shared database is used). Skips (rather than fails) if
    the emulator is not reachable, so the suite is a no-op when no emulator is running.
    """
    client = _build_emulator_client(monkeypatch, _FakeChat())
    provider = CosmosMemoryContextProvider(
        memory_client=client,
        top_k=5,
        min_confidence=0.0,
        memory_types=["fact"],
    )
    try:
        await provider.__aenter__()
    except Exception as exc:  # noqa: BLE001 - surface a clear skip for any connectivity/setup failure
        await client.close()
        pytest.skip(f"Cosmos DB emulator not reachable or vector search unavailable at {_EMULATOR_ENDPOINT}: {exc}")

    try:
        yield provider
    finally:
        await provider.__aexit__(None, None, None)
        await client.close()


class TestEmulatorVectorSearch:
    """Validate the real Cosmos vector path (quantizedFlat) end to end via the provider."""

    async def test_before_run_retrieves_seeded_fact(self, emulator_provider: CosmosMemoryContextProvider) -> None:
        """A fact seeded with an embedding is retrieved by before_run's vector search."""
        provider = emulator_provider
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        thread_id = f"thread-{uuid.uuid4().hex[:8]}"

        # Seed a fact directly with a deterministic embedding (embed=True uses the fake
        # embeddings client). This lands in the memories container under the quantizedFlat
        # vector index, without needing LLM extraction.
        assert provider.memory_client is not None
        await provider.memory_client.add_cosmos(
            user_id=user_id,
            thread_id=thread_id,
            role="user",
            content="The user loves hiking in the mountains.",
            memory_type="fact",
            embed=True,
        )

        session = AgentSession(session_id=thread_id)
        session.state.setdefault(provider.source_id, {})["user_id"] = user_id
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["What outdoor activities do I enjoy?"])],
            session_id=session.session_id,
        )

        await provider.before_run(
            agent=_STUB_AGENT,
            session=session,
            context=ctx,
            state=session.state.setdefault(provider.source_id, {}),
        )

        injected = ctx.context_messages.get(provider.source_id, [])
        blob = "\n".join(m.text for m in injected if m.text)  # type: ignore[union-attr]
        assert "hiking" in blob.lower()

    async def test_after_run_persists_turns(self, emulator_provider: CosmosMemoryContextProvider) -> None:
        """after_run writes conversation turns to the emulator (verified via get_thread)."""
        provider = emulator_provider
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        thread_id = f"thread-{uuid.uuid4().hex[:8]}"

        session = AgentSession(session_id=thread_id)
        scoped = session.state.setdefault(provider.source_id, {})
        scoped["user_id"] = user_id
        ctx = SessionContext(
            input_messages=[Message(role="user", contents=["Remember I prefer window seats."])],
            session_id=session.session_id,
        )

        await provider.after_run(
            agent=_STUB_AGENT,
            session=session,
            context=ctx,
            state=scoped,
        )

        assert provider.memory_client is not None
        turns = await provider.memory_client.get_thread(user_id=user_id, thread_id=thread_id)
        contents = " ".join(str(t.get("content", "")) for t in turns)
        assert "window seats" in contents.lower()


class TestEmulatorTransparentExtraction:
    """Memory extraction must run transparently: storing a turn via ``after_run`` schedules the
    toolkit's background pipeline on its own, and the provider drains it when the context exits.
    The application never calls ``flush()``/``process_now()`` in its control flow.
    """

    async def test_after_run_triggers_and_drains_extraction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stored turn schedules background extraction; exiting the provider drains it.

        This test manages the provider lifecycle directly (instead of the shared fixture) so it
        can assert state both while extraction is in flight and after the context exits.
        """
        chat = _FakeChat()
        client = _build_emulator_client(monkeypatch, chat)
        provider = CosmosMemoryContextProvider(
            memory_client=client,
            top_k=5,
            min_confidence=0.0,
            memory_types=["fact"],
        )
        try:
            await provider.__aenter__()
        except Exception as exc:  # noqa: BLE001 - clear skip on any connectivity/setup failure
            await client.close()
            pytest.skip(f"Cosmos DB emulator not reachable or vector search unavailable at {_EMULATOR_ENDPOINT}: {exc}")

        try:
            user_id = f"user-{uuid.uuid4().hex[:8]}"
            thread_id = f"thread-{uuid.uuid4().hex[:8]}"
            session = AgentSession(session_id=thread_id)
            session.state.setdefault(provider.source_id, {})["user_id"] = user_id
            ctx = SessionContext(
                input_messages=[Message(role="user", contents=["I live in Seattle and enjoy kayaking."])],
                session_id=session.session_id,
            )

            # Storing the turn through the normal agent hook must, on its own, schedule the
            # toolkit's extraction pipeline as a fire-and-forget background task
            # (FACT_EXTRACTION_EVERY_N defaults to 1). The caller does nothing else.
            await provider.after_run(
                agent=_STUB_AGENT,
                session=session,
                context=ctx,
                state=session.state.setdefault(provider.source_id, {}),
            )

            # The write scheduled background work rather than blocking the turn on extraction.
            assert client._background_tasks, "after_run did not schedule background extraction"
        finally:
            # Exiting the context must drain in-flight extraction. No flush()/process_now() is called.
            await provider.__aexit__(None, None, None)

        # Draining ran the extraction pipeline transparently (its chat step was invoked) and
        # left no pending background tasks behind.
        assert chat.calls, "background extraction did not run transparently after the turn"
        assert all(task.done() for task in client._background_tasks)
        await client.close()


def _make_custom_prompts_dir(dest: Path, marker: str) -> Path:
    """Build a complete prompts directory whose ``extract_memories.prompty`` carries a marker.

    Copies the toolkit's bundled templates into ``dest`` (the loader needs the full set), then
    injects ``marker`` into the extraction template's system prompt. Deriving from the installed
    template keeps the output schema valid regardless of toolkit version.
    """
    import azure.cosmos.agent_memory as toolkit

    bundled = Path(toolkit.__file__).parent / "prompts"
    dest.mkdir(parents=True, exist_ok=True)
    for template in bundled.glob("*.prompty"):
        shutil.copy2(template, dest / template.name)

    extract = dest / "extract_memories.prompty"
    text = extract.read_text(encoding="utf-8")
    section = "\nsystem:\n"
    idx = text.find(section)
    assert idx != -1, "unexpected extract_memories.prompty format (no 'system:' section)"
    insert_at = idx + len(section)
    extract.write_text(text[:insert_at] + f"\n{marker}\n" + text[insert_at:], encoding="utf-8")
    return dest


class TestEmulatorCustomExtractionPrompt:
    """A custom ``prompts_dir`` must change the prompt the extraction pipeline actually sends.

    Overriding ``extract_memories.prompty`` is how callers customize what the LLM extracts. This
    proves the provider's ``prompts_dir`` seam is wired through to the toolkit pipeline: a unique
    marker placed in the custom template shows up in the messages the pipeline sends to the chat
    client during extraction.
    """

    async def test_prompts_dir_overrides_extraction_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The provider routes extraction through the caller-supplied ``prompts_dir``."""
        marker = f"AF_CUSTOM_RUBRIC_{uuid.uuid4().hex}"
        custom_dir = _make_custom_prompts_dir(tmp_path / "prompts", marker)

        chat = _FakeChat()
        client = _build_emulator_client(monkeypatch, chat)
        provider = CosmosMemoryContextProvider(
            memory_client=client,
            top_k=5,
            min_confidence=0.0,
            memory_types=["fact"],
            prompts_dir=str(custom_dir),
        )
        try:
            await provider.__aenter__()
        except Exception as exc:  # noqa: BLE001 - clear skip on any connectivity/setup failure
            await client.close()
            pytest.skip(f"Cosmos DB emulator not reachable or vector search unavailable at {_EMULATOR_ENDPOINT}: {exc}")

        try:
            user_id = f"user-{uuid.uuid4().hex[:8]}"
            thread_id = f"thread-{uuid.uuid4().hex[:8]}"
            session = AgentSession(session_id=thread_id)
            session.state.setdefault(provider.source_id, {})["user_id"] = user_id
            ctx = SessionContext(
                input_messages=[Message(role="user", contents=["We chose the repository pattern for data access."])],
                session_id=session.session_id,
            )
            await provider.after_run(
                agent=_STUB_AGENT,
                session=session,
                context=ctx,
                state=session.state.setdefault(provider.source_id, {}),
            )
        finally:
            # Draining runs the extraction pipeline, which loads the (custom) extract template.
            await provider.__aexit__(None, None, None)

        # The extraction step sent our custom prompt to the chat client: the marker only exists
        # in the overridden template, so its presence proves prompts_dir was honored end to end.
        sent = "\n".join(str(msg.get("content", "")) for call in chat.calls for msg in call)
        assert marker in sent, "custom extract_memories.prompty was not used by the extraction pipeline"
        await client.close()
