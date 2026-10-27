# NVIDIA Package (agent-framework-nvidia)

Integration with NVIDIA NIM for embedding generation.

## Implementation Notes

- NVIDIA NIM exposes an OpenAI-compatible endpoint, so this package builds on
  `RawOpenAIEmbeddingClient` from `agent-framework-openai` rather than reimplementing the wire
  format. This mirrors `agent-framework-foundry-local`, which builds on the OpenAI Chat
  Completions client for the same reason.
- The default endpoint is `https://integrate.api.nvidia.com/v1`. `base_url` overrides it, which is
  the hook for a self-hosted NIM container.
- Model availability is per-account. An unentitled model returns `404 ... Not found for account`,
  and a retired model returns `410 Gone`, so neither is a request-shape error.
- `input_type` and `truncate` are outside the OpenAI embedding schema. The client sends them as
  `extra_body` by overriding `_prepare_extra_request_options`, and rejects invalid values before
  the request. Callers set `input_type` per call through vector-store `embeddings_options`, the
  same route the Gemini client uses for `task_type`. An `agent-framework-openai` without that hook
  would drop both fields silently, so importing the package raises `ImportError` instead.
- The hosted endpoint rejects requests with more than 256 inputs (`MAX_BATCH_SIZE`) or a body over
  2 MiB (`413`, budgeted by `MAX_BATCH_BYTES`), and a vector-store upsert embeds every record in one
  call, so `get_embeddings` splits larger inputs into consecutive requests, as the Gemini client does
  for Enterprise.

## Main Classes

- **`NvidiaEmbeddingClient`** - Embedding client for NVIDIA NIM models, with telemetry
- **`RawNvidiaEmbeddingClient`** - The same client without the telemetry layer
- **`NvidiaEmbeddingOptions`** - Options TypedDict for NVIDIA-specific embedding parameters
- **`NvidiaEmbeddingSettings`** - TypedDict settings for NVIDIA configuration

## Usage

```python
from agent_framework_nvidia import NvidiaEmbeddingClient

# Requires NVIDIA_API_KEY environment variable (or pass api_key= directly)
client = NvidiaEmbeddingClient(model="nvidia/nemotron-3-embed-1b")
result = await client.get_embeddings(["Hello, world!"])
print(result[0].vector)
```

## Import Path

The package is alpha, so there is no `agent_framework.nvidia` namespace in core yet.

```python
from agent_framework_nvidia import NvidiaEmbeddingClient
```
