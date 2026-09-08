# Vector Stores and Embeddings

## Overview

This feature ports the vector store abstractions, embedding generator abstractions, and their implementations from Semantic Kernel into Agent Framework. The ported code follows AF's coding standards, feels native to AF, and is structured to allow data models/schemas to be reusable across both frameworks. The embedding abstraction combines the best of SK's `EmbeddingGeneratorBase` and MEAI's `IEmbeddingGenerator<TInput, TEmbedding>`.

| Capability | Description |
| --- | --- |
| Embedding generation | Generic embedding client abstraction supporting text, image, and audio inputs |
| Vector store collections | CRUD operations on vector store collections (upsert, get, delete) |
| Vector search | Unified search interface with `search_type` parameter (`"vector"`, `"keyword_hybrid"`) |
| Data model decorator | `@vectorstoremodel` decorator for defining vector store data models (supports Pydantic, dataclasses, plain classes, dicts) |
| Agent tools | `create_vector_search_tool`, `create_upsert_tool`, `create_get_tool`, `create_delete_tool` for agent-usable vector store operations |
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
- **TypeVar naming convention**: `ModelT`, `KeyT` (suffix T, per AF standard)
- **Support Pydantic for user-facing data models** — the `@vectorstoremodel` decorator and `VectorStoreCollectionDefinition` should work with Pydantic models, dataclasses, plain classes, and dicts
- **Remove SK-specific dependencies** — no `KernelBaseModel`, `KernelFunction`, `KernelParameterMetadata`, `kernel_function`, `PromptExecutionSettings`
- **Embedding types in `_types.py`**, embedding protocol/base class in `_clients.py`
- **Portable filters** are data-only operation inputs in `_vector_filters.py`; no Python source or AST translation
- **Dependency-free local storage** is isolated in `_in_memory.py`
- **Vector store definitions, protocols, and base classes** remain in `_vectors.py`
- **Error handling** uses AF's exception hierarchy (e.g., `IntegrationException` variants)

### Vector Filter Representation

The original Phase 3 design accepted callable or string lambdas, recovered
their source with `inspect`, parsed the source into an AST, and delegated
translation to each connector. Phase 4 replaces that experimental model before
connector implementations depend on it.

Options considered:

- **Lambda source and connector-specific AST translation** — concise authoring,
  but brittle across Python execution contexts, vulnerable to semantic drift,
  and carries security concerns when evaluated locally.
- **A closed class hierarchy with one type per operation** — strongly typed,
  but every provider-specific capability would require another core type.
- **A small data-only tree with namespaced provider extensions** — chosen.
  `Filter` represents a field, operator, and value; `FilterGroup` provides
  explicit AND, OR, and NOT composition; `Param` marks model-set values when
  creating a search tool. Common operators have shared semantics, while
  namespaced operators let connectors add structured provider capabilities
  without accepting raw query source.

### Package Structure
- **Embedding types** (`Embedding`, `GeneratedEmbeddings`, `EmbeddingGenerationOptions`) in `agent_framework/_types.py`
- **Embedding protocol + base class** (`SupportsGetEmbeddings`, `BaseEmbeddingClient`) in `agent_framework/_clients.py`
- **Vector store abstractions** in `agent_framework/_vectors.py` — this includes:
  - String literal aliases: `FieldTypes`, `IndexKind`, `DistanceFunction`
  - `VectorStoreField`, `VectorStoreCollectionDefinition`
  - `SearchResponse`, `SearchResults`, and explicit CRUD/search keyword arguments
  - `@vectorstoremodel` decorator
  - `register_vectorstoremodel` with msgspec-backed default codecs and optional custom codecs
  - Internal record conversion shared by `BaseVectorCollection` and `BaseVectorSearch`
  - `SupportsVectorUpsert`, `SupportsVectorSearch` protocols
- **OpenAI embeddings** in `agent_framework/openai/` (built into core, like OpenAI chat)
- **Azure OpenAI embeddings** in `agent_framework/azure/` (built into core, follows `AzureOpenAIChatClient` pattern)
- **Each vector store connector** in its own AF package under `packages/`
- **Portable filters** (`Filter`, `FilterGroup`, `Param`) in `agent_framework/_vector_filters.py`
- **In-memory store** in `agent_framework/_in_memory.py`

