# Neo4j GraphRAG Context Provider

The [Neo4j GraphRAG context provider](https://github.com/neo4j-labs/neo4j-maf-provider) adds read-only retrieval from a Neo4j knowledge graph to an Agent Framework agent. It supports vector, fulltext, and hybrid retrieval, and can enrich search results by traversing graph relationships with a Cypher `retrieval_query`.

This sample keeps setup lightweight by using a pre-built Neo4j fulltext index plus a graph-enrichment query.

For full documentation, see the [Neo4j GraphRAG integration guide on Microsoft Learn](https://learn.microsoft.com/agent-framework/integrations/neo4j-graphrag).

## Example

| File | Description |
|---|---|
| [`main.py`](main.py) | Runnable GraphRAG sample using a Neo4j fulltext index and a Cypher enrichment query to surface related companies, products, and risk factors. |

## Prerequisites

1. A Neo4j database with document chunks already loaded
2. A Neo4j fulltext index over chunk text, such as `search_chunks`
3. An Azure AI Foundry project endpoint and chat deployment
4. Azure CLI authentication via `az login`

## Environment variables

This sample expects:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `NEO4J_FULLTEXT_INDEX_NAME` (optional, defaults to `search_chunks`)

## Run with uv

From the `python/` directory:

```bash
uv run samples/05-end-to-end/neo4j_graphrag/main.py
```

## Notes

- This sample uses the published `agent-framework-neo4j` package rather than code from this repository.
- The package also supports vector and hybrid retrieval when you configure embeddings and indexes in Neo4j.
- For memory-oriented scenarios, the Neo4j project also maintains companion examples in the external provider repository.
