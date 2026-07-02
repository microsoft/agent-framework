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
import uuid
from collections.abc import AsyncIterator

import pytest

# The Agent Memory Toolkit requires Python 3.11+, so it is not installed on the 3.10 CI
# leg. Skip this module there (mirrors the github_copilot package's importorskip guard).
pytest.importorskip("azure.cosmos.agent_memory")

from agent_framework import Message  # noqa: E402
from agent_framework._sessions import AgentSession, SessionContext  # noqa: E402
from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient  # noqa: E402

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider  # noqa: E402

pytestmark = pytest.mark.integration

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

    Returns an empty extraction result so the pipeline never invokes a real LLM. The tests
    seed memories directly, so no chat output is needed.
    """

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict | None = None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        **extra: object,
    ) -> str:
        return '{"memories": []}'

    async def close(self) -> None:
        return None


@pytest.fixture
async def emulator_provider(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[CosmosMemoryContextProvider]:
    """Provider wired to the emulator with quantizedFlat vectors and injected fakes.

    Uses a unique database per test run for isolation and to avoid cross-run interference.
    Skips (rather than fails) if the emulator is not reachable, so the suite is a no-op when
    no emulator is running.
    """
    # The emulator does not support the diskANN index; force the emulator-compatible
    # quantizedFlat index type for the containers the provider creates on entry.
    monkeypatch.setenv("AI_FOUNDRY_EMBEDDING_VECTOR_INDEX_TYPE", "quantizedFlat")

    # The provider only ever performs pure vector search (hybrid_search=False), so the
    # toolkit's full-text index is not needed here. The toolkit bakes a full-text index into
    # every container it creates, which requires the Cosmos "Full Text Search" preview feature.
    # Strip it from the container-creation policies so the suite runs on a stock emulator that
    # only has vector search. Vector queries are unaffected.
    from azure.cosmos.agent_memory.aio import cosmos_memory_client as _aio_client_mod

    _orig_policies = _aio_client_mod._container_policies

    def _vector_only_policies(**kwargs: object) -> tuple[dict, dict, dict | None]:
        vec_policy, idx_policy, _ft_policy = _orig_policies(**kwargs)
        idx_policy = {k: v for k, v in idx_policy.items() if k != "fullTextIndexes"}
        return vec_policy, idx_policy, None

    monkeypatch.setattr(_aio_client_mod, "_container_policies", _vector_only_policies)

    client = AsyncCosmosMemoryClient(
        cosmos_endpoint=_EMULATOR_ENDPOINT,
        cosmos_key=_EMULATOR_KEY,
        cosmos_database=f"test_af_mem_{uuid.uuid4().hex[:8]}",
        embedding_dimensions=_EMBED_DIM,
        embeddings_client=_FakeEmbeddings(),
        chat_client=_FakeChat(),
        use_default_credential=False,
        # The toolkit defaults to serverless throughput, which the emulator (a provisioned
        # account) does not support and rejects with a ServiceUnavailable "high demand" error.
        # Use provisioned autoscale throughput at a low RU so the containers fit the emulator.
        cosmos_throughput_mode="autoscale",
        cosmos_autoscale_max_ru=1000,
    )
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
            agent=None,  # type: ignore[arg-type]
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
            agent=None,  # type: ignore[arg-type]
            session=session,
            context=ctx,
            state=scoped,
        )

        turns = await provider.memory_client.get_thread(user_id=user_id, thread_id=thread_id)
        contents = " ".join(str(t.get("content", "")) for t in turns)
        assert "window seats" in contents.lower()
