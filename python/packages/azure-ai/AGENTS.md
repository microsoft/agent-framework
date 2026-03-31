# Azure AI Package (agent-framework-azure-ai)

Integration with Azure AI inference embeddings plus shared Azure authentication helpers.

## Main Classes

- **`AzureAIInferenceEmbeddingClient`** - Full-featured Azure AI inference embeddings client
- **`RawAzureAIInferenceEmbeddingClient`** - Raw embeddings client without middleware layers
- **`AzureAIInferenceEmbeddingOptions`** / **`AzureAIInferenceEmbeddingSettings`** - Embedding options and settings
- **`AzureAISettings`** - Shared Azure AI project settings TypedDict
- **`AzureCredentialTypes`** / **`AzureTokenProvider`** - Shared Azure authentication helpers

## Usage

```python
from agent_framework_azure_ai import AzureAIInferenceEmbeddingClient

client = AzureAIInferenceEmbeddingClient(
    endpoint="https://<resource>.inference.ai.azure.com",
    api_key="...",
    model_id="text-embedding-3-large",
)
result = await client.get_embeddings(["Hello"])
```

## Import Path

```python
from agent_framework_azure_ai import AzureAIInferenceEmbeddingClient
```
