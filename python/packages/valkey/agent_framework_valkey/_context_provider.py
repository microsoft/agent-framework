# Copyright (c) Microsoft. All rights reserved.

"""Valkey context provider using ContextProvider.

This module provides ``ValkeyContextProvider``, built on the
:class:`ContextProvider` hooks pattern. It uses valkey-glide with Valkey's
native vector search capabilities (FT.CREATE / FT.SEARCH) for semantic
retrieval of past conversation context.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from agent_framework import Message
from agent_framework._sessions import AgentSession, ContextProvider, SessionContext
from agent_framework.exceptions import IntegrationInvalidRequestException

try:
    from glide import GlideClient, GlideClientConfiguration, NodeAddress
except ImportError:
    GlideClient = None  # type: ignore[assignment,misc]
    GlideClientConfiguration = None  # type: ignore[assignment,misc]
    NodeAddress = None  # type: ignore[assignment,misc]

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._agents import SupportsAgentRun

EmbedFn = Callable[[str], Awaitable[list[float]]]


def _check_glide_available() -> None:
    """Raise a clear error if valkey-glide is not installed."""
    if GlideClient is None:
        raise ImportError(
            "valkey-glide is required but not installed. "
            "It is not available on Windows. "
            "Install it with: pip install valkey-glide"
        )


class ValkeyContextProvider(ContextProvider):
    """Valkey context provider using the ContextProvider hooks pattern.

    Stores context in Valkey using HASH keys and retrieves scoped context via
    full-text search or optional hybrid vector search using Valkey's native
    FT.CREATE / FT.SEARCH commands through valkey-glide.
    """

    DEFAULT_CONTEXT_PROMPT = "## Memories\nConsider the following memories when answering user questions:"
    DEFAULT_SOURCE_ID: ClassVar[str] = "valkey"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        valkey_url: str | None = None,
        host: str | None = None,
        port: int | None = None,
        *,
        use_tls: bool = False,
        index_name: str = "context_idx",
        prefix: str = "context:",
        vector_dims: int | None = None,
        vector_field_name: str | None = None,
        vector_algorithm: Literal["FLAT", "HNSW"] = "HNSW",
        vector_distance_metric: Literal["COSINE", "IP", "L2"] = "COSINE",
        embed_fn: EmbedFn | None = None,
        application_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        context_prompt: str | None = None,
        client: "GlideClient | None" = None,
    ):
        """Create a Valkey Context Provider.

        Args:
            source_id: Unique identifier for this provider instance.
            valkey_url: Valkey connection URL (e.g., "valkey://localhost:6379").
                If provided, host and port are extracted from the URL.
                Mutually exclusive with explicit host/port.
            host: Valkey server hostname. Defaults to "localhost" when neither
                valkey_url nor client is provided.
            port: Valkey server port. Defaults to 6379 when neither valkey_url
                nor client is provided.
            use_tls: Enable TLS for the connection. Defaults to False.
            index_name: The name of the search index. Defaults to "context_idx".
            prefix: The key prefix for stored documents. Defaults to "context:".
            vector_dims: Dimensionality of embedding vectors. Required if embed_fn is set.
            vector_field_name: The name of the vector field. Required if embed_fn is set.
            vector_algorithm: Vector index algorithm ("FLAT" or "HNSW"). Defaults to "HNSW".
            vector_distance_metric: Distance metric ("COSINE", "IP", or "L2"). Defaults to "COSINE".
            embed_fn: An async callable that takes a string and returns a list of floats.
                Required for vector search. When provided, vector_field_name and
                vector_dims must also be set.
            application_id: The application ID to scope the context.
            agent_id: The agent ID to scope the context.
            user_id: The user ID to scope the context.
            context_prompt: The context prompt to use for the provider.
            client: A pre-created GlideClient instance. If provided, host/port/url
                are ignored and the caller is responsible for the client lifecycle.
        """
        _check_glide_available()
        super().__init__(source_id)

        # Validate mutually exclusive connection params
        if client is None and valkey_url is not None and (host is not None or port is not None):
            raise ValueError("valkey_url and explicit host/port are mutually exclusive.")

        # Validate vector configuration consistency
        if embed_fn is not None:
            if vector_field_name is None or vector_dims is None:
                raise ValueError(
                    "vector_field_name and vector_dims are required when embed_fn is provided."
                )
            if vector_dims <= 0:
                raise ValueError("vector_dims must be a positive integer.")

        self.valkey_url = valkey_url
        self.host = host or "localhost"
        self.port = port or 6379
        self.use_tls = use_tls
        self.index_name = index_name
        self.prefix = prefix
        self.vector_dims = vector_dims
        self.vector_field_name = vector_field_name
        self.vector_algorithm = vector_algorithm
        self.vector_distance_metric = vector_distance_metric
        self.embed_fn = embed_fn
        self.application_id = application_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.context_prompt = context_prompt or self.DEFAULT_CONTEXT_PROMPT
        self._client: GlideClient | None = client  # type: ignore[assignment]
        self._owns_client = client is None
        self._index_created: bool = False

    async def _get_client(self) -> GlideClient:  # type: ignore[return]
        """Get or create the Valkey client."""
        if self._client is None:
            if self.valkey_url is not None:
                parsed_host, parsed_port = self._parse_url(self.valkey_url)
            else:
                parsed_host, parsed_port = self.host, self.port
            config = GlideClientConfiguration(
                addresses=[NodeAddress(host=parsed_host, port=parsed_port)],
                use_tls=self.use_tls,
            )
            self._client = await GlideClient.create(config)
        return self._client

    @staticmethod
    def _parse_url(url: str) -> tuple[str, int]:
        """Parse a Valkey URL into host and port components.

        Args:
            url: A URL like "valkey://host:port" or "redis://host:port".

        Returns:
            A tuple of (host, port).
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        return host, port

    # -- Hooks pattern ---------------------------------------------------------

    @override
    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Retrieve scoped context from Valkey and add to the session context."""
        self._validate_filters()
        input_text = "\n".join(msg.text for msg in context.input_messages if msg and msg.text and msg.text.strip())
        if not input_text.strip():
            return

        memories = await self._search(text=input_text)
        line_separated_memories = "\n".join(
            str(memory.get("content", "")) for memory in memories if memory.get("content")
        )
        if line_separated_memories:
            context.extend_messages(
                self.source_id,
                [Message(role="user", contents=[f"{self.context_prompt}\n{line_separated_memories}"])],
            )

    @override
    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Store request/response messages to Valkey for future retrieval."""
        self._validate_filters()

        messages_to_store: list[Message] = list(context.input_messages)
        if context.response and context.response.messages:
            messages_to_store.extend(context.response.messages)

        docs: list[dict[str, Any]] = []
        for message in messages_to_store:
            if message.role in {"user", "assistant", "system"} and message.text and message.text.strip():
                doc: dict[str, Any] = {
                    "role": message.role,
                    "content": message.text,
                    "conversation_id": context.session_id or "",
                    "message_id": message.message_id or "",
                    "author_name": message.author_name or "",
                    "application_id": self.application_id or "",
                    "agent_id": self.agent_id or "",
                    "user_id": self.user_id or "",
                    "thread_id": context.session_id or "",
                }
                docs.append(doc)

        if docs:
            await self._add(data=docs)

    # -- Internal methods ------------------------------------------------------

    async def _ensure_index(self) -> None:
        """Create the search index if it does not already exist."""
        if self._index_created:
            return

        client = await self._get_client()

        # Build FT.CREATE arguments
        args: list[str] = [
            self.index_name,
            "ON",
            "HASH",
            "PREFIX",
            "1",
            self.prefix,
            "SCHEMA",
            "role",
            "TAG",
            "content",
            "TEXT",
            "conversation_id",
            "TAG",
            "message_id",
            "TAG",
            "author_name",
            "TAG",
            "application_id",
            "TAG",
            "agent_id",
            "TAG",
            "user_id",
            "TAG",
            "thread_id",
            "TAG",
        ]

        if self.vector_field_name and self.vector_dims:
            args.extend([
                self.vector_field_name,
                "VECTOR",
                self.vector_algorithm,
                "6",
                "TYPE",
                "FLOAT32",
                "DIM",
                str(self.vector_dims),
                "DISTANCE_METRIC",
                self.vector_distance_metric,
            ])

        try:
            await client.custom_command(["FT.CREATE", *args])  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            # Index already exists is not an error
            if "Index already exists" in str(exc):
                pass
            else:
                raise IntegrationInvalidRequestException(f"Failed to create Valkey search index: {exc}") from exc

        self._index_created = True

    async def _add(self, *, data: list[dict[str, Any]]) -> None:
        """Insert documents into Valkey as HASH keys.

        Partition fields (application_id, agent_id, user_id) are defaulted
        from the provider's configuration if not already present in each document.
        """
        await self._ensure_index()
        client = await self._get_client()

        for doc in data:
            doc_id = f"{self.prefix}{uuid.uuid4().hex}"

            # Default partition fields if not already set (defensive, like Redis provider)
            doc.setdefault("application_id", self.application_id or "")
            doc.setdefault("agent_id", self.agent_id or "")
            doc.setdefault("user_id", self.user_id or "")

            field_map: dict[str | bytes, str | bytes] = {}
            for key, value in doc.items():
                if key == self.vector_field_name:
                    continue
                field_map[key] = str(value)

            if self.embed_fn is not None and self.vector_field_name and "content" in doc:
                try:
                    import numpy as np
                except ImportError as exc:
                    raise IntegrationInvalidRequestException(
                        "Vector support requires the optional dependency 'numpy'. "
                        "Install agent-framework-valkey[vector] to enable vector search."
                    ) from exc

                embedding: list[float] = await self.embed_fn(doc["content"])
                vec_bytes: bytes = np.asarray(embedding, dtype=np.float32).tobytes()
                field_map[self.vector_field_name] = vec_bytes

            await client.hset(doc_id, field_map)  # pyright: ignore[reportArgumentType]

    async def _search(
        self,
        text: str,
        *,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Run a text or hybrid vector-text search with scope filters.

        Args:
            text: The search query text.
            num_results: Maximum number of results to return.

        Returns:
            A list of document dicts with at least a "content" field.
        """
        await self._ensure_index()
        client = await self._get_client()

        q = (text or "").strip()
        if not q:
            raise IntegrationInvalidRequestException("search requires non-empty text")

        # Build filter expression from scope fields
        filter_parts: list[str] = []
        if self.application_id:
            filter_parts.append(f"@application_id:{{{self._escape_tag(self.application_id)}}}")
        if self.agent_id:
            filter_parts.append(f"@agent_id:{{{self._escape_tag(self.agent_id)}}}")
        if self.user_id:
            filter_parts.append(f"@user_id:{{{self._escape_tag(self.user_id)}}}")

        filter_expr = " ".join(filter_parts) if filter_parts else "*"

        # Fields to return from FT.SEARCH — excludes the vector field to avoid
        # binary data in text-oriented parsing.
        return_fields = ["content", "role", "conversation_id", "message_id", "author_name",
                         "application_id", "agent_id", "user_id", "thread_id"]

        try:
            result: Any
            if self.embed_fn is not None and self.vector_field_name:
                # Hybrid: vector KNN with pre-filter
                try:
                    import numpy as np
                except ImportError as exc:
                    raise IntegrationInvalidRequestException(
                        "Vector search requires the optional 'numpy' dependency. "
                        "Install agent-framework-valkey[vector]."
                    ) from exc

                embedding: list[float] = await self.embed_fn(q)
                vec_bytes: bytes = np.asarray(embedding, dtype=np.float32).tobytes()

                query_str = f"({filter_expr})=>[KNN {num_results} @{self.vector_field_name} $vec AS score]"
                result = await client.custom_command([  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    "FT.SEARCH",
                    self.index_name,
                    query_str,
                    "RETURN",
                    str(len(return_fields) + 1),  # +1 for the "score" alias
                    *return_fields,
                    "score",
                    "PARAMS",
                    "2",
                    "vec",
                    vec_bytes,
                    "SORTBY",
                    "score",
                    "LIMIT",
                    "0",
                    str(num_results),
                    "DIALECT",
                    "2",
                ])
            else:
                # Text-only search
                escaped_text = self._escape_query(q)
                query_str = f"{filter_expr} {escaped_text}" if filter_parts else escaped_text
                result = await client.custom_command([  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    "FT.SEARCH",
                    self.index_name,
                    query_str,
                    "RETURN",
                    str(len(return_fields)),
                    *return_fields,
                    "LIMIT",
                    "0",
                    str(num_results),
                ])

            return self._parse_search_results(result, vector_field_name=self.vector_field_name)
        except IntegrationInvalidRequestException:
            raise
        except Exception as exc:
            raise IntegrationInvalidRequestException(f"Valkey search failed: {exc}") from exc

    async def search_all(self, page_size: int = 200) -> list[dict[str, Any]]:
        """Return all documents in the index.

        Note: This method is unscoped — it returns documents across all
        application_id/agent_id/user_id partitions. Use for debugging,
        testing, and administrative tasks only.

        Args:
            page_size: Number of documents per page. Defaults to 200.

        Returns:
            A list of all document dicts in the index.
        """
        await self._ensure_index()
        client = await self._get_client()

        all_docs: list[dict[str, Any]] = []
        offset = 0
        while True:
            result: Any = await client.custom_command([  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                "FT.SEARCH",
                self.index_name,
                "*",
                "LIMIT",
                str(offset),
                str(page_size),
            ])
            page = self._parse_search_results(result, vector_field_name=self.vector_field_name)
            if not page:
                break
            all_docs.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return all_docs

    @staticmethod
    def _decode_field_value(v: Any, field_name: str, vector_field_name: str | None) -> str | None:
        """Decode a field value from FT.SEARCH results, skipping vector fields.

        Args:
            v: The raw value from the search result.
            field_name: The name of the field being decoded.
            vector_field_name: The name of the vector field to skip.

        Returns:
            The decoded string value, or None if the field should be skipped.
        """
        if field_name == vector_field_name:
            return None
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8")
            except UnicodeDecodeError:
                # Binary data (e.g. leftover vector bytes) — skip gracefully
                return None
        return str(v)

    @staticmethod
    def _parse_search_results(result: Any, *, vector_field_name: str | None = None) -> list[dict[str, Any]]:
        """Parse FT.SEARCH response into a list of document dicts."""
        docs: list[dict[str, Any]] = []
        if not result or not isinstance(result, list):
            return docs

        result_list = cast(list[Any], result)
        if len(result_list) < 2:
            return docs

        # Valkey 9.1+ returns dict format: [total_count, {doc_id: {field: value, ...}, ...}]
        if isinstance(result_list[1], dict):
            for _doc_id, fields in result_list[1].items():  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                if isinstance(fields, dict):
                    doc: dict[str, Any] = {}
                    for k, v in fields.items():  # pyright: ignore[reportUnknownVariableType]
                        key: str = k.decode("utf-8") if isinstance(k, bytes) else str(k)  # pyright: ignore[reportUnknownArgumentType]
                        value = ValkeyContextProvider._decode_field_value(v, key, vector_field_name)
                        if value is not None:
                            doc[key] = value
                    docs.append(doc)
            return docs

        # Legacy flat list format: [total_count, doc_id, [field, value, ...], ...]
        i = 1
        while i < len(result_list):
            if i + 1 < len(result_list) and isinstance(result_list[i + 1], list):
                fields = cast(list[Any], result_list[i + 1])
                doc = {}
                for j in range(0, len(fields), 2):
                    key = fields[j].decode("utf-8") if isinstance(fields[j], bytes) else str(fields[j])
                    value = ValkeyContextProvider._decode_field_value(
                        fields[j + 1], key, vector_field_name
                    )
                    if value is not None:
                        doc[key] = value
                docs.append(doc)
                i += 2
            else:
                i += 1

        return docs

    @staticmethod
    def _escape_tag(value: str) -> str:
        """Escape special characters in a TAG filter value."""
        special = r".,<>{}[]\"':;!@#$%^&*()-+=~/ "
        escaped: list[str] = []
        for ch in value:
            if ch in special:
                escaped.append(f"\\{ch}")
            else:
                escaped.append(ch)
        return "".join(escaped)

    @staticmethod
    def _escape_query(text: str) -> str:
        """Escape special characters in a full-text query."""
        special = r"@!{}()|\-=~[]^\"':*$>+/"
        escaped: list[str] = []
        for ch in text:
            if ch in special:
                escaped.append(f"\\{ch}")
            else:
                escaped.append(ch)
        return "".join(escaped)

    def _validate_filters(self) -> None:
        """Validate that at least one scope filter is provided."""
        if not self.agent_id and not self.user_id and not self.application_id:
            raise ValueError("At least one of the filters: agent_id, user_id, or application_id is required.")

    async def aclose(self) -> None:
        """Close the Valkey connection if owned by this instance."""
        if self._owns_client and self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.aclose()


__all__ = ["ValkeyContextProvider"]
