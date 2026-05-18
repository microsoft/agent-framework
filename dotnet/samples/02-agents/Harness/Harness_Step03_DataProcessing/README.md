# What this sample demonstrates

This sample demonstrates how to use a `HarnessAgent` with the `FileAccessProvider` to give an agent access to a folder of data files for reading, analyzing, and writing results. The `HarnessAgent` pre-configures function invocation, per-service-call chat history persistence, and in-loop compaction — so the sample only needs to supply the chat client, token limits, and application-specific options.

Key features showcased:

- **HarnessAgent** — a pre-configured agent that wraps a `ChatClientAgent` with function invocation, per-service-call persistence, and context-window compaction
- **FileAccessProvider** — gives the agent tools to read, write, list, search, and delete files in a shared data folder
- **CSV data processing** — the agent reads sales transaction data and performs analysis on demand
- **Output file creation** — the agent can write summaries, filtered data, or reports back to the data folder
- **Streaming output** — responses are streamed token-by-token for a natural experience
- **No planning mode** — this is a simple conversational sample focused on data interaction

## Prerequisites

Before running this sample, ensure you have:

1. An Azure AI Foundry project with a deployed model (e.g., `gpt-5.4`)
2. Azure CLI installed and authenticated (`az login`)

## Environment Variables

Set the following environment variables:

```bash
# Required: Your Azure AI Foundry OpenAI endpoint
export AZURE_FOUNDRY_OPENAI_ENDPOINT="https://your-project.services.ai.azure.com/openai/v1/"

# Optional: Model deployment name (defaults to gpt-5.4)
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4"
```

## Running the Sample

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/Harness_Step03_DataProcessing
```

## What to Expect

The sample starts an interactive conversation with a data analyst agent. The `data/` folder contains a `sales.csv` file with ~50 rows of sales transaction data (date, product, category, quantity, unit price, region, salesperson).

You can ask the agent to:

1. **List available files** — "What files do you have?"
2. **Analyze the data** — "What are the total sales by region?" or "Which salesperson has the highest revenue?"
3. **Create output files** — "Create a summary report as a markdown file" or "Write a CSV with monthly totals"
4. **Search for patterns** — "Find all transactions over $1000"
5. **Type `exit`** — to end the session

E.g. try the following prompt `Please process the sales.csv file by first filtering it to only North region sales, and then calculating the sum of sales by person. I'd like to write the results of the processing to north_region_totals.csv`.

## Sample Data

The included `data/sales.csv` contains sales transactions from January to March 2025 with the following columns:

| Column | Description |
| --- | --- |
| `date` | Transaction date (YYYY-MM-DD) |
| `product` | Product name |
| `category` | Product category (Electronics, Furniture, Stationery) |
| `quantity` | Units sold |
| `unit_price` | Price per unit |
| `region` | Sales region (North, South, West) |
| `salesperson` | Name of the salesperson |
