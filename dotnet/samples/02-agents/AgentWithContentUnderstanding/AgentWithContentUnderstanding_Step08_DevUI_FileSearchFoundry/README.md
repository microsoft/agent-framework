# Step 08 — DevUI File-Search Agent (Foundry backend)

Hosts a Foundry-backed agent with the Content Understanding context provider behind the DevUI web interface. Wires `FileSearchConfig.FromFoundry` so each uploaded file is CU-extracted and indexed in a Foundry vector store, then queried via the `file_search` tool — the same RAG flow as [Step 05](../AgentWithContentUnderstanding_Step05_LargeDocFileSearch/), but driven from an interactive DevUI session instead of a script.

Mirrors the Python sample at [`samples/02-devui/02-file_search_agent/foundry_backend/agent.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/02-devui/02-file_search_agent/foundry_backend/agent.py).

## Prerequisites

| Environment variable | Description |
| --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint URL. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Foundry model deployment name (defaults to `gpt-4.1`). |
| `AZURE_CONTENTUNDERSTANDING_ENDPOINT` | Azure Content Understanding endpoint URL. |

Authenticate with `az login` (the sample uses `DefaultAzureCredential`).

## Run

```sh
dotnet run
```

Then open <https://localhost:50524/devui> in a browser.

## Cleanup

A Foundry vector store is created at startup and deleted on `Ctrl+C` (via `IHostApplicationLifetime.ApplicationStopping`). The CU provider's `DisposeAsync` (triggered at app shutdown) deletes the per-file uploads it owned.
