# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB context provider."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any, TypedDict

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AgentSession,
    ContextProvider,
    Message,
    SessionContext,
    SupportsGetEmbeddings,
)
from agent_framework._settings import SecretString, load_settings
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun


logger = logging.getLogger(__name__)

AzureCredentialTypes = TokenCredential | AsyncTokenCredential

COSMOS_USER_AGENT_SUFFIX = f"{AGENT_FRAMEWORK_USER_AGENT} CosmosContextProvider"


class CosmosContextSearchMode(str, Enum):
    """Supported Azure Cosmos DB retrieval modes for the context provider."""

    VECTOR = "vector"
    FULL_TEXT = "full_text"
    HYBRID = "hybrid"


class CosmosContextSettings(TypedDict, total=False):
    """Settings for CosmosContextProvider resolved from args and environment."""

    endpoint: str | None
    database_name: str | None
    container_name: str | None
    key: SecretString | None
    top_k: int | None
    scan_limit: int | None


class CosmosContextProvider(ContextProvider):
    """Azure Cosmos DB-backed context provider.

    Queries a Cosmos DB knowledge container for relevant context before
    agent model invocation, and writes request/response messages back
    into the same container after each run.
    """

    def __init__(
        self,
        source_id: str = "azure_cosmos_context",
        *,
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: str | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        container_client: ContainerProxy | None = None,
        top_k: int | None = None,
        scan_limit: int | None = None,
        search_mode: CosmosContextSearchMode = CosmosContextSearchMode.VECTOR,
        content_field_names: Sequence[str] = ("content", "text"),
        message_field_name: str | None = "message",
        vector_field_name: str = "embedding",
        embedding_function: Callable[[str], Awaitable[list[float]]]
        | SupportsGetEmbeddings[str, list[float], Any]
        | None = None,
        partition_key: str | None = None,
        weights: Sequence[float] | None = None,
        context_prompt: str = "Use the following context to answer the question:",
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        super().__init__(source_id)

        self.top_k = top_k or 5
        self.scan_limit = scan_limit or 25
        self.search_mode = search_mode
        self.content_field_names = tuple(content_field_names)
        self.message_field_name = message_field_name
        self.vector_field_name = vector_field_name
        self.embedding_function = embedding_function
        self.partition_key = partition_key
        self.weights = tuple(float(w) for w in weights) if weights is not None else None
        self.context_prompt = context_prompt

        self._cosmos_client: CosmosClient | None = cosmos_client
        self._container_proxy: ContainerProxy | None = container_client
        self._database_client: DatabaseProxy | None = None
        self._owns_client = False

        if self._container_proxy is not None:
            self.database_name: str = database_name or ""
            self.container_name: str = container_name or ""
            return

        required_fields: list[str] = ["database_name", "container_name"]
        if cosmos_client is None:
            required_fields.append("endpoint")
            if credential is None:
                required_fields.append("key")

        settings = load_settings(
            CosmosContextSettings,
            env_prefix="AZURE_COSMOS_",
            required_fields=required_fields,
            endpoint=endpoint,
            database_name=database_name,
            container_name=container_name,
            key=credential if isinstance(credential, str) else None,
            top_k=top_k,
            scan_limit=scan_limit,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self.database_name = settings["database_name"]  # type: ignore[assignment,reportTypedDictNotRequiredAccess]
        self.container_name = settings["container_name"]  # type: ignore[assignment,reportTypedDictNotRequiredAccess]
        env_top_k = settings.get("top_k")
        if env_top_k is not None:
            self.top_k = env_top_k
        env_scan_limit = settings.get("scan_limit")
        if env_scan_limit is not None:
            self.scan_limit = env_scan_limit

        if self._cosmos_client is None:
            self._cosmos_client = CosmosClient(
                url=settings["endpoint"],  # type: ignore[arg-type]
                credential=credential or settings["key"].get_secret_value(),  # type: ignore[arg-type,union-attr]
                user_agent_suffix=COSMOS_USER_AGENT_SUFFIX,
            )
            self._owns_client = True

        self._database_client = self._cosmos_client.get_database_client(self.database_name)

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Retrieve relevant context from Cosmos DB before model invocation."""
        filtered = [
            msg
            for msg in context.input_messages
            if msg and msg.text and msg.text.strip() and msg.role in {"user", "assistant"}
        ]
        if not filtered:
            return

        query_text = "\n".join(msg.text.strip() for msg in filtered).strip()
        if not query_text:
            return

        query_terms = tuple(dict.fromkeys(m.casefold() for m in re.findall(r"\w+", query_text, flags=re.UNICODE)))
        if self.search_mode in {CosmosContextSearchMode.FULL_TEXT, CosmosContextSearchMode.HYBRID} and not query_terms:
            return

        state["query_text"] = query_text

        items = await self._execute_retrieval_query(query_text, query_terms)

        result_messages: list[Message] = []
        for item in items:
            msg = self._shape_context_message(item)
            if msg is not None:
                result_messages.append(msg)
            if len(result_messages) >= self.top_k:
                break

        if result_messages:
            context.extend_messages(
                self.source_id,
                [Message(role="user", contents=[self.context_prompt]), *result_messages],
            )

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Persist conversation messages to the knowledge container after each run.

        Stores user and assistant messages with embeddings (when available) so
        they are retrievable by ``before_run`` on subsequent invocations.
        """
        messages_to_store: list[Message] = list(context.input_messages)
        if context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)

        writeback = [m for m in messages_to_store if m.role in {"user", "assistant"} and m.text and m.text.strip()]
        if not writeback:
            return

        container = await self._get_container()
        session_key = context.session_id or str(uuid.uuid4())
        if not context.session_id:
            logger.warning("No session_id; generated '%s' for Cosmos writeback partition key.", session_key)

        agent_name = getattr(agent, "name", None)
        user_id = context.metadata.get("user_id") if context.metadata else None

        base_sort_key = time.time_ns()
        for index, message in enumerate(writeback):
            content_text = message.text.strip()
            role_value = str(message.role.value) if hasattr(message.role, "value") else str(message.role)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportAttributeAccessIssue]
            document: dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "session_id": session_key,
                "sort_key": base_sort_key + index,
                "source_id": self.source_id,
                "role": role_value,
                "content": content_text,
                "message": message.to_dict(),
            }
            if agent_name:
                document["agent_name"] = agent_name
            if user_id:
                document["user_id"] = user_id
            if message.author_name:
                document["author_name"] = message.author_name
            if self.partition_key is not None:
                document["partition_key"] = self.partition_key

            if self.embedding_function is not None:
                try:
                    embedding = await self._get_query_vector(content_text)
                    document[self.vector_field_name] = embedding
                except Exception:
                    logger.warning("Failed to generate embedding for writeback document; skipping vector field.")

            await container.upsert_item(document)

    async def close(self) -> None:
        """Close the underlying Cosmos client when this provider owns it."""
        if self._owns_client and self._cosmos_client is not None:
            await self._cosmos_client.close()

    async def __aenter__(self) -> CosmosContextProvider:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        try:
            await self.close()
        except Exception:
            if exc_type is None:
                raise

    # --- Private ---

    async def _get_container(self) -> ContainerProxy:
        """Return the Cosmos container proxy, resolving lazily from database client."""
        if self._container_proxy is not None:
            return self._container_proxy
        if self._database_client is None:
            raise RuntimeError("Cosmos database client is not initialized.")
        self._container_proxy = self._database_client.get_container_client(self.container_name)
        return self._container_proxy

    async def _execute_retrieval_query(self, query_text: str, query_terms: tuple[str, ...]) -> list[dict[str, Any]]:
        """Build and execute the Cosmos retrieval query for the configured search mode."""
        fields = list(self.content_field_names)
        if self.message_field_name and self.message_field_name not in fields:
            fields.append(self.message_field_name)
        select = ", ".join(f"c.{f}" for f in fields)
        base = f"SELECT TOP {self.scan_limit} {select} FROM c"  # noqa: S608  # nosec B608

        parameters: list[dict[str, object]] = []

        if self.search_mode is CosmosContextSearchMode.FULL_TEXT:
            search_field = self.content_field_names[0]
            query = f"{base} ORDER BY RANK FullTextScore(c.{search_field}, @query_text)"
            parameters.append({"name": "@query_text", "value": " ".join(query_terms)})

        elif self.search_mode is CosmosContextSearchMode.VECTOR:
            query_vector = await self._get_query_vector(query_text)
            query = f"{base} ORDER BY VectorDistance(c.{self.vector_field_name}, @query_vector) ASC"
            parameters.append({"name": "@query_vector", "value": query_vector})

        elif self.search_mode is CosmosContextSearchMode.HYBRID:
            query_vector = await self._get_query_vector(query_text)
            search_field = self.content_field_names[0]
            ft = f"FullTextScore(c.{search_field}, @query_text)"
            vd = f"VectorDistance(c.{self.vector_field_name}, @query_vector)"
            if self.weights is not None:
                wl = "[" + ", ".join(f"{w:g}" for w in self.weights) + "]"
                rrf = f"RRF({ft}, {vd}, {wl})"
            else:
                rrf = f"RRF({ft}, {vd})"
            query = f"{base} ORDER BY RANK {rrf}"
            parameters.append({"name": "@query_text", "value": " ".join(query_terms)})
            parameters.append({"name": "@query_vector", "value": query_vector})

        else:
            raise ValueError(f"Unsupported search_mode: {self.search_mode}")

        container = await self._get_container()
        query_kwargs: dict[str, Any] = {"query": query, "max_item_count": self.scan_limit}
        if parameters:
            query_kwargs["parameters"] = parameters
        if self.partition_key is not None:
            query_kwargs["partition_key"] = self.partition_key
        return [item async for item in container.query_items(**query_kwargs)]

    def _shape_context_message(self, item: dict[str, Any]) -> Message | None:
        """Convert a Cosmos item into a context Message."""
        payload = item.get(self.message_field_name) if self.message_field_name else None
        if isinstance(payload, dict):
            try:
                return Message.from_dict(payload)  # pyright: ignore[reportUnknownArgumentType]
            except (TypeError, ValueError):
                pass

        content = next(
            (v.strip() for f in self.content_field_names if isinstance(v := item.get(f), str) and v.strip()),
            None,
        )
        if not content:
            return None
        return Message(role="user", contents=[content])

    async def _get_query_vector(self, query_text: str) -> list[float]:
        """Get a query embedding from the configured embedding provider."""
        if self.embedding_function is None:
            raise ValueError("embedding_function is required for vector and hybrid retrieval")

        if isinstance(self.embedding_function, SupportsGetEmbeddings):
            embeddings = await self.embedding_function.get_embeddings([query_text])  # type: ignore[reportUnknownVariableType]
            if not embeddings:
                raise ValueError("embedding_function returned no embeddings")
            return [float(v) for v in embeddings[0].vector]  # type: ignore[reportUnknownVariableType]

        return [float(v) for v in await self.embedding_function(query_text)]


__all__ = ["CosmosContextProvider", "CosmosContextSearchMode"]
