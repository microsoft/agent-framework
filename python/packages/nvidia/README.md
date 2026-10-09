# Get Started with Microsoft Agent Framework NVIDIA NIM

An alpha NVIDIA NIM embedding integration for Microsoft Agent Framework. Please install this package:

```bash
pip install agent-framework-nvidia --pre
```

and see the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.

See the [NVIDIA samples](samples/README.md) for a runnable example.

## Embedding Client

The `NvidiaEmbeddingClient` provides embedding generation using models hosted on
[NVIDIA NIM](https://build.nvidia.com/). NIM exposes an OpenAI-compatible surface, so this client
builds on the OpenAI embedding client rather than reimplementing the wire format.

### Quick Start

```python
from agent_framework_nvidia import NvidiaEmbeddingClient

# Using environment variables (NVIDIA_API_KEY, NVIDIA_EMBEDDING_MODEL)
# Parameters can also be passed directly:
# NvidiaEmbeddingClient(model="nvidia/nemotron-3-embed-1b", api_key="your-api-key")
client = NvidiaEmbeddingClient()

result = await client.get_embeddings(["Hello, world!", "How are you?"])
for embedding in result:
    print(f"Dimensions: {embedding.dimensions}")
    print(f"Vector: {embedding.vector[:5]}...")

# Close the HTTP client the embedding client created. A client passed as async_client is left open.
await client.close()
```

### Configuration

| Environment Variable | Description |
|---|---|
| `NVIDIA_API_KEY` | Your NVIDIA API key, from [build.nvidia.com](https://build.nvidia.com/) |
| `NVIDIA_EMBEDDING_MODEL` | Embedding model name (e.g., `nvidia/nemotron-3-embed-1b`) |
| `NVIDIA_BASE_URL` | Optional endpoint override, for a self-hosted NIM container |

The service throttles bursts with `429`, which the OpenAI SDK retries twice by default. For heavy
parallel ingestion, pass a pre-configured `async_client`, for example
`AsyncOpenAI(..., max_retries=5)`, to change retries or timeouts.

### Options

`NvidiaEmbeddingOptions` adds two NVIDIA fields to the OpenAI embedding options:

| Option | Values | Purpose |
|---|---|---|
| `input_type` | `"passage"`, `"query"` | Asymmetric retrieval models embed documents and search text differently |
| `truncate` | `"NONE"`, `"START"`, `"END"` | Reject over-long input, or drop tokens from that end |

For retrieval, embed stored documents as passages and search text as queries. Vector collections
forward `embeddings_options` to each request:

```python
await collection.upsert(notes, embeddings_options={"input_type": "passage", "truncate": "END"})
results = await collection.search("How do I call a model?", embeddings_options={"input_type": "query"})
```

`create_vector_search_tool(..., embeddings_options={"input_type": "query"})` does the same for the
tool an agent calls. `nvidia/nemotron-3-embed-1b` accepts only 2048 dimensions, so declare that on
the vector field.

The hosted endpoint accepts at most 256 inputs and a 2 MiB body per request, so the client sends
larger calls, such as an upsert of many records, as consecutive requests within both limits and
returns the vectors in order.

Without `truncate`, the service shortens input over the model's token limit itself, but it rejects any
input over 65,536 characters, and one such document fails the whole call, so nothing in that upsert
is written. Set `truncate="END"` (or `"START"`) when ingesting documents of unknown length.
`truncate="NONE"` rejects input over the token limit instead.

### Choosing a model

Model availability is per-account: the endpoint lists more embedding models than a given API key
is entitled to call, and an unentitled model returns `404 ... Not found for account` rather than a
permission error. Retired models return `410 Gone`. If a model name from the documentation does
not work, list the models available to your key rather than assuming the name is wrong. An invalid key
returns `403 Forbidden` with `Authorization failed`, not `401`.
