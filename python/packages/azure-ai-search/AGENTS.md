# Azure AI Search Package (agent-framework-azure-ai-search)

Integration with Azure AI Search for RAG (Retrieval-Augmented Generation) and vector storage.

## Main Classes

- **`AzureAISearchContextProvider`** - Context provider that retrieves relevant documents from Azure AI Search
- **`AzureAISearchSettings`** - TypedDict settings for Azure AI Search configuration
- **`AzureAISearchCollection`** - Experimental async vector/index collection with batch CRUD and native search
- **`AzureAISearchStore`** - Experimental collection factory, index lifecycle, and index alias operations

## API versions: stable vs preview

The package depends on `azure-search-documents>=12.0.0,<13`, which spans both channels, and
auto-detects which build is installed — there is no `api_version` parameter:

| Channel | Install | SDK | Data-plane `api-version` (chosen by the SDK) |
| --- | --- | --- | --- |
| **Stable / GA** | `pip install azure-search-documents` | `12.0.0` | `2026-04-01` |
| **Preview** | `pip install --pre azure-search-documents` | `12.1.0b2` | `2026-08-01-preview` |

The provider never pins an `api-version`; the installed build picks its own default, so newer
releases work without code changes (single source of truth = the install).

Capability gating keys off `_preview_agentic_features_available` — whether the preview build's
agentic symbols (`KnowledgeRetrieval{Low,Medium}ReasoningEffort`, `KnowledgeRetrievalOutputMode`)
can be imported. Agentic **output mode** (`answer_synthesis`) and **extended reasoning effort**
(`low`/`medium`) ship only in the preview build; on a stable build the provider omits them
(extractive + minimal) and raises an actionable `ValueError` (citing the installed version) if
they are explicitly requested. Semantic mode is unaffected.

Agentic query-time user identity is also preview-only. It is gated by
`_query_source_authorization_available`; when enabled, `query_source_credential` supplies a
per-request Azure AI Search token through the `x-ms-query-source-authorization` header. Both sync
and async Azure token credentials are supported, starting with `azure-search-documents>=12.1.0b1`.

## Usage

```python
from agent_framework.azure import AzureAISearchContextProvider

provider = AzureAISearchContextProvider(
    endpoint="https://your-search.search.windows.net",
    index_name="your-index",
)
agent = Agent(..., context_provider=provider)
```

## Import Path

```python
from agent_framework.azure import AzureAISearchContextProvider
# or directly:
from agent_framework_azure_ai_search import AzureAISearchContextProvider
```

## Vector connector

`_vector_store.py` is the single vector connector implementation module: concrete SDK/settings and
filter-condition helpers, then `AzureAISearchCollection`, then `AzureAISearchStore`. Both classes use
core registration, codecs, batch CRUD, and `SearchResults`. Collection `_prepare_filter` owns support
guards and OData translation for both filtered get and search; `_validate_operation_options` rejects
unsupported options before I/O. Codec/filter/query helpers precede `_inner_upsert`, `_inner_get`,
`_inner_delete`, `_inner_search`, and result extraction. Store administration precedes its close methods.
Do not migrate/refactor the existing ContextProvider as part of vector connector work.

Write serialization validates all keys and vector elements once before upload. Upload preflight
accounts for SDK JSON escaping, spacing, action metadata, and the batch envelope, rejecting a
single oversized document before any batch I/O. It retains batch boundaries, not copies of
serialized vector payloads. Numeric write validation follows the configured EDM storage type;
query vectors follow the service's floating-point query contract instead of integer storage limits.
New vector schemas default to retrievable unless explicitly disabled or unstored. Both constructors
validate query credentials before resolving connection settings or creating owned clients.

Both constructors create owned clients through `_create_index_client`, reusing `AzureAISearchSettings`
and the public AF `load_settings` / `SecretString` API with the `AZURE_SEARCH_` prefix. Explicit settings
override the selected `.env` file, which overrides the process environment. `env_file_path` and
`env_file_encoding` are supported on both. Injected clients bypass settings entirely and reject explicit
connection/file overrides; store-created collections reuse its resolved client without another load.
The store tracks open collections in insertion order with constant-time removal. A collection's
private close callback removes its registration and is cleared even when client cleanup fails;
store shutdown still attempts all remaining owned clients without closing borrowed credentials.

Keep the package exports and core `agent_framework/azure/__init__.py` / `__init__.pyi` synchronized.
Read the package README for supported field annotations, operation options, score units, null/missing
restrictions, ownership, and stable/preview capability gates. Preview gates check SDK capabilities and
the actual outgoing API version before transport; never silently drop query identity or thresholds.

Service tests require dedicated AZURE_SEARCH_VECTOR_TEST_* settings and explicit opt-in; SDK mocks
are not evidence of live-service behavior.