## Naming: SK → AF

### Names that change

| SK Name | AF Name | Rationale |
|---------|---------|-----------|
| `VectorStoreCollection` | `BaseVectorCollection` | Drop redundant `Store`, add `Base` prefix per AF pattern |
| `VectorStore` | `BaseVectorStore` | Add `Base` prefix per AF pattern |
| `VectorSearch` | `BaseVectorSearch` | Add `Base` prefix per AF pattern |
| `VectorSearchOptions` | Explicit `search()` keyword arguments | Avoid an options object that only forwards values |
| `VectorSearchResult` | `SearchResponse` | Align with `ChatResponse`/`AgentResponse` |
| `GetFilteredRecordOptions` | Explicit `get()` keyword arguments | Avoid an options object that only forwards values |
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
| `create_vector_search_tool` | `_vectors.py` | Creates AF `FunctionTool` from vector search |

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

### Phase 1: Core Embedding Abstractions & OpenAI Implementation ✅ DONE
**Goal:** Establish the embedding generator abstraction and ship one working implementation.
**Mergeable:** Yes — adds new types/protocols, no breaking changes.
**Status:** Merged via PR #4153. Closes sub-issue #4163.

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

#### 2.1 — Foundry inference embedding (in `packages/foundry/`)
#### 2.2 — Ollama embedding (in `packages/ollama/`)
#### 2.3 — Anthropic embedding (in `packages/anthropic/`)
#### 2.4 — Bedrock embedding (in `packages/bedrock/`)

---

### Phase 3: Core Vector Store Abstractions
**Goal:** Establish all vector store types, enums, the decorator, collection definition, and base classes.
**Mergeable:** Yes — adds new abstractions, no breaking changes.
**Feature stage:** Experimental (`VECTOR_STORES`).

#### 3.1 — Vector store literal aliases and field types in `_vectors.py`
- `FieldTypes`: `Literal["key", "vector", "data"]`
- `IndexKind`: common literal values for IDE guidance plus open provider-defined strings
- `DistanceFunction`: common literal values, including negative dot product, plus open provider-defined strings
- `SearchType`: `Literal["vector", "keyword_hybrid"]`
- `VectorStoreField` plain class (not Pydantic)
  - Key fields can opt into store-generated keys
  - Provider annotations are copied on construction and carry mutable connector-specific field configuration
- `VectorStoreCollectionDefinition` class (not Pydantic internally, but supports Pydantic models as input)
- `SearchResponse` generic `TypedDict`
- `SearchResults` generic result container
- Explicit keyword arguments on `get()` and `search()` instead of options classes
- `DISTANCE_FUNCTION_DIRECTION_HELPER` dict

#### 3.2 — `@vectorstoremodel` decorator
- Port from SK, works with dataclasses, Pydantic models, plain classes, and dicts
- Plain classes can declare `VectorStoreField` metadata on annotated `__init__` parameters, matching `@tool`
- Sets `__vectorstoremodel__` and `__vectorstoremodel_definition__` on the class
- Remove SK-specific `kernel` prefix (`__kernel_vectorstoremodel__` → `__vectorstoremodel__`)

#### 3.3 — Registered model codecs
- `register_vectorstoremodel` registers one collection definition and encoder/decoder pair per model type
- `@vectorstoremodel` creates the definition and registers msgspec-backed default codecs
- Dictionary records provide their collection definition directly
- DataFrames and other row containers convert to sequences of row mappings before using the batch API
- Custom encoder and decoder callbacks can be overridden independently
- Array-like values such as NumPy arrays serialize through their `tolist()` method without a NumPy dependency;
  supply a custom decoder that calls `numpy.array` or `numpy.asarray` when the model should restore an array

