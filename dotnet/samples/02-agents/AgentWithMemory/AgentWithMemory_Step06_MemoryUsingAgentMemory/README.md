# Agent with Memory Using AgentMemory — Shopping Assistant

A **.NET port of the Neo4j Labs "agent-memory" retail assistant** example
([`microsoft_agent_retail_assistant`](https://github.com/neo4j-labs/agent-memory/tree/main/examples/microsoft_agent_retail_assistant),
referenced from the [Learn integration page](https://learn.microsoft.com/en-us/agent-framework/integrations/neo4j-memory)).
A shopping assistant that **learns a customer's preferences** and **recommends products via graph
traversal**, backed by durable memory in Neo4j.

It uses the [`AgentMemory`](https://www.nuget.org/packages/AgentMemory) library — a .NET port of the
(Python-only) Neo4j Labs memory provider, **not an officially recognized Neo4j integration** — through
its Microsoft Agent Framework adapter.

## Features Demonstrated

- **`Neo4jMemoryContextProvider`** (an `AIContextProvider`) — recalls relevant memory before each run,
  persists new memory after (the same bidirectional pattern as the official provider), and — via
  `ExposeMemoryToolsFromContextProvider = true` — surfaces the memory tools (search / remember / recall)
  itself through `AIContext.Tools`.
- **`ProductCatalog.CreateAIFunctions()`** — retail tools over a Neo4j `:Product` graph (search /
  recommend / related / inventory).
- Preference learning that persists across a brand-new `AgentSession` for the same shopper.
- Graph-based product recommendations and "related products" via traversal.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- A **Neo4j 5.x** instance (the sample bootstraps the schema and seeds sample products)
- An **Azure OpenAI / Foundry** deployment (a chat model + an embedding model)


## Configuration

Set the following environment variables:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | ✅ | — | Azure OpenAI / Foundry endpoint |
| `AZURE_OPENAI_API_KEY` | — | — | API key; if unset, `DefaultAzureCredential` (`az login`) is used |
| `FOUNDRY_MODEL` | — | `gpt-4o-mini` | chat model deployment |
| `FOUNDRY_EMBEDDING_MODEL` | — | `text-embedding-3-small` | embedding model deployment (1536 dims) |
| `NEO4J_URI` | — | `bolt://localhost:7687` | Neo4j bolt URI |
| `NEO4J_USER` | — | `neo4j` | Neo4j user |
| `NEO4J_PASSWORD` | — | `password` | Neo4j password |

> Ensure the embedding model's dimensions match the Neo4j vector-index dimensions AgentMemory bootstraps
> (default 1536, which matches `text-embedding-3-small`).

## Run the Sample

```bash
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.26

export AZURE_OPENAI_ENDPOINT="https://<your-resource>.openai.azure.com"
export AZURE_OPENAI_API_KEY="<your-key>"          # or omit and `az login`
export FOUNDRY_MODEL="gpt-4o-mini"

dotnet run
```

## Expected Output

1. The sample bootstraps the Neo4j schema and seeds a small product graph (`:Product`,
   `:ProductCategory`, `:ProductBrand` nodes).
2. **Session A** — the shopper says she wants running shoes, loves Nike, and has a $150 budget; the
   agent calls the memory tools to remember this and the product tools to recommend matching items.
3. **Session B** — a brand-new session for the same shopper (`shopper-amelia`) still recalls her
   preferences and can suggest something new, because memory persists in Neo4j across sessions.

## Note on packaging

This sample is part of the repo's solution and targets .NET 10 like every other sample, but it
deliberately opts out of **Central Package Management** and does **not** reference `Microsoft.Agents.AI`
via the repo's in-source project — it consumes the **published** `AgentMemory` NuGet packages instead
(which target `Microsoft.Agents.AI` 1.9.0). A version that references the repo's current
`Microsoft.Agents.AI` source would require AgentMemory to be rebuilt against that version first.
