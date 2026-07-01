# Agent With Content Understanding

These samples demonstrate the [Azure Content Understanding context provider](..) for `Microsoft.Agents.AI`. Each sample wires the provider into a Foundry- or Azure-OpenAI-backed agent so the agent can answer questions about uploaded documents, audio, and video using Azure Content Understanding for extraction.

These samples live under the package directory and mirror the layout of the [`agent-framework-azure-contentunderstanding` Python package samples](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-contentunderstanding/samples):

- **[`01-get-started/`](01-get-started/)** — script-style flows (easy → advanced).
- **[`02-devui/`](02-devui/)** — the provider hosted behind the [DevUI](../../Microsoft.Agents.AI.DevUI) web interface.

## Prerequisites

| Environment variable | Used by | Description |
| --- | --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | 01-get-started, DevUI multimodal & Foundry backend | Azure AI Foundry project endpoint URL. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | 01-get-started, DevUI multimodal & Foundry backend | Foundry model deployment name (defaults to `gpt-4.1`). |
| `AZURE_OPENAI_ENDPOINT` | DevUI Azure OpenAI backend | Azure OpenAI endpoint URL. |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | DevUI Azure OpenAI backend | Azure OpenAI chat-model deployment name (defaults to `gpt-4.1`). |
| `AZURE_CONTENTUNDERSTANDING_ENDPOINT` | All samples | Azure Content Understanding endpoint URL. |

All samples authenticate with `DefaultAzureCredential` (e.g. `az login` for local dev).

The script samples copy `shared/SampleAssets/invoice.pdf` to the project output directory at build time. The multi-modal chat script (`03_MultimodalChat`) also loads audio / video over HTTPS from the public [Azure Content Understanding sample assets repo](https://github.com/Azure-Samples/azure-ai-content-understanding-assets).

## Running a sample

```sh
cd dotnet/src/Microsoft.Agents.AI.AzureAI.ContentUnderstanding/samples/01-get-started/01_DocumentQA
dotnet run
```

The DevUI samples launch an ASP.NET Core server; once running, open the URL printed in the console (typically `https://localhost:5052x/devui`).

### 01-get-started — script samples

| # | Sample | Description |
| --- | --- | --- |
| 01 | [01_DocumentQA](01-get-started/01_DocumentQA/Program.cs) | Single-turn PDF Q&A. |
| 02 | [02_MultiTurnSession](01-get-started/02_MultiTurnSession/Program.cs) | 3-turn session with cached CU results. |
| 03 | [03_MultimodalChat](01-get-started/03_MultimodalChat/Program.cs) | PDF + audio URL + video URL analyzed in parallel; 5-turn session. |
| 04 | [04_InvoiceProcessing](01-get-started/04_InvoiceProcessing/Program.cs) | `prebuilt-invoice` analyzer with fields-only output. |
| 05 | [05_LargeDocFileSearch](01-get-started/05_LargeDocFileSearch/Program.cs) | `FileSearchConfig.FromFoundry` — CU markdown auto-uploaded to a vector store; agent queries via the `file_search` tool. |

### 02-devui — interactive web UI samples

| # | Sample | Description |
| --- | --- | --- |
| 01 | [01_MultimodalAgent](02-devui/01_MultimodalAgent/Program.cs) | Foundry-backed multimodal agent hosted in the DevUI web interface. |
| 02a | [02_FileSearchAgent/AzureOpenAIBackend](02-devui/02_FileSearchAgent/AzureOpenAIBackend/Program.cs) | Azure-OpenAI–backed file_search RAG hosted in DevUI; `FileSearchConfig.FromOpenAI`. |
| 02b | [02_FileSearchAgent/FoundryBackend](02-devui/02_FileSearchAgent/FoundryBackend/Program.cs) | Foundry-backed file_search RAG hosted in DevUI; `FileSearchConfig.FromFoundry`. |

## Notes

- **Per-attachment analyzer override** (`04_InvoiceProcessing`): the provider currently exposes only a global `ContentUnderstandingContextProviderOptions.AnalyzerId`. Mixing analyzers (for example `prebuilt-documentSearch` and `prebuilt-invoice`) within a single message is not yet supported. For sample 04, which uses a single attachment, the global setting is equivalent. Tracking the mixed-analyzer case as a follow-up.
- **`OPENAI001` suppression** (`05_LargeDocFileSearch`, `02_FileSearchAgent/AzureOpenAIBackend`, `02_FileSearchAgent/FoundryBackend`): the Foundry / OpenAI vector-store APIs in `OpenAI 2.10` are tagged `[Experimental("OPENAI001")]`. The vector-store samples add `<NoWarn>$(NoWarn);OPENAI001</NoWarn>` to their `.csproj` for that reason. The `Microsoft.Agents.AI.AzureAI.ContentUnderstanding` library itself never leaks the warning to consumers.
- **Cleanup boundaries**: the CU provider's `DisposeAsync` deletes any files it uploaded into a vector store (so `file_search` indexing artifacts don't accumulate). The vector store itself stays under caller ownership — the script sample `05_LargeDocFileSearch` and the Foundry DevUI sample `02_FileSearchAgent/FoundryBackend` delete it explicitly; the Azure-OpenAI DevUI sample `02_FileSearchAgent/AzureOpenAIBackend` relies on the vector store's 1-day idle expiration policy.
