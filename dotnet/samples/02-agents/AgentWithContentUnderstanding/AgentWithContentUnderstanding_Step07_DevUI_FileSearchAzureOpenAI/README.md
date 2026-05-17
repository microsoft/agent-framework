# Step 07 — DevUI File-Search Agent (Azure OpenAI backend)

Hosts an Azure-OpenAI–backed agent with the Content Understanding context provider behind the DevUI web interface. Wires `FileSearchConfig.FromOpenAI` so each uploaded file is CU-extracted and indexed in an Azure OpenAI vector store, then queried via the `file_search` tool — ideal for large documents or audio/video that exceed the context window.

Mirrors the Python sample at [`samples/02-devui/02-file_search_agent/azure_openai_backend/agent.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/02-devui/02-file_search_agent/azure_openai_backend/agent.py).

## Prerequisites

| Environment variable | Description |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL. |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Chat-model deployment name (defaults to `gpt-4.1`). |
| `AZURE_CONTENTUNDERSTANDING_ENDPOINT` | Azure Content Understanding endpoint URL. |

Authenticate with `az login` (the sample uses `DefaultAzureCredential`).

## Run

```sh
dotnet run
```

Then open <https://localhost:50522/devui> in a browser.

## Cleanup

The vector store is created with a 1-day idle expiration policy, so abandoned DevUI sessions are auto-cleaned by Azure OpenAI. The CU provider's `DisposeAsync` (triggered at app shutdown) deletes the per-file uploads it owned; the vector store itself is left to the auto-expiration policy.
