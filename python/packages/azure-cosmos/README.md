# Get Started with Microsoft Agent Framework Azure Cosmos DB

Please install this package via pip:

```bash
pip install agent-framework-azure-cosmos --pre
```

## Azure Cosmos DB History Provider

The Azure Cosmos DB integration provides `CosmosHistoryProvider` for persistent conversation history storage.

### Basic Usage Example

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_cosmos import CosmosHistoryProvider

provider = CosmosHistoryProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=DefaultAzureCredential(),
    database_name="agent-framework",
    container_name="chat-history",
)
```

Credentials follow the same pattern used by other Azure connectors in the repository:

- Pass a credential object (for example `DefaultAzureCredential`)
- Or pass a key string directly
- Or set `AZURE_COSMOS_KEY` in the environment

Container naming behavior:

- Container name is configured on the provider (`container_name` or `AZURE_COSMOS_CONTAINER_NAME`)
- `session_id` is used as the Cosmos partition key for reads/writes

See `samples/cosmos_history_provider.py` for a runnable package-local example.

## Azure Cosmos DB Context Provider

The Azure Cosmos DB integration also provides `AzureCosmosContextProvider` for context injection before model invocation. It also writes input and response messages back into the same Cosmos container after each run so the knowledge container can accumulate additional context over time.

### Basic Usage Example

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework_azure_cosmos import AzureCosmosContextProvider, CosmosContextSearchMode

provider = AzureCosmosContextProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=DefaultAzureCredential(),
    database_name="agent-framework",
    container_name="knowledge",
    default_search_mode=CosmosContextSearchMode.FULL_TEXT,
    content_field_names=("content", "text"),
)
```

Supported retrieval configuration includes:

- `default_search_mode`: `CosmosContextSearchMode.FULL_TEXT`, `.VECTOR`, or `.HYBRID`
- `search_mode` override in `before_run(...)` for advanced callers
- `weights` in `before_run(...)` for hybrid RRF runs
- `top_k` override in `before_run(...)` for per-run final result count
- `scan_limit` override in `before_run(...)` for per-run candidate scan size
- `partition_key` override in `before_run(...)` for per-run Cosmos retrieval scope

When the provider is attached to an agent through `context_providers=[...]`, the framework uses the provider's constructor defaults for normal agent runs. Advanced callers can still invoke `before_run(...)` directly and override `default_search_mode`, `top_k`, `scan_limit`, and `partition_key` for a single run. RRF weights are only used for hybrid runs:

```python
await provider.before_run(
    agent=agent,
    session=session,
    context=context,
    state=session.state.setdefault(provider.source_id, {}),
    search_mode=CosmosContextSearchMode.HYBRID,
    weights=[2.0, 1.0],
    top_k=3,
    scan_limit=10,
    partition_key="tenant-a",
)
```

`AzureCosmosContextProvider` contributes retrieval context in `before_run(...)` and persists input/response messages in `after_run(...)`.

The provider builds retrieval input by joining the filtered `user` and `assistant` messages from the current run into a single query string. That joined query text is then used for full-text tokenization, vector embedding generation, or hybrid retrieval depending on the resolved search mode.

The provider writes the request/response messages back into the same knowledge container configured by `container_name`. Those writeback documents are tagged with an internal `document_type` marker and excluded from retrieval queries.

Constructor values for `top_k`, `scan_limit`, and `partition_key` remain the provider defaults. Passing those same names to `before_run(...)` only affects that invocation and does not mutate the provider instance for future runs.

The provider assumes the Cosmos account, database, container, partitioning strategy, and any required Cosmos full-text/vector/hybrid indexing policies already exist and are correctly configured by the application owner. It does not create or manage Cosmos resources, schema, or search policies for you.

See `samples/cosmos_context_provider.py` for a runnable package-local example.

