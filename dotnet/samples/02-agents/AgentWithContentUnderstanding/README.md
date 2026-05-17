# Agent With Content Understanding

These samples demonstrate the [Azure Content Understanding context provider](../../../src/Microsoft.Agents.AI.AzureAI.ContentUnderstanding) for `Microsoft.Agents.AI`. Each sample wires the provider into a Foundry- or Azure-OpenAI-backed agent so the agent can answer questions about uploaded documents, audio, and video using Azure Content Understanding for extraction.

Samples 01–05 are script-style flows ported 1:1 from the Python package's [`samples/01-get-started/`](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-contentunderstanding/samples/01-get-started). Samples 06–08 host the provider behind the [DevUI](../../../src/Microsoft.Agents.AI.DevUI) web interface and mirror the Python [`samples/02-devui/`](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-contentunderstanding/samples/02-devui) set.

## Prerequisites

| Environment variable | Used by | Description |
| --- | --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | Samples 01–06, 08 | Azure AI Foundry project endpoint URL. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Samples 01–06, 08 | Foundry model deployment name (defaults to `gpt-4.1`). |
| `AZURE_OPENAI_ENDPOINT` | Sample 07 | Azure OpenAI endpoint URL. |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Sample 07 | Azure OpenAI chat-model deployment name (defaults to `gpt-4.1`). |
| `AZURE_CONTENTUNDERSTANDING_ENDPOINT` | All samples | Azure Content Understanding endpoint URL. |

All samples authenticate with `DefaultAzureCredential` (e.g. `az login` for local dev).

The script samples copy `SampleAssets/invoice.pdf` to the project output directory at build time. Sample 03 also loads audio / video over HTTPS from the public [Azure Content Understanding sample assets repo](https://github.com/Azure-Samples/azure-ai-content-understanding-assets).

## Running a sample

```sh
cd dotnet/samples/02-agents/AgentWithContentUnderstanding/AgentWithContentUnderstanding_Step01_DocumentQA
dotnet run
```

DevUI samples (06–08) launch an ASP.NET Core server; once running, open the URL printed in the console (typically `https://localhost:5052x/devui`).

## Samples

| # | Sample | Description | Python parity |
| --- | --- | --- | --- |
| 01 | [AgentWithContentUnderstanding_Step01_DocumentQA](AgentWithContentUnderstanding_Step01_DocumentQA/Program.cs) | Single-turn PDF Q&A. | [01_document_qa.py](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/01-get-started/01_document_qa.py) |
| 02 | [AgentWithContentUnderstanding_Step02_MultiTurnSession](AgentWithContentUnderstanding_Step02_MultiTurnSession/Program.cs) | 3-turn session with cached CU results. | [02_multi_turn_session.py](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/01-get-started/02_multi_turn_session.py) |
| 03 | [AgentWithContentUnderstanding_Step03_MultimodalChat](AgentWithContentUnderstanding_Step03_MultimodalChat/Program.cs) | PDF + audio URL + video URL analyzed in parallel; 5-turn session. | [03_multimodal_chat.py](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/01-get-started/03_multimodal_chat.py) |
| 04 | [AgentWithContentUnderstanding_Step04_InvoiceProcessing](AgentWithContentUnderstanding_Step04_InvoiceProcessing/Program.cs) | `prebuilt-invoice` analyzer with fields-only output. | [04_invoice_processing.py](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/01-get-started/04_invoice_processing.py) |
| 05 | [AgentWithContentUnderstanding_Step05_LargeDocFileSearch](AgentWithContentUnderstanding_Step05_LargeDocFileSearch/Program.cs) | `FileSearchConfig.FromFoundry` — CU markdown auto-uploaded to a vector store; agent queries via the `file_search` tool. | [05_large_doc_file_search.py](https://github.com/microsoft/agent-framework/blob/main/python/packages/azure-contentunderstanding/samples/01-get-started/05_large_doc_file_search.py) |
| 06 | [AgentWithContentUnderstanding_Step06_DevUI_MultimodalAgent](AgentWithContentUnderstanding_Step06_DevUI_MultimodalAgent/Program.cs) | Foundry-backed multimodal agent hosted in the DevUI web interface. | [02-devui/01-multimodal_agent](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-contentunderstanding/samples/02-devui/01-multimodal_agent) |
| 07 | [AgentWithContentUnderstanding_Step07_DevUI_FileSearchAzureOpenAI](AgentWithContentUnderstanding_Step07_DevUI_FileSearchAzureOpenAI/Program.cs) | Azure-OpenAI–backed file_search RAG hosted in DevUI; `FileSearchConfig.FromOpenAI`. | [02-devui/02-file_search_agent/azure_openai_backend](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-contentunderstanding/samples/02-devui/02-file_search_agent/azure_openai_backend) |
| 08 | [AgentWithContentUnderstanding_Step08_DevUI_FileSearchFoundry](AgentWithContentUnderstanding_Step08_DevUI_FileSearchFoundry/Program.cs) | Foundry-backed file_search RAG hosted in DevUI; `FileSearchConfig.FromFoundry`. | [02-devui/02-file_search_agent/foundry_backend](https://github.com/microsoft/agent-framework/tree/main/python/packages/azure-contentunderstanding/samples/02-devui/02-file_search_agent/foundry_backend) |

## Parity notes

- **Per-attachment analyzer override** (sample 04): the Python provider supports `additional_properties={"analyzer_id": "..."}` per attachment so that a single message can mix `prebuilt-documentSearch` and `prebuilt-invoice`. The .NET provider currently exposes only a global `ContentUnderstandingContextProviderOptions.AnalyzerId`. For sample 04, which uses a single attachment, that is functionally equivalent. Tracking the mixed-analyzer case as a follow-up.
- **`OPENAI001` suppression** (samples 05, 07, 08): the Foundry / OpenAI vector-store APIs in `OpenAI 2.10` are tagged `[Experimental("OPENAI001")]`. The vector-store samples add `<NoWarn>$(NoWarn);OPENAI001</NoWarn>` to their `.csproj` for that reason. The `Microsoft.Agents.AI.AzureAI.ContentUnderstanding` library itself never leaks the warning to consumers.
- **Cleanup boundaries**: the CU provider's `DisposeAsync` deletes any files it uploaded into a vector store (so `file_search` indexing artifacts don't accumulate). The vector store itself stays under caller ownership — the script sample 05 and the Foundry DevUI sample 08 delete it explicitly; the Azure-OpenAI DevUI sample 07 relies on the vector store's 1-day idle expiration policy.