#### 3.4 — Vector store base classes in `_vectors.py`
- `_VectorStoreRecordHandler` — private base class that handles record conversion and embedding generation
- `BaseVectorCollection` — base for collections
  - Uses `SupportsGetEmbeddings` instead of `EmbeddingGeneratorBase`
  - Not a Pydantic model — use `__init__` with explicit params
  - Batch-oriented `upsert`, `get`, and `delete`
  - `upsert()` generates vector values by default and requires an embedding generator for every vector field;
    pass `generate_vectors=False` to preserve supplied vector values
  - `generate_vectors` can also take a list or tuple of selected vector field names, allowing one model to combine
    locally generated, precomputed, and provider-vectorized values
  - After optional generation, check materialized dense sequence lengths against each field's `dimensions` for the
    entire batch before connector conversion or writes. A mismatch raises `ValueError` with the zero-based record
    index, logical field name, and expected/actual lengths; this rejection performs no writes
  - Batch upsert does not promise atomicity; stable application keys make retries safer, while store-generated keys
    may produce duplicates after a partial failure
  - CRUD `get()` excludes vectors by default; pass `include_vectors=True` when stored embeddings are needed
  - CRUD `get()` accepts either keys or a portable filter with paging and ordering
  - `ensure_collection_exists`, `collection_exists`, `ensure_collection_deleted`
  - Async context manager support
- `BaseVectorStore` — base for stores
  - `get_collection`, `list_collection_names`, `collection_exists`, `ensure_collection_deleted`
  - Async context manager support

#### 3.5 — Vector search base class
- `BaseVectorSearch` — base for vector search
  - Single `search(search_type=...)` method with `search_type: Literal["vector", "keyword_hybrid"]` parameter — no enum, just a literal
  - `_inner_search` abstract method for implementations
  - Portable `Filter` and `FilterGroup` trees passed unchanged to connector implementations
  - Core validates portable request structure and deserializes returned records, but does not compute scores,
    interpret score thresholds, or re-filter connector results. Connectors own execution and paging
  - Vector generation from values using embedding generator
  - Check supplied or locally generated dense query length against the selected field's `dimensions` before
    connector dispatch, including empty collections. In-memory search also checks array-like queries after its
    numeric normalization; existing query/stored length checks remain in scoring

#### 3.6 — Protocols for type checking
- `SupportsVectorUpsert` — Protocol for upsert/get/delete operations
- `SupportsVectorSearch` — Protocol for vector search (single `search()` with `search_type` parameter)
- No separate `SupportsVectorHybridSearch` — search type is a parameter, not a separate capability
- No protocol for `VectorStore` — it's a factory for collections, not a capability to duck-type against

#### 3.7 — Exception types
- Use `ValueError` and `TypeError` for invalid arguments, model definitions, and record conversion
- Use `NotImplementedError` for connector capabilities that are not supported
- Use the existing `IntegrationException` and `IntegrationInvalidResponseException` at connector boundaries

#### 3.8 — `create_vector_search_tool`
- Standalone factory that creates an AF `FunctionTool` from any `SupportsVectorSearch` implementation
- Wraps the single `search()` method, passing `search_type` parameter
- Accepts: `name`, `description`, `approval_mode`, `search_type`, `top`, `skip`, `filter`, `result_mapper`
- Defaults to a required string `query`
- Discovers `Param` values in filters and paging options, generating a closed JSON Schema without Pydantic
- Validates model-set values against native Python types and inline constraints before resolving the filter
- The tool vectorizes the query, searches, and maps results to text or multimodal `Content`
- Can also be a standalone factory function in `_vectors.py`

#### 3.9 — Tests for all vector store abstractions
- Unit tests for enums, field types, collection definition
- Unit tests for decorator
- Unit tests for serialization/deserialization
- Unit tests for record handler

---

### Phase 4: Portable Filters and In-Memory Vector Store
**Goal:** Provide safe cross-store filters and a zero-dependency vector store for testing and development.
**Mergeable:** Yes — the filter contract and in-memory implementation can be reviewed independently.

#### 4.1 — Replace source filters with portable data
- `Filter(field_name, operator, value)` for leaf conditions
- `FilterGroup(operator, filters)` for explicit AND, OR, and NOT composition
- Common operators plus namespaced provider extensions
- No callable inspection, source strings, AST parsing, `eval`, `exec`, or `compile`

