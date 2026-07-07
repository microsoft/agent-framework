# Harness Step 02 — BackgroundAgents (Stock Price Research)

This sample demonstrates how to use the **BackgroundAgentsProvider** to delegate work from a parent agent to background agents. Both agents use `HarnessAgent` for pre-configured function invocation, per-service-call persistence, and context-window compaction.

## What It Does

A parent agent receives a list of stock tickers and uses a web-search background agent to find the closing price for each ticker on December 31, 2025. The background tasks run concurrently, and results are presented in a summary table.

### Architecture

```
┌──────────────────────────────────────────────────┐
│     StockPriceResearcher                         │
│         (Parent Agent)                           │
│                                                  │
│  BackgroundAgentsProvider                        │
│    ├─ background_agents_start_task               │
│    ├─ background_agents_wait_for_first_completion│
│    ├─ background_agents_get_task_results         │
│    └─ ...                                        │
└─────────────┬────────────────────────────────────┘
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
  - `FOUNDRY_MODEL` — Model deployment name (defaults to `gpt-5.4`)

## Running the Sample

```bash
cd dotnet/samples/02-agents/Harness/Harness_Step02_Research_WithBackgroundAgents
dotnet run
```

When prompted, enter a list of stock tickers such as:

```
BAC, MSFT, BA
```

The parent agent will delegate each ticker lookup to the web search background agent concurrently and present the results in a table.
