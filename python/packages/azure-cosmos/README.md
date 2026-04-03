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

The Azure Cosmos DB integration also provides `AzureCosmosContextProvider` for context injection before model invocation, with default writeback into the same knowledge container after each run.

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
- `query_builder_mode`: `"latest_user"`, `"recent_messages"`, or `"latest_user_with_context"`
- `writeback_enabled`: defaults to `True`; set `False` to skip `after_run(...)` persistence

The provider can be reused across runs with different retrieval behavior by overriding the mode on the hook call. RRF weights are only used for hybrid runs:

```python
await provider.before_run(
    agent=agent,
    session=session,
    context=context,
    state=session.state.setdefault(provider.source_id, {}),
    search_mode=CosmosContextSearchMode.HYBRID,
    weights=[2.0, 1.0],
)
```

`AzureCosmosContextProvider` contributes retrieval context in `before_run(...)` and, by default, persists input/response messages in `after_run(...)`.

If you want the provider to persist input and response messages after each run, enable the explicit writeback contract and target an existing writeback container:

```python
provider = AzureCosmosContextProvider(
    endpoint="https://<account>.documents.azure.com:443/",
    credential=DefaultAzureCredential(),
    database_name="agent-framework",
    container_name="knowledge",
    writeback_enabled=False,
)
```

When writeback is enabled, the provider writes the request/response messages back into the same knowledge container configured by `container_name`. Those writeback documents are tagged with an internal `document_type` marker and excluded from retrieval queries.

See `samples/cosmos_context_provider.py` for a runnable package-local example.

