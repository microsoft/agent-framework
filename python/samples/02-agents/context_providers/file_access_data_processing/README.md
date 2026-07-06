# File Access Data Processing

This sample demonstrates how to give an `Agent` access to a folder of data files
by attaching `FileAccessProvider` (backed by `FileSystemAgentFileStore`) as a
context provider.

The agent is given a `working/` folder containing `sales.csv` — ~50 rows of
sales transaction data — and is driven through a short scripted conversation
that exercises every tool the provider exposes:

| Step | Prompt | Tool(s) used |
|---|---|---|
| 1 | "What files do you have access to?" | `file_access_ls` |
| 2 | "Read sales.csv and summarize…" | `file_access_read` |
| 3 | "Calculate the total revenue per region…" | (uses previously read data) |
| 4 | "Save a markdown report named `region_totals.md`…" | `file_access_write` |
| 5 | "List the files again so I can confirm…" | `file_access_ls` |

After the run, the sample prints the final contents of `working/` so the
written file is easy to spot.

## Prerequisites

| Variable | Description |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Your Azure AI Foundry project endpoint. |
| `FOUNDRY_MODEL` | Chat model deployment name (e.g. `gpt-4o`). |

Run `az login` before executing the sample so `AzureCliCredential` can
authenticate.

## Running the sample

From `python/`:

```bash
uv run --package agent-framework-core python samples/02-agents/context_providers/file_access_data_processing/data_processing.py
```

Or directly:

```bash
python samples/02-agents/context_providers/file_access_data_processing/data_processing.py
```

## Sample data

`working/sales.csv` contains January–March 2025 sales transactions with these
columns:

| Column | Description |
|---|---|
| `date` | Transaction date (YYYY-MM-DD) |
| `product` | Product name |
| `category` | Product category (Electronics, Furniture, Stationery) |
| `quantity` | Units sold |
| `unit_price` | Price per unit |
| `region` | Sales region (North, South, West) |
| `salesperson` | Name of the salesperson |

The sample writes `region_totals.md` into the same folder. Delete it between
runs if you want a clean state.