#### 4.1.1 — Connector extensibility aligned with Microsoft.Extensions.VectorData
- Index kinds and distance functions provide common literal hints but remain open to provider-defined strings
- `VectorStoreField.provider_annotations` is copied when the field is created and carries mutable provider-specific
  configuration; the frozen field protects core schema attributes, not nested provider values
- Key fields can declare `is_auto_generated=True`; connectors decide which generated key types they support
- Search already supports provider-side query vectorization: without a local generator, connectors receive the
  original `values` and `vector=None`
- Server-side write vectorization needs no core flag; leave that field out of `generate_vectors` so its source value
  reaches a connector that supports it
- Dense vectors support numeric sequences and binary `bytes`; supplied and generated mutable `bytearray` values
  normalize to `bytes`
- Float16, float32, float64, and integer element support remains connector-specific through `type_` and
  `supported_vector_types`
- Sparse vectors remain provider-native values supplied through model codecs or `search(values=...)`; core does not
  define a sparse representation or dense+sparse fusion mode

#### 4.1.2 — Dense vector dimension checks
- Enforce declared dimensions at the shared write and search boundaries by default. This replaces the earlier
  decision to leave dense length enforcement entirely to providers
- Check sequence length only, without copying, converting, or scanning elements solely for validation. Resolve
  vector fields and storage names once per write batch, and validate final values after any local generation
- Null vectors remain allowed. Source text and non-sequence provider-native values are not treated as dense
  vectors; `bytes`/`bytearray` length is not assumed to equal dimensionality. Connectors validate these representations
- The contract covers materialized non-string, non-binary sequences, not arbitrary provider-specific encodings,
  numeric element validity, or revalidation on retrieval. Provider-side vectorization remains unchanged
- Local benchmarking of 1,000-record batches found length checking inexpensive relative to serialization and
  in-memory copying. Use a straightforward pass without an opt-out flag or a more complex serialization path

#### 4.2 — Derive search-tool parameters from filters
- A `Param` used as a complete filter value defines its model-visible name, native type, default, and constraints
- The tool factory emits a closed JSON Schema and resolves parameters before search
- An absent optional parameter without a default removes its containing filter; fixed filters remain unchanged
- `omit_if_none=True` also removes the leaf when its resolved argument is `None` (JSON `null`). It requires a
  nullable type and an explicit `default=None`, for example
  `Param("text", str | None, default=None, omit_if_none=True)`. Absent/null arguments omit the leaf; non-null
  arguments retain normal type, constraint, and operator validation. This policy is not supported for paging.
- AND/OR groups evaluate their remaining children, not a `True` replacement for an omitted leaf. Groups left
  empty, including NOT groups whose child is removed, are removed recursively. If the whole tree is removed,
  search receives no filter; other search options still apply.
- Without the opt-in, explicit null values retain normal validation and provider semantics. Strings such as
  `"*"` are literal filter values, not omission markers.
- String operators reject non-string operands centrally, after substitution for parameterized leaves
- Defaults and supplied mutable parameter values are copied per invocation, including nested containers
- Bound structural inspection before copying: filter depth/node limits apply to the tree and collection members,
  including non-sequence collections such as sets; mapping keys cannot hide a `Param`. Limits also apply to
  search tools whose search implementation has no collection definition. Unknown field names remain
  connector-owned in that case
- Structural budgets do not sandbox arbitrary provider-native objects or trusted Python hooks

#### 4.3 — Add `InMemoryCollection` and `InMemoryStore`
- Dedicated `_in_memory.py` module
- Shared process-local collection state, full CRUD/listing/order behavior, and flat vector search
- Pure-Python distance functions with no NumPy or SciPy dependency
- Scoring, filters, and thresholds execute locally before paging. `DEFAULT` resolves to cosine distance and
  therefore accepts scores at or below the threshold, including zero for identical vectors
- Cosine calculations scale each vector independently to avoid overflow/underflow from finite magnitudes.
  Non-finite scores are rejected for every metric, and unsupported distance functions fail before scanning records
