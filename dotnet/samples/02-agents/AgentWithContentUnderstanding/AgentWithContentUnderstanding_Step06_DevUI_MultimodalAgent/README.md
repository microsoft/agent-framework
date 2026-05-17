# Step 06 — DevUI Multi-Modal Agent

Hosts a Foundry-backed agent with the [Azure Content Understanding context provider](../../../../src/Microsoft.Agents.AI.AzureAI.ContentUnderstanding) behind the DevUI web interface. Upload a PDF, scanned image, audio, or video in the browser and ask questions about its contents.

Mirrors the Python sample at [`samples/02-devui/01-multimodal_agent/agent.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/02-devui/01-multimodal_agent/agent.py).

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

Then open <https://localhost:50520/devui> in a browser.
