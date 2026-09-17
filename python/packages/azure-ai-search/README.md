# Microsoft Agent Framework Azure AI Search

Connect [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/) agents
to [Azure AI Search](https://learn.microsoft.com/azure/search/) for retrieval and vector storage.

- **`AzureAISearchContextProvider`** adds retrieved context to agents using semantic
  search or Knowledge Base retrieval.
- **`AzureAISearchCollection`** provides asynchronous batch upsert, get, delete,
  vector search, and keyword-hybrid search.
- **`AzureAISearchStore`** creates collection clients and manages indexes and index aliases.

All three classes are available from `agent_framework.azure` or
`agent_framework_azure_ai_search`. The vector collection and store APIs are experimental.

## Installation

Requires Python 3.10 or later.

```bash
pip install agent-framework-azure-ai-search --pre
```

## Connection and authentication

You need an Azure AI Search service and permission to query its indexes. Writing
documents or managing indexes requires additional permissions. Existing indexes must
match your record model; semantic search requires a suitable semantic configuration,
and Knowledge Base retrieval requires a configured Knowledge Base.

Set `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_API_KEY`, or pass `endpoint` and
`api_key` explicitly. API keys accept strings or Agent Framework `SecretString`.
For Microsoft Entra ID authentication, install `azure-identity` and pass an async
Azure token credential as `credential` instead of an API key.
See [Azure AI Search role-based access](https://learn.microsoft.com/azure/search/search-security-rbac).

The package uses `AzureAISearchSettings` and Agent Framework settings resolution:
explicit values override the file selected by `env_file_path`, then environment variables.
`env_file_encoding` defaults to UTF-8. For the context provider, select an index with
`index_name` or `AZURE_SEARCH_INDEX_NAME`; for agentic mode, use
`mode="agentic"` and `knowledge_base_name` or `AZURE_SEARCH_KNOWLEDGE_BASE_NAME`.
Attach the provider through your agent's `context_provider` parameter.

Injected SDK clients bypass connection settings and remain caller-owned unless
`managed_client=True`. Use async context managers to close owned store/collection
clients; credentials and embedding clients remain caller-owned.

## Vector collections and stores (experimental)

This example queries an existing `documents` index with `id`, `text`, and a
three-dimensional `vector` field. Replace the example vector with an embedding
from the same model and dimensions used by your index.

```python
import asyncio
from dataclasses import dataclass
from typing import Annotated

from agent_framework import VectorStoreField, vectorstoremodel
from agent_framework.azure import AzureAISearchStore


@vectorstoremodel
@dataclass
class Document:
    id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    vector: Annotated[list[float] | None, VectorStoreField("vector", dimensions=3)] = None


async def main():
    async with AzureAISearchStore() as store:
        documents = store.get_collection(Document, collection_name="documents")
        async for result in await documents.search(vector=[1.0, 0.0, 0.0], top=3):
            print(result["record"].text, result["score"])


asyncio.run(main())
```

Use `ensure_collection_exists()` to create an absent index; it never updates an
existing index. CRUD methods accept batches and require application-provided string
keys of 1-1,024 ASCII letters, digits, `-`, `_`, or `=`, without a leading `_`.
Uploads are split by both the 1,000-action and 16 MiB request limits. All keys,
vector values, and individual document sizes are checked before the first upload;
service-side batch failures can still partially persist records.

Use `generate_vectors=False` when upserting precomputed vectors, or configure
an embedding generator. Text queries without a local generator require an integrated
vectorizer on the index. Search targets one top-level dense vector field at a time;
binary, sparse, and nested multivector payloads are not supported.

Vector elements must be finite non-boolean numbers within the configured EDM type's
range; `Edm.SByte` and `Edm.Int16` fields require integers. Query vectors use the
service's floating-point query contract, not the stored field's integer constraints.
New vector fields are retrievable by default for `include_vectors=True`. Set
`retrievable=False`, or `stored=False`, in the field's `azure_ai_search` provider
annotations to disable vector retrieval. `stored=False` cannot be combined with
`retrievable=True`. Vector fields cannot be filterable, sortable, facetable, or
analyzer-backed.

Portable filters execute in Azure Search. Presence/null filters, `ne`, null-valued
comparisons, empty `contains_all`, date comparisons, and literal
`contains_text`/`starts_with`/`ends_with` are rejected where their semantics cannot
be preserved. Use the explicitly tokenized `azure_ai_search.match` filter operator
for full-text matching. Returned scores are Azure `@search.score`, not raw cosine
similarity; hybrid scores use reciprocal rank fusion.
`not_in` excludes null and missing values, matching the portable in-memory behavior.

## Stable and preview features

The installed Azure Search SDK selects its API version; the package does not force
a preview API. Vector thresholds, hybrid text-recall controls, strict postfiltering,
and query-time document permissions require a supporting preview SDK/API and
`allow_preview=True` on the store or collection.

`score_threshold` applies only to a single pure-vector query. The separate
`vector_threshold` operation option filters vector candidates before hybrid fusion,
not final hybrid scores. Unsupported thresholds raise rather than silently falling back.
For permission-filtered reads, pass the caller's `query_source_credential`.

Context-provider answer synthesis, low/medium reasoning effort, and query-time
identity also require a supporting preview SDK. Stable Knowledge Base retrieval
uses extractive output with minimal reasoning.

## Documentation

- [Agent Framework documentation](https://learn.microsoft.com/agent-framework/)
- [Azure AI Search documentation](https://learn.microsoft.com/azure/search/)
- [Create a vector index](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index)
- [Vector and hybrid queries](https://learn.microsoft.com/azure/search/vector-search-how-to-query)
- [Knowledge Base retrieval](https://learn.microsoft.com/azure/search/agentic-retrieval-overview)
