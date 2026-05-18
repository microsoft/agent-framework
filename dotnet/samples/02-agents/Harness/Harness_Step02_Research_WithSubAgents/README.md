# Harness Step 02 — SubAgents (Stock Price Research)

This sample demonstrates how to use the **SubAgentsProvider** to delegate work from a parent agent to sub-agents. Both agents use `HarnessAgent` for pre-configured function invocation, per-service-call persistence, and context-window compaction.

## What It Does

A parent agent receives a list of stock tickers and uses a web-search sub-agent to find the closing price for each ticker on December 31, 2025. The sub-tasks run concurrently, and results are presented in a summary table.

### Architecture

```
┌─────────────────────────────────┐
│     StockPriceResearcher        │
│         (Parent Agent)          │
│                                 │
│  SubAgentsProvider              │
│    ├─ SubAgents_StartTask       │
│    ├─ SubAgents_WaitFor...      │
│    ├─ SubAgents_GetTaskResults  │
│    └─ ...                       │
└────────────┬────────────────────┘
             │  delegates to
             ▼
┌─────────────────────────────────┐
│       WebSearchAgent            │
│        (Sub-Agent)              │
│                                 │
│  Tools:                         │
│    └─ web_search (Foundry)      │
└─────────────────────────────────┘
```

## Prerequisites

- An Azure AI Foundry endpoint with an OpenAI model deployment
- Set the following environment variables:
  - `AZURE_FOUNDRY_OPENAI_ENDPOINT` — Your Foundry OpenAI endpoint URL
  - `AZURE_AI_MODEL_DEPLOYMENT_NAME` — Model deployment name (defaults to `gpt-5.4`)

## Running the Sample

```bash
cd dotnet/samples/02-agents/Harness/Harness_Step02_Research_WithSubAgents
dotnet run
```

When prompted, enter a list of stock tickers such as:

```
BAC, MSFT, BA
```

The parent agent will delegate each ticker lookup to the web search sub-agent concurrently and present the results in a table.
