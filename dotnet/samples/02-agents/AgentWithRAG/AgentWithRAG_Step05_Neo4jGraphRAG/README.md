# Agent Framework Retrieval Augmented Generation (RAG) with Neo4j GraphRAG

This sample demonstrates how to create and run an agent that uses the [Neo4j GraphRAG context provider](https://github.com/neo4j-labs/neo4j-maf-provider) with Microsoft Agent Framework for .NET.

The sample uses a Neo4j fulltext index for retrieval and a Cypher `RetrievalQuery` to enrich results with related companies, products, and risk factors.

## Prerequisites

- .NET 10 SDK or later
- Azure OpenAI endpoint and chat deployment
- Azure CLI installed and authenticated
- A Neo4j database with chunked documents and a fulltext index such as `search_chunks`

## Environment variables

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"
$env:NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
$env:NEO4J_USERNAME="neo4j"
$env:NEO4J_PASSWORD="your-password"
$env:NEO4J_FULLTEXT_INDEX_NAME="search_chunks"
```

## Build and run

```powershell
dotnet build
dotnet run --framework net10.0 --no-build
```

The sample issues a few questions against the graph-backed retrieval provider and prints the responses to the console.
