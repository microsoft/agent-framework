# Vector Stores and Embeddings

## Overview

This feature ports the vector store abstractions, embedding generator abstractions, and their implementations from Semantic Kernel into Agent Framework. The ported code follows AF's coding standards, feels native to AF, and is structured to allow data models/schemas to be reusable across both frameworks. The embedding abstraction combines the best of SK's `EmbeddingGeneratorBase` and MEAI's `IEmbeddingGenerator<TInput, TEmbedding>`.

| Capability | Description |
| --- | --- |
| Embedding generation | Generic embedding client abstraction supporting text, image, and audio inputs |
| Vector store collections | CRUD operations on vector store collections (upsert, get, delete) |
| Vector search | Unified search interface with `search_type` parameter (`"vector"`, `"keyword_hybrid"`) |
| Data model decorator | `@vectorstoremodel` decorator for defining vector store data models (supports Pydantic, dataclasses, plain classes, dicts) |
| Agent tools | `create_search_tool`, `create_upsert_tool`, `create_get_tool`, `create_delete_tool` for agent-usable vector store operations |
| In-memory store | Zero-dependency vector store for testing and development |
| 13+ connectors | Azure AI Search, Qdrant, Redis, PostgreSQL, MongoDB, Cosmos DB, Pinecone, Chroma, Weaviate, Oracle, SQL Server, FAISS |

## Key Design Decisions