- Hamming distance is the proportion of unequal dimensions, not a mismatch count; scores and thresholds use
  the range zero to one, consistent with `scipy.spatial.distance.hamming`
- Strict filter evaluator over serialized mappings with the shared conservative resource limits
- Dictionary inputs and custom encoder outputs both pass through `msgspec.to_builtins` before storage, so
  ordinary filtering operates on normalized data rather than original object comparison methods. Custom codecs
  and connector overrides are trusted Python code, not a sandbox

#### 4.4 — Tests and samples
- Direct filter composition and model-set search-tool filter parameters
- Security regressions for fail-closed behavior, scope preservation, and the SK exploit class
- FAISS remains deferred to its own optional connector phase

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
- Documentation must clearly distinguish this from `create_vector_search_tool`: get_tool retrieves specific records by their known key, while the search tool performs similarity/filtered search across the collection
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
- `SearchResponse`, `TextSearchResult`, and explicit search keyword arguments
- `TextSearch` base class with `search()` method
- `create_search_function()` for kernel integration (may need AF equivalent)

#### 10.2 — Brave Search implementation
#### 10.3 — Google Search implementation
#### 10.4 — Vector store text search bridge (connecting VectorSearch to TextSearch interface)

---

## Key Considerations

1. **msgspec-backed conversion**: Use msgspec as the default serialization/deserialization path. Pydantic and plain classes remain supported user-model adapters.

2. **Protocol + Base class**: Follow AF's pattern of both a `Protocol` for duck-typing and a `Base` ABC for implementation, matching how `SupportsChatGetResponse` + `BaseChatClient` works.

3. **Exception hierarchy**: Use AF's `IntegrationException` branch for vector store operations, since vector stores are external dependencies.

4. **`from __future__ import annotations`**: Required in all files per AF coding standard.

5. **No `**kwargs` escape hatches in public APIs**: For user-facing interfaces, use explicit named parameters per AF coding standard. Internal implementation details (e.g., cooperative multiple inheritance / MRO patterns) may use `**kwargs` where necessary, as long as they are not exposed in public signatures.

6. **Lazy loading**: Connector packages use `__getattr__` lazy loading in core provider folders.

7. **Reusable data models**: The `@vectorstoremodel` decorator and `VectorStoreCollectionDefinition` should be agnostic enough to work with both SK and AF. The core types (`FieldTypes`, `IndexKind`, `DistanceFunction`, `VectorStoreField`) should be identical or easily mapped.

8. **`create_vector_search_tool`**: The AF-native equivalent of SK's `create_search_function`. Instead of creating a `KernelFunction`, this creates an AF `FunctionTool` from any `SupportsVectorSearch` implementation. This allows agents to use vector search as a tool during conversations. Design:
   - `create_vector_search_tool(search, name, description, search_type, ...)` returns a `FunctionTool`
   - The tool accepts `query` plus `Param` values discovered in filters or paging options
   - It generates a closed native JSON Schema, performs embedding + vector search, and returns text or multimodal content
   - Lives in `_vectors.py` without expanding the structural search protocol

9. **CRUD tools**: A full set of create/read/update/delete tools for vector store collections, allowing agents to manage data in vector stores. Design:
   - `create_upsert_tool(...)` → tool for upserting records
   - `create_get_tool(...)` → tool for retrieving records by key
   - `create_delete_tool(...)` → tool for deleting records
   - These are separate from search and are placed in a later phase

10. **Score threshold filtering**: Scoring, filter execution, score thresholds, and paging belong to the connector
    and backing store (ref: [SK .NET PR #13501](https://github.com/microsoft/semantic-kernel/pull/13501)). Core passes
    `score_threshold` through without requiring a known distance function or an explicit metric and does not
    post-filter returned results, including results without scores. Each connector defines its score units,
    threshold direction, and default metric. Execute filtering and thresholding natively where supported;
    otherwise implement an explicit connector-local fallback coordinated with paging, or reject the unsupported
    option rather than silently ignoring it. `DISTANCE_FUNCTION_DIRECTION_HELPER` remains available for
    connectors implementing comparisons for common metrics locally; it is not a core capability gate.
