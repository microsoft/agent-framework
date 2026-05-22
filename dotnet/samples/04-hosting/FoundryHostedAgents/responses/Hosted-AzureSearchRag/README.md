# Hosted-AzureSearchRag

A hosted agent with **Retrieval Augmented Generation (RAG)** capabilities backed by **Azure AI Search**. The agent grounds its answers in product documentation by running a keyword search against an Azure AI Search index before each model invocation, then citing the source in its response.

This sample is the Azure AI Search counterpart to `Hosted-TextRag`. Where `Hosted-TextRag` uses a mock in-process search function, this sample talks to a real Azure AI Search index that is provisioned out of band (see "Provisioning the search index" below).

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a deployed model (e.g., `gpt-4o`)
- An Azure AI Search service ([create one](https://learn.microsoft.com/azure/search/search-create-service-portal))
- **A pre-provisioned search index** with the schema and content described in the next section
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs:

- **Azure AI User** on the Foundry project scope
- **Search Index Data Reader** on the Azure AI Search service (the sample only reads from the index)

## Provisioning the search index (one time)

The sample assumes the search index already exists and contains documents the agent can retrieve from. Provision it once via the Azure Portal, the [REST API](https://learn.microsoft.com/azure/search/search-how-to-create-search-index), or the snippet below.

### Index schema

| Field | Type | Attributes |
|---|---|---|
| `id` | `Edm.String` | key, filterable |
| `content` | `Edm.String` | searchable (full-text) |
| `sourceName` | `Edm.String` | retrievable, filterable |
| `sourceLink` | `Edm.String` | retrievable |

### Example: provision and seed via Azure CLI + REST

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

You can also point the sample at any existing index that exposes the four fields above; the sample reads `content`, `sourceName`, and `sourceLink` as projected by the search results.

## Configuration

Copy the template and fill in your endpoints:

```bash
cp .env.example .env
```

Edit `.env`:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
AZURE_SEARCH_INDEX_NAME=contoso-outdoors
AZURE_BEARER_TOKEN_FOUNDRY=DefaultAzureCredential
AZURE_BEARER_TOKEN_SEARCH=DefaultAzureCredential
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework source.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-AzureSearchRag
AGENT_NAME=hosted-azure-search-rag dotnet run
```

The agent will start on `http://localhost:8088`. The sample assumes the search index has already been provisioned and seeded (see "Provisioning the search index" above).

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What is your return policy?"
azd ai agent invoke --local "How long does shipping take?"
azd ai agent invoke --local "How do I clean my tent?"
```

Or with curl:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "What is your return policy?", "model": "hosted-azure-search-rag"}'
```

## Running with Docker

Since this project uses `ProjectReference`, use `Dockerfile.contributor` which takes a pre-published output.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-azure-search-rag .
```

### 3. Run the container

Generate two bearer tokens on your host (one per audience) and pass them to the container. A single Azure AD token has only one `aud` claim, so Foundry and Azure AI Search require separate tokens.

```bash
# Generate tokens (each expires in ~1 hour)
export AZURE_BEARER_TOKEN_FOUNDRY=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
export AZURE_BEARER_TOKEN_SEARCH=$(az account get-access-token --resource https://search.azure.com --query accessToken -o tsv)

# Run with both tokens
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-azure-search-rag \
  -e AZURE_BEARER_TOKEN_FOUNDRY=$AZURE_BEARER_TOKEN_FOUNDRY \
  -e AZURE_BEARER_TOKEN_SEARCH=$AZURE_BEARER_TOKEN_SEARCH \
  --env-file .env \
  hosted-azure-search-rag
```

### 4. Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "What is your return policy?"
```

## How RAG works in this sample

The `TextSearchProvider` runs a keyword search against the configured Azure AI Search index **before each model invocation**. When the index is seeded with the three Contoso Outdoors documents from the provisioning section above:

| User query mentions | Search result injected |
|---|---|
| "return", "refund" | Contoso Outdoors Return Policy (canary token: `TR-CANARY-7821`) |
| "shipping", "promo" | Contoso Outdoors Shipping Guide (canary token: `SHIP-CANARY-4493`) |
| "tent", "fabric" | TrailRunner Tent Care Instructions (canary token: `TENT-CANARY-9067`) |

The model receives the top three search results as additional context and cites the source in its response. Each seeded document includes a unique `*-CANARY-*` token that does not exist in any model training data, so the integration tests can prove an answer was grounded in retrieved content (not fabricated from training) by asking for the canary and asserting it appears in the response.

Replace the seed documents (or point the sample at an existing index with your own content) to ground the agent in your own knowledge base.

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from source), use the standard `Dockerfile` instead of `Dockerfile.contributor`. See the commented section in `HostedAzureSearchRag.csproj` for the `PackageReference` alternative.
