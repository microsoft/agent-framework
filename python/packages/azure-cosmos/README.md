# Microsoft Agent Framework integrations for Azure Cosmos DB

Use Azure Cosmos DB for NoSQL as an Agent Framework vector store, conversation history
provider, or workflow checkpoint store.

## Contents

- `CosmosCollection` and `CosmosStore` for vector CRUD and `VectorDistance` search
- `CosmosHistoryProvider` for persistent conversation history
- `CosmosCheckpointStorage` for durable workflow checkpoints

## Install

```bash
pip install agent-framework-azure-cosmos --pre
```

The package requires Python 3.10 or later, an Azure Cosmos DB for NoSQL account,
and `azure-cosmos` 4.7 or later. Vector collections also require the account's
[NoSQL vector search capability](https://learn.microsoft.com/azure/cosmos-db/vector-search)
to be enabled before use.

## Authentication and settings

Pass a caller-owned Azure credential or account key. If constructor values are omitted,
the package reads an explicitly selected `.env` file and then these environment variables:

| Variable | Purpose |
| --- | --- |
| `AZURE_COSMOS_ENDPOINT` | Azure Cosmos DB account endpoint |
| `AZURE_COSMOS_DATABASE_NAME` | Database name |
| `AZURE_COSMOS_CONTAINER_NAME` | Container name for direct collection/provider use |
| `AZURE_COSMOS_KEY` | Account key; omit when passing an Azure credential |

Explicit constructor values take precedence over a selected `.env` file, which takes
precedence over process environment variables. Injected asynchronous `CosmosClient`,
`DatabaseProxy`, and `ContainerProxy` objects bypass connection settings and remain
caller-owned.

## Vector store

Vector collections require:

- one application-provided string key with storage name `id`;
- a single Hash partition key path `/id`;
- top-level dense vector fields; and
- the container vector and indexing policies derived from the collection definition.

This makes `get()` and `delete()` unambiguous point operations because the item ID is also
its partition key. IDs must contain 1-1,023 UTF-8 bytes and cannot contain `/`, `\`,
`?`, or `#`; the connector never encodes them. Custom and hierarchical partition keys
are not supported.

```python
from dataclasses import dataclass
from typing import Annotated

from agent_framework import VectorStoreField, vectorstoremodel
from agent_framework.azure import CosmosStore
from azure.identity.aio import AzureCliCredential


@vectorstoremodel(collection_name="documents")
@dataclass
class Document:
    id: Annotated[str, VectorStoreField("key", storage_name="id")]
    text: Annotated[str, VectorStoreField("data", is_indexed=True)]
    embedding: Annotated[
        list[float],
        VectorStoreField(
            "vector",
            dimensions=1536,
            distance_function="cosine_similarity",
        ),
    ]


async with CosmosStore(
    endpoint="https://<account>.documents.azure.com:443/",
    database_name="agent-framework",
    credential=AzureCliCredential(),
) as store:
    collection = store.get_collection(Document)
    await collection.ensure_collection_exists()
    await collection.upsert(
        [Document(id="doc-1", text="Vector search", embedding=[1.0] + [0.0] * 1535)],
        generate_vectors=False,
    )
    results = await collection.search(vector=[1.0] + [0.0] * 1535, top=3)
    async for result in results:
        print(result["record"].text, result["score"])
```

The default vector index is `quantizedFlat`, which supports up to 4,096 dimensions and
uses quantized rather than exact-float recall. Below 1,000 indexed vectors, Azure Cosmos DB
falls back to a full scan. For exact search, explicitly set `index_kind="flat"` on vector
fields with at most 505 dimensions.

Supported vector element types are `float32`, `int8`, and `uint8`. Supported metrics are
cosine similarity, dot product, and Euclidean distance. Scores are returned unchanged:
higher is better for cosine and dot product, while lower is better for Euclidean distance.
Score thresholds are supported for cosine and dot product; Euclidean search is supported
without `score_threshold` because direct `VectorDistance` predicates do not reliably apply
Euclidean cutoffs.
After results are consumed, `SearchResults.metadata` contains the bounded request charge,
last activity ID, and whether the last response page advertised more results; continuation
tokens are not exposed.

Vector index tuning is available through the field's `azure_cosmos` provider annotations:

```python
VectorStoreField(
    "vector",
    dimensions=1536,
    index_kind="disk_ann",
    provider_annotations={
        "azure_cosmos": {
            "quantizer_type": "spherical",
            "quantization_byte_size": 256,
            "indexing_search_list_size": 200,
        }
    },
)
```

Search operation options support `search_list_size_multiplier`,
`quantized_vector_list_multiplier`, `filter_priority`, and `brute_force`.
Values and vectors are always sent as query parameters.

Writes and deletes span `/id` partitions and are not multi-item transactions. The connector
validates the complete input batch before the first request, but a service failure can still
leave an operation partially applied. Retry with stable application keys for idempotent
upserts and deletes.

See the [Azure Cosmos DB vector search documentation](https://learn.microsoft.com/azure/cosmos-db/vector-search)
and the [Agent Framework vector-store samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/vector_stores).

## Conversation history

```python
from agent_framework.azure import CosmosHistoryProvider
from azure.identity.aio import AzureCliCredential

provider = CosmosHistoryProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=AzureCliCredential(),
    database_name="agent-framework",
    container_name="chat-history",
)
```

`CosmosHistoryProvider` stores each conversation under its `session_id` partition key.
See the [conversation sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/conversations/cosmos_history_provider.py).

## Workflow checkpoints

```python
from agent_framework_azure_cosmos import CosmosCheckpointStorage
from azure.identity.aio import AzureCliCredential

storage = CosmosCheckpointStorage(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=AzureCliCredential(),
    database_name="agent-framework",
    container_name="workflow-checkpoints",
)
```

`CosmosCheckpointStorage` uses `/workflow_name` as its partition key and creates its
database and container on first use. See the
[checkpoint sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/checkpoint/cosmos_workflow_checkpointing.py).
