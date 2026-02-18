# Neo4j Context Providers

Neo4j offers two context providers for the Agent Framework, each serving a different purpose:

| | [Neo4j Memory](../neo4j_memory/README.md) | [Neo4j GraphRAG](../neo4j_graphrag/README.md) |
|---|---|---|
| **What it does** | Read-write memory — stores conversations, builds knowledge graphs, learns from interactions | Read-only retrieval from a pre-existing knowledge base with optional graph traversal |
| **Data source** | Agent interactions (grows over time) | Pre-loaded documents and indexes |
| **Package** | [`neo4j-agent-memory`](https://github.com/neo4j-labs/agent-memory) | [`agent-framework-neo4j`](https://github.com/neo4j-labs/neo4j-maf-provider) |
| **Database setup** | Empty — creates its own schema | Requires pre-indexed documents with vector or fulltext indexes |
| **Example use case** | "Remember my preferences", "What did we discuss last time?" | "Search our documents", "What risks does Acme Corp face?" |

## Which should I use?

**Use [Neo4j Memory](../neo4j_memory/README.md)** when your agent needs to remember things across sessions — user preferences, past conversations, extracted entities, and reasoning traces. The memory provider writes to the database on every interaction, building a knowledge graph that grows over time.

**Use [Neo4j GraphRAG](../neo4j_graphrag/README.md)** when your agent needs to search an existing knowledge base — documents, articles, product catalogs — and optionally enrich results by traversing graph relationships. The GraphRAG provider is read-only and does not modify your data.

You can use both together: GraphRAG for domain knowledge retrieval, Memory for personalization and learning.