### Embedding Abstractions (combining SK + MEAI)
- **Both Protocol and Base class** (matching AF's `SupportsChatGetResponse` + `BaseChatClient` pattern):
  - `SupportsGetEmbeddings` — Protocol for duck-typing
  - `BaseEmbeddingClient` — ABC base class for implementations (similar to `BaseChatClient`)
- **Generic input type** (`EmbeddingInputT`, default `str`) from MEAI — allows image/audio embeddings in the future
- **Generic output type** (`EmbeddingT`, default `list[float]`) from MEAI — supports `list[float]`, `list[int]`, `bytes`, etc.
- **Generic order**: `[EmbeddingInputT, EmbeddingT, EmbeddingOptionsT]` — options last, matching MEAI's `IEmbeddingGenerator<TInput, TEmbedding>` with options appended
- **TypeVar naming convention**: Use `SuffixT` per AF standard (e.g., `EmbeddingInputT`, `EmbeddingT`, `ModelT`, `KeyT`)
- `EmbeddingGenerationOptions` TypedDict (inspired by MEAI, matching AF's `ChatOptions` pattern) — `total=False`, includes `dimensions`, `model_id`. No `additional_properties` since each implementation extends with its own fields.
- Protocol and base class are generic over input, output, and options: `SupportsGetEmbeddings[EmbeddingInputT, EmbeddingT, OptionsContraT]`, `BaseEmbeddingClient[EmbeddingInputT, EmbeddingT, OptionsCoT]`
- **`Embedding[EmbeddingT]` type** in `_types.py` — a lightweight generic class (not Pydantic) with `vector: EmbeddingT`, `model_id: str | None`, `dimensions: int | None` (explicit or computed from vector), `created_at: datetime | None`, `additional_properties: dict[str, Any]`
- **`GeneratedEmbeddings[EmbeddingT, EmbeddingOptionsT]` type** — a list-like container of `Embedding[EmbeddingT]` objects with `options: EmbeddingOptionsT | None` (stores the options used to generate), `usage: dict[str, Any] | None`, `additional_properties: dict[str, Any]`
- **No numpy dependency** — return `list[float]` by default; users cast as needed

### Vector Store Abstractions
- **Port core abstractions without Pydantic for internal classes** — use plain classes
- **Both Protocol and Base class** for vector store operations (matching AF pattern):
  - `SupportsVectorUpsert` / `SupportsVectorSearch` — Protocols for duck-typing (follows `Supports<Capability>` naming convention)
  - `BaseVectorCollection` / `BaseVectorSearch` — ABC base classes for implementations
  - `BaseVectorStore` — ABC base class for store operations (factory for collections, no protocol needed)
- **TypeVar naming convention**: `ModelT`, `KeyT`, `FilterT` (suffix T, per AF standard)
- **Support Pydantic for user-facing data models** — the `@vectorstoremodel` decorator and `VectorStoreCollectionDefinition` should work with Pydantic models, dataclasses, plain classes, and dicts
- **Remove SK-specific dependencies** — no `KernelBaseModel`, `KernelFunction`, `KernelParameterMetadata`, `kernel_function`, `PromptExecutionSettings`
- **Embedding types in `_types.py`**, embedding protocol/base class in `_clients.py`
- **All vector store specific types, enums, protocols, base classes** in `_vectors.py`
- **Error handling** uses AF's exception hierarchy (e.g., `IntegrationException` variants)

### Package Structure
- **Embedding types** (`Embedding`, `GeneratedEmbeddings`, `EmbeddingGenerationOptions`) in `agent_framework/_types.py`
- **Embedding protocol + base class** (`SupportsGetEmbeddings`, `BaseEmbeddingClient`) in `agent_framework/_clients.py`
- **All vector store specific code** in a new `agent_framework/_vectors.py` module — this includes:
  - Enums: `FieldTypes`, `IndexKind`, `DistanceFunction`
  - `VectorStoreField`, `VectorStoreCollectionDefinition`
  - `SearchOptions`, `SearchResponse`, `RecordFilterOptions`
  - `@vectorstoremodel` decorator
  - Serialization/deserialization protocols
  - `VectorStoreRecordHandler`, `BaseVectorCollection`, `BaseVectorStore`, `BaseVectorSearch`
  - `SupportsVectorUpsert`, `SupportsVectorSearch` protocols
- **OpenAI embeddings** in `agent_framework/openai/` (built into core, like OpenAI chat)
- **Azure OpenAI embeddings** in `agent_framework/azure/` (built into core, follows `AzureOpenAIChatClient` pattern)
- **Each vector store connector** in its own AF package under `packages/`
- **In-memory store** in core (no external deps)
- **TextSearch and its implementations** (Brave, Google) — last phase, separate work

## Naming: SK → AF

### Names that change

| SK Name | AF Name | Rationale |
|---------|---------|-----------|
| `VectorStoreCollection` | `BaseVectorCollection` | Drop redundant `Store`, add `Base` prefix per AF pattern |
| `VectorStore` | `BaseVectorStore` | Add `Base` prefix per AF pattern |
| `VectorSearch` | `BaseVectorSearch` | Add `Base` prefix per AF pattern |
| `VectorSearchOptions` | `SearchOptions` | Shorter — context is already vector search |
| `VectorSearchResult` | `SearchResponse` | Align with `ChatResponse`/`AgentResponse` |
| `GetFilteredRecordOptions` | `RecordFilterOptions` | Shorter, more natural |
| `EmbeddingGeneratorBase` | `BaseEmbeddingClient` | Matches AF `BaseChatClient` pattern |
| `VectorStoreCollectionProtocol` | `SupportsVectorUpsert` | AF `Supports*` naming convention |
| `VectorSearchProtocol` | `SupportsVectorSearch` | AF `Supports*` naming convention |
| `__kernel_vectorstoremodel__` | `__vectorstoremodel__` | Drop SK `kernel` prefix |
| `__kernel_vectorstoremodel_definition__` | `__vectorstoremodel_definition__` | Drop SK `kernel` prefix |
| `search()` + `hybrid_search()` | `search(search_type=...)` | Single method with `Literal` parameter |
| `SearchType` enum | `Literal["vector", "keyword_hybrid"]` | No enum, just a literal |
| `KernelSearchResults` | `SearchResults` | Drop SK `Kernel` prefix (plural — container of `SearchResponse` items) |

### Names that stay the same

| Name | Location |
|------|----------|
| `@vectorstoremodel` | `_vectors.py` |
| `VectorStoreField` | `_vectors.py` |
| `VectorStoreCollectionDefinition` | `_vectors.py` |
| `VectorStoreRecordHandler` | `_vectors.py` |
| `FieldTypes` | `_vectors.py` |
| `IndexKind` | `_vectors.py` |
| `DistanceFunction` | `_vectors.py` |
| `DISTANCE_FUNCTION_DIRECTION_HELPER` | `_vectors.py` |
| `Embedding` | `_types.py` |
| `GeneratedEmbeddings` | `_types.py` |
| `EmbeddingGenerationOptions` | `_types.py` |
| `SupportsGetEmbeddings` | `_clients.py` |

### New AF-only names (no SK equivalent)

| Name | Location | Purpose |
|------|----------|---------|
| `BaseEmbeddingClient` | `_clients.py` | ABC base for embedding implementations |
| `EmbeddingInputT` | `_types.py` | TypeVar for generic embedding input (default `str`) |
| `EmbeddingTelemetryLayer` | `observability.py` | MRO-based OTel tracing for embeddings |
| `SupportsVectorUpsert` | `_vectors.py` | Protocol for collection CRUD |
| `SupportsVectorSearch` | `_vectors.py` | Protocol for vector search |
| `create_search_tool` | `_vectors.py` | Creates AF `FunctionTool` from vector search |

## Source Files Reference (SK → AF mapping)

### SK Source Files
| SK File | Lines | Content |
|---------|-------|---------|
| `data/vector.py` | 2369 | All vector store abstractions, enums, decorator, search |
| `data/_shared.py` | 184 | SearchOptions, KernelSearchResults, shared search types |
| `data/text_search.py` | 349 | TextSearch base, TextSearchResult |
| `connectors/ai/embedding_generator_base.py` | 50 | EmbeddingGeneratorBase ABC |
| `connectors/in_memory.py` | 520 | InMemoryCollection, InMemoryStore |
| `connectors/azure_ai_search.py` | 793 | Azure AI Search collection + store |
| `connectors/azure_cosmos_db.py` | 1104 | Cosmos DB (Mongo + NoSQL) |
| `connectors/redis.py` | 845 | Redis (Hashset + JSON) |
| `connectors/qdrant.py` | 653 | Qdrant collection + store |
| `connectors/postgres.py` | 987 | PostgreSQL collection + store |
| `connectors/mongodb.py` | 633 | MongoDB Atlas collection + store |
| `connectors/pinecone.py` | 691 | Pinecone collection + store |
| `connectors/chroma.py` | 484 | Chroma collection + store |
| `connectors/faiss.py` | 278 | FAISS (extends InMemory) |
| `connectors/weaviate.py` | 804 | Weaviate collection + store |
| `connectors/oracle.py` | 1267 | Oracle collection + store |
| `connectors/sql_server.py` | 1132 | SQL Server collection + store |
| `connectors/ai/open_ai/services/open_ai_text_embedding.py` | 91 | OpenAI embedding impl |
| `connectors/ai/open_ai/services/open_ai_text_embedding_base.py` | 78 | OpenAI embedding base |
| `connectors/brave.py` | ~200 | Brave TextSearch impl |
| `connectors/google_search.py` | ~200 | Google TextSearch impl |

---

## Implementation Phases

### Phase 1: Core Embedding Abstractions & OpenAI Implementation
**Goal:** Establish the embedding generator abstraction and ship one working implementation.
**Mergeable:** Yes — adds new types/protocols, no breaking changes.

#### 1.1 — Embedding types in `_types.py`
- `EmbeddingInputT` TypeVar (default `str`) — generic input type for embedding generation
- `EmbeddingT` TypeVar (default `list[float]`) — generic output embedding vector type
- `Embedding[EmbeddingT]` generic class: `vector: EmbeddingT`, `model_id: str | None`, `dimensions: int | None` (explicit param or computed from vector length), `created_at: datetime | None`, `additional_properties: dict[str, Any]`
- `GeneratedEmbeddings[EmbeddingT, EmbeddingOptionsT]` generic class: list-like container of `Embedding[EmbeddingT]` objects with `options: EmbeddingOptionsT | None` (the options used to generate), `usage: dict[str, Any] | None`, `additional_properties: dict[str, Any]`
- `EmbeddingGenerationOptions` TypedDict (`total=False`): `dimensions: int`, `model_id: str` — follows the same pattern as `ChatOptions`. No `additional_properties` needed since it's a TypedDict and each implementation can extend with its own fields.

#### 1.2 — Embedding generator protocol + base class in `_clients.py`
- `SupportsGetEmbeddings(Protocol[EmbeddingInputT, EmbeddingT, OptionsContraT])`: generic over input, output, and options (all with defaults), `get_embeddings(values: Sequence[EmbeddingInputT], *, options: OptionsContraT | None = None) -> Awaitable[GeneratedEmbeddings[EmbeddingT]]`
- `BaseEmbeddingClient(ABC, Generic[EmbeddingInputT, EmbeddingT, OptionsCoT])`: ABC base class mirroring `BaseChatClient` pattern
  - `__init__` with `additional_properties`, etc.
  - Abstract `get_embeddings(...)` for subclasses to implement directly (no `_inner_*` indirection — simpler than chat, no middleware needed)
- `EmbeddingTelemetryLayer` in `observability.py` — MRO-based telemetry (no closure), `gen_ai.operation.name = "embeddings"`

#### 1.3 — OpenAI embedding generator in `agent_framework/openai/` and `agent_framework/azure/`
- `RawOpenAIEmbeddingClient` — implements `get_embeddings` via `_ensure_client()` factory
- `OpenAIEmbeddingClient(OpenAIConfigMixin, EmbeddingTelemetryLayer[str, list[float], OptionsT], RawOpenAIEmbeddingClient[OptionsT])` — full client with config + telemetry layers
- `OpenAIEmbeddingOptions(EmbeddingGenerationOptions)` — extends with `encoding_format`, `user`
- `AzureOpenAIEmbeddingClient` in `agent_framework/azure/` — follows `AzureOpenAIChatClient` pattern with `AzureOpenAIConfigMixin`, `load_settings`, Entra ID credential support
- `AzureOpenAISettings` extended with `embedding_deployment_name` (env var: `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME`)

#### 1.4 — Tests and samples
- Unit tests for types, protocol, base class, OpenAI client, Azure OpenAI client
- Integration tests for OpenAI and Azure OpenAI (gated behind credentials check, `@pytest.mark.flaky`)
- Samples in `samples/02-agents/embeddings/` — `openai_embeddings.py`, `azure_openai_embeddings.py`

---

### Phase 2: Embedding Generators for Existing Providers
**Goal:** Add embedding generators to all existing AF provider packages that have chat clients.
**Mergeable:** Yes — each is independent, added to existing provider packages.

#### 2.1 — Azure AI Inference embedding (in `packages/azure-ai/`)
#### 2.2 — Ollama embedding (in `packages/ollama/`)
#### 2.3 — Anthropic embedding (in `packages/anthropic/`)
#### 2.4 — Bedrock embedding (in `packages/bedrock/`)

---

### Phase 3: Core Vector Store Abstractions
**Goal:** Establish all vector store types, enums, the decorator, collection definition, and base classes.
**Mergeable:** Yes — adds new abstractions, no breaking changes.

#### 3.1 — Vector store enums and field types in `_vectors.py`
- `FieldTypes` enum: `KEY`, `VECTOR`, `DATA`
- `IndexKind` enum: `HNSW`, `FLAT`, `IVF_FLAT`, `DISK_ANN`, `QUANTIZED_FLAT`, `DYNAMIC`, `DEFAULT`
- `DistanceFunction` enum: `COSINE_SIMILARITY`, `COSINE_DISTANCE`, `DOT_PROD`, `EUCLIDEAN_DISTANCE`, `EUCLIDEAN_SQUARED_DISTANCE`, `MANHATTAN`, `HAMMING`, `DEFAULT`
- No `SearchType` enum — use `Literal["vector", "keyword_hybrid"]` instead, per AF convention of avoiding unnecessary imports
- `VectorStoreField` plain class (not Pydantic)
- `VectorStoreCollectionDefinition` class (not Pydantic internally, but supports Pydantic models as input)
- `SearchOptions` plain class — includes `score_threshold: float | None` for filtering results by score (see note below)
- `SearchResponse` generic class
- `RecordFilterOptions` plain class
- `DISTANCE_FUNCTION_DIRECTION_HELPER` dict

#### 3.2 — `@vectorstoremodel` decorator
- Port from SK, works with dataclasses, Pydantic models, plain classes, and dicts
- Sets `__vectorstoremodel__` and `__vectorstoremodel_definition__` on the class
- Remove SK-specific `kernel` prefix (`__kernel_vectorstoremodel__` → `__vectorstoremodel__`)

#### 3.3 — Serialization/deserialization protocols
- `SerializeMethodProtocol`, `ToDictFunctionProtocol`, `FromDictFunctionProtocol`, etc.
- Port the record handler logic but without Pydantic base class — use plain class or ABC

#### 3.4 — Vector store base classes in `_vectors.py`
- `VectorStoreRecordHandler` — internal base class that handles serialization/deserialization between user data models and store-specific formats, plus embedding generation for vector fields. Both `BaseVectorCollection` and `BaseVectorSearch` extend this.
- `BaseVectorCollection(VectorStoreRecordHandler)` — base for collections
  - Uses `SupportsGetEmbeddings` instead of `EmbeddingGeneratorBase`
  - Not a Pydantic model — use `__init__` with explicit params
  - `upsert`, `get`, `delete`, `ensure_collection_exists`, `collection_exists`, `ensure_collection_deleted`
  - Async context manager support
- `BaseVectorStore` — base for stores
  - `get_collection`, `list_collection_names`, `collection_exists`, `ensure_collection_deleted`
  - Async context manager support

#### 3.5 — Vector search base class
- `BaseVectorSearch(VectorStoreRecordHandler)` — base for vector search
  - Single `search(search_type=...)` method with `search_type: Literal["vector", "keyword_hybrid"]` parameter — no enum, just a literal
  - `_inner_search` abstract method for implementations
  - Filter building with lambda parser (AST-based)
  - Vector generation from values using embedding generator

#### 3.6 — Protocols for type checking
- `SupportsVectorUpsert` — Protocol for upsert/get/delete operations
- `SupportsVectorSearch` — Protocol for vector search (single `search()` with `search_type` parameter)
- No separate `SupportsVectorHybridSearch` — search type is a parameter, not a separate capability
- No protocol for `VectorStore` — it's a factory for collections, not a capability to duck-type against

#### 3.7 — Exception types
- Add vector store exceptions under `IntegrationException` or create new branch
- `VectorStoreException`, `VectorStoreOperationException`, `VectorSearchException`, `VectorStoreModelException`, etc.

#### 3.8 — `create_search_tool` on `BaseVectorSearch`
- Method on `BaseVectorSearch` that creates an AF `FunctionTool` from the vector search
- Wraps the single `search()` method, passing `search_type` parameter
- Accepts: `name`, `description`, `search_type`, `top`, `skip`, `filter`, `string_mapper`
- The tool takes a query string, vectorizes it, searches, and returns results as strings
- Can also be a standalone factory function in `_vectors.py`

#### 3.9 — Tests for all vector store abstractions
- Unit tests for enums, field types, collection definition
- Unit tests for decorator
- Unit tests for serialization/deserialization
- Unit tests for record handler

---

### Phase 4: In-Memory Vector Store
**Goal:** Provide a zero-dependency vector store for testing and development.
**Mergeable:** Yes — first usable vector store.

#### 4.1 — Port `InMemoryCollection` and `InMemoryStore` into core
- Place in `agent_framework/_vectors.py` (alongside the abstractions)
- Supports vector search (cosine similarity, etc.)
- No external dependencies

#### 4.2 — Port FAISS extension (optional, can be separate package)
- Extends InMemory with FAISS indexing

#### 4.3 — Tests and sample code

---

### Phase 5: Vector Store Connectors — Tier 1 (High Priority)
**Goal:** Ship the most commonly used vector store connectors.
**Mergeable:** Yes — each connector is independent.

Each connector follows the AF package structure:
- New package under `packages/`
- Own `pyproject.toml`, `tests/`, lazy loading in core

#### 5.1 — Azure AI Search (`packages/azure-ai-search/`)
- May extend existing package or be new
- `AzureAISearchCollection`, `AzureAISearchStore`

#### 5.2 — Qdrant (`packages/qdrant/`)
- New package
- `QdrantCollection`, `QdrantStore`

#### 5.3 — Redis (`packages/redis/`)
- May extend existing redis package
- `RedisCollection` (JSON + Hashset variants), `RedisStore`

#### 5.4 — PostgreSQL/pgvector (`packages/postgres/`)
- New package
- `PostgresCollection`, `PostgresStore`

---

### Phase 6: Vector Store Connectors — Tier 2
**Goal:** Ship remaining vector store connectors.
**Mergeable:** Yes — each connector is independent.

#### 6.1 — MongoDB Atlas (`packages/mongodb/`)
#### 6.2 — Azure Cosmos DB (`packages/azure-cosmos-db/`)
- Cosmos Mongo + Cosmos NoSQL
#### 6.3 — Pinecone (`packages/pinecone/`)
#### 6.4 — Chroma (`packages/chroma/`)
#### 6.5 — Weaviate (`packages/weaviate/`)

---

### Phase 7: Vector Store Connectors — Tier 3
**Goal:** Ship niche or less common connectors.
**Mergeable:** Yes — each connector is independent.

#### 7.1 — Oracle (`packages/oracle/`)
#### 7.2 — SQL Server (`packages/sql-server/`)
#### 7.3 — FAISS (`packages/faiss/` or in core extending InMemory)

> **Note:** When implementing any SQL-based connector (PostgreSQL, SQL Server, SQLite, Cosmos DB), review the .NET MEVD changes made by @roji (Shay Rojansky) in SK for design patterns, query building, filter translation, and feature parity: https://github.com/microsoft/semantic-kernel/pulls?q=is%3Apr+author%3Aroji+is%3Aclosed

---

### Phase 8: Vector Store CRUD Tools
**Goal:** Provide a full set of agent-usable tools for CRUD operations on vector store collections.
**Mergeable:** Yes — adds tools without changing existing APIs.

#### 8.1 — `create_upsert_tool` — tool for upserting records into a collection
#### 8.2 — `create_get_tool` — tool for retrieving records by key
- Key-based lookup only (by primary key), not a search tool
- Documentation must clearly distinguish this from `create_search_tool`: get_tool retrieves specific records by their known key, while search_tool performs similarity/filtered search across the collection
- Consider if this overlaps with filtered search and document when to use which
#### 8.3 — `create_delete_tool` — tool for deleting records by key
#### 8.4 — Tests and samples for CRUD tools

---

### Phase 9: Additional Embedding Implementations (New Providers)
**Goal:** Provide embedding generators for providers that don't yet have AF packages.
**Mergeable:** Yes — each is independent, new packages.

#### 9.1 — HuggingFace/ONNX embedding (new package or lab)
#### 9.2 — Mistral AI embedding (new package)
#### 9.3 — Google AI / Vertex AI embedding (new package)
#### 9.4 — Nvidia embedding (new package)

---

### Phase 10: TextSearch Abstractions & Implementations (Separate Work)
**Goal:** Port text search (non-vector) abstractions and implementations.
**Mergeable:** Yes — independent of vector stores.

#### 10.1 — TextSearch base class and types
- `SearchOptions`, `SearchResponse`, `TextSearchResult`
- `TextSearch` base class with `search()` method
- `create_search_function()` for kernel integration (may need AF equivalent)

#### 10.2 — Brave Search implementation
#### 10.3 — Google Search implementation
#### 10.4 — Vector store text search bridge (connecting VectorSearch to TextSearch interface)

---

## Key Considerations

1. **No Pydantic for internal classes**: All AF internal classes should use plain classes. Pydantic is only used for user-facing input validation (e.g., vector store data models).

2. **Protocol + Base class**: Follow AF's pattern of both a `Protocol` for duck-typing and a `Base` ABC for implementation, matching how `SupportsChatGetResponse` + `BaseChatClient` works.

3. **Exception hierarchy**: Use AF's `IntegrationException` branch for vector store operations, since vector stores are external dependencies.

4. **`from __future__ import annotations`**: Required in all files per AF coding standard.

5. **No `**kwargs` escape hatches in public APIs**: For user-facing interfaces, use explicit named parameters per AF coding standard. Internal implementation details (e.g., cooperative multiple inheritance / MRO patterns) may use `**kwargs` where necessary, as long as they are not exposed in public signatures.

6. **Lazy loading**: Connector packages use `__getattr__` lazy loading in core provider folders.

7. **Reusable data models**: The `@vectorstoremodel` decorator and `VectorStoreCollectionDefinition` should be agnostic enough to work with both SK and AF. The core types (`FieldTypes`, `IndexKind`, `DistanceFunction`, `VectorStoreField`) should be identical or easily mapped.

8. **`create_search_tool`**: The AF-native equivalent of SK's `create_search_function`. Instead of creating a `KernelFunction`, this creates an AF `FunctionTool` (via the `@tool` decorator pattern) from a vector search. This allows agents to use vector search as a tool during conversations. Design:
   - `create_search_tool(name, description, search_type, ...)` → returns a `FunctionTool` that wraps `VectorSearch.search(search_type=...)`
   - The tool accepts a query string, performs embedding + vector search, and returns results as strings
   - Supports configurable string mappers, filter functions, top/skip defaults
   - Lives in `_vectors.py` as a method on `BaseVectorSearch` and/or as a standalone factory function

9. **CRUD tools**: A full set of create/read/update/delete tools for vector store collections, allowing agents to manage data in vector stores. Design:
   - `create_upsert_tool(...)` → tool for upserting records
   - `create_get_tool(...)` → tool for retrieving records by key
   - `create_delete_tool(...)` → tool for deleting records
   - These are separate from search and are placed in a later phase

10. **Score threshold filtering**: `SearchOptions` includes `score_threshold: float | None` to filter search results by relevance score (ref: [SK .NET PR #13501](https://github.com/microsoft/semantic-kernel/pull/13501)). The semantics depend on the distance function: for similarity functions (cosine similarity, dot product), results *below* the threshold are filtered out; for distance functions (cosine distance, euclidean), results *above* the threshold are filtered out. Use `DISTANCE_FUNCTION_DIRECTION_HELPER` to determine direction. Connectors should implement this natively where the database supports it, falling back to client-side post-filtering otherwise.
