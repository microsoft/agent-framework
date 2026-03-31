# Agent Framework with Neo4j

Neo4j offers two context providers for the Agent Framework, each serving a different purpose:

| | Neo4j GraphRAG | Neo4j Memory |
|---|---|---|
| **What it does** | Read-only retrieval from a pre-existing knowledge base with optional graph traversal | Read-write memory — stores conversations, builds knowledge graphs, learns from interactions |
| **Data source** | Pre-loaded documents and indexes | Agent interactions (grows over time) |
| **NuGet package** | [`Neo4j.AgentFramework.GraphRAG`](https://www.nuget.org/packages/Neo4j.AgentFramework.GraphRAG) | — (Python only, see [Neo4j Memory](https://github.com/neo4j-labs/agent-memory)) |
| **Database setup** | Requires pre-indexed documents with vector or fulltext indexes | Empty — creates its own schema |
| **Example use case** | "Search our documents", "What risks does Acme Corp face?" | "Remember my preferences", "What did we discuss last time?" |

## Samples

|Sample|Description|
|---|---|
|[Neo4j GraphRAG](./AgentWithNeo4j_Step01_GraphRAG/)|Retrieve context from a Neo4j knowledge base using vector, fulltext, hybrid, or graph-enriched search.|

## Additional Resources

- [Neo4j GraphRAG Provider Repository](https://github.com/neo4j-labs/neo4j-maf-provider)
- [Neo4j Agent Memory Repository](https://github.com/neo4j-labs/agent-memory)
- [Python Neo4j Context Provider Samples](../../../../python/samples/02-agents/context_providers/neo4j/README.md)
