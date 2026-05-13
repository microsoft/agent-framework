# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with **Retrieval Augmented Generation (RAG)** capabilities backed by **Azure AI Search**, hosted using the **Responses protocol**. The agent grounds its answers in product documentation by running a search against an Azure AI Search index before each model invocation, then citing the source in its response.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment.

### RAG via Azure AI Search

`AzureAISearchContextProvider` runs a search against the configured Azure AI Search index **before each model invocation** and injects the top results into the model context. The agent then composes a grounded answer and cites the source document.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- An Azure AI Foundry project with a deployed model (e.g., `gpt-4.1-mini`)
- An Azure AI Search service ([create one](https://learn.microsoft.com/azure/search/search-create-service-portal))
- **A pre-provisioned search index** with the schema and content described below
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs:

- **Azure AI User** on the Foundry project scope
- **Search Index Data Reader** on the Azure AI Search service (the sample only reads from the index)

## Provisioning the search index (one time)

The sample assumes the search index already exists and contains documents the agent can retrieve from. Provision it once via the Azure Portal, the [REST API](https://learn.microsoft.com/azure/search/search-how-to-create-search-index), or one of the snippets below.

### Option A: Python script (recommended)

[`provision_index.py`](provision_index.py) creates the index (if it doesn't already exist) and seeds it with the three Contoso Outdoors documents using `DefaultAzureCredential`. Your identity needs the following roles on the **Azure AI Search service** scope:

- **Search Service Contributor** — to create the index
- **Search Index Data Contributor** — to upload documents

> Note: `Search Service Contributor` only covers control-plane operations (create/list/delete indexes). It does **not** grant document write access — `Search Index Data Contributor` is required for that even if you already have `Search Service Contributor`.

Grant the roles to your signed-in user (replace `<search-name>` and `<rg>`):

```powershell
$searchId = az search service show -n <search-name> -g <rg> --query id -o tsv
$me = az ad signed-in-user show --query id -o tsv

az role assignment create --assignee $me --role "Search Service Contributor"   --scope $searchId
az role assignment create --assignee $me --role "Search Index Data Contributor" --scope $searchId
```

Role propagation typically takes 1–5 minutes. Also confirm the search service has RBAC enabled (Portal → search service → **Keys** → **API Access control** → "Both" or "Role-based access control"); if it is set to "API Key" only, every AAD request returns `403 Forbidden`.

Then, from this directory:

```bash
export AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
export AZURE_SEARCH_INDEX_NAME="contoso-outdoors"
python provision_index.py
```

Or in PowerShell:

```powershell
$env:AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
$env:AZURE_SEARCH_INDEX_NAME="contoso-outdoors"
python provision_index.py
```

The script is safe to re-run: if the index already exists, it leaves the schema untouched and merges-or-uploads the documents. To change the schema, delete the index first (Azure AI Search does not allow modifying existing field attributes) and re-run the script.

### Index schema

| Field | Type | Attributes |
|---|---|---|
| `id` | `Edm.String` | key, filterable |
| `content` | `Edm.String` | searchable (full-text) |
| `sourceName` | `Edm.String` | retrievable, filterable |
| `sourceLink` | `Edm.String` | retrievable |

### Option B: Azure CLI + REST

```bash
SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
INDEX_NAME="contoso-outdoors"
TOKEN=$(az account get-access-token --resource https://search.azure.com --query accessToken -o tsv)

# 1. Create the index.
curl -X PUT "$SEARCH_ENDPOINT/indexes/$INDEX_NAME?api-version=2024-07-01" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "contoso-outdoors",
    "fields": [
      { "name": "id",         "type": "Edm.String", "key": true,  "filterable": true,  "searchable": false, "retrievable": true },
      { "name": "content",    "type": "Edm.String", "key": false, "filterable": false, "searchable": true,  "retrievable": true, "analyzer": "standard.lucene" },
      { "name": "sourceName", "type": "Edm.String", "key": false, "filterable": true,  "searchable": false, "retrievable": true },
      { "name": "sourceLink", "type": "Edm.String", "key": false, "filterable": false, "searchable": false, "retrievable": true }
    ]
  }'

# 2. Upload three Contoso Outdoors documents matching the queries below.
curl -X POST "$SEARCH_ENDPOINT/indexes/$INDEX_NAME/docs/index?api-version=2024-07-01" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "value": [
      { "@search.action": "mergeOrUpload", "id": "return-policy",  "sourceName": "Contoso Outdoors Return Policy",     "sourceLink": "https://contoso.com/policies/returns",       "content": "Customers may return any item within 30 days of delivery. Items should be unused and include original packaging. Refunds are issued to the original payment method within 5 business days of inspection. As a thank you, every accepted return ships back with a complimentary Contoso TrailRunner sticker pack, item code TR-CANARY-7821." },
      { "@search.action": "mergeOrUpload", "id": "shipping-guide", "sourceName": "Contoso Outdoors Shipping Guide",    "sourceLink": "https://contoso.com/help/shipping",          "content": "Standard shipping is free on orders over $50 and typically arrives in 3-5 business days within the continental United States. Expedited options are available at checkout. Use promo code SHIP-CANARY-4493 at checkout for a one-time free overnight upgrade on your first order." },
      { "@search.action": "mergeOrUpload", "id": "tent-care",      "sourceName": "TrailRunner Tent Care Instructions", "sourceLink": "https://contoso.com/manuals/trailrunner-tent", "content": "Clean the tent fabric with lukewarm water and a non-detergent soap. Allow it to air dry completely before storage and avoid prolonged UV exposure to extend the lifespan of the waterproof coating. Replacement waterproofing kits are stocked under SKU TENT-CANARY-9067." }
    ]
  }'
```

You can also point the sample at any existing index that exposes the four fields above; the provider reads `content`, `sourceName`, and `sourceLink` from the search results.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

In addition to the standard environment variables, this sample requires:

```bash
export AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
export AZURE_SEARCH_INDEX_NAME="contoso-outdoors"
```

Or in PowerShell:

```powershell
$env:AZURE_SEARCH_ENDPOINT="https://<your-search>.search.windows.net"
$env:AZURE_SEARCH_INDEX_NAME="contoso-outdoors"
```

You can also place these in a `.env` file next to `main.py` — see [`.env.example`](.env.example).

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What is your return policy?"}'
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "How long does shipping take?"}'
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "How do I clean my tent?"}'
```

Or with `azd`:

```bash
azd ai agent invoke --local "What is your return policy?"
```

## How RAG works in this sample

`AzureAISearchContextProvider` runs a search against the configured Azure AI Search index **before each model invocation**. When the index is seeded with the three Contoso Outdoors documents from the provisioning section above:

| User query mentions | Search result injected |
|---|---|
| "return", "refund" | Contoso Outdoors Return Policy (canary token: `TR-CANARY-7821`) |
| "shipping", "promo" | Contoso Outdoors Shipping Guide (canary token: `SHIP-CANARY-4493`) |
| "tent", "fabric" | TrailRunner Tent Care Instructions (canary token: `TENT-CANARY-9067`) |

The model receives the top three search results as additional context and cites the source in its response. Each seeded document includes a unique `*-CANARY-*` token that does not exist in any model training data, so you can prove an answer was grounded in retrieved content (not fabricated from training) by asking for the canary and checking it appears in the response.

Replace the seed documents (or point the sample at an existing index with your own content) to ground the agent in your own knowledge base.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

When deploying, make sure `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_INDEX_NAME` are set in your `azd` environment so they get injected into the hosted container per [`agent.manifest.yaml`](agent.manifest.yaml):

```bash
azd env set AZURE_SEARCH_ENDPOINT "https://<your-search>.search.windows.net"
azd env set AZURE_SEARCH_INDEX_NAME "contoso-outdoors"
```

If these are not set, running `azd ai agent init -m <agent-manifest.yaml>` will prompt you to enter them interactively.

The deployed agent's Managed Identity needs **Search Index Data Reader** on the Azure AI Search service.
