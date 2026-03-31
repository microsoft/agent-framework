# Agent with Neo4j GraphRAG Context Provider

This sample demonstrates how to create and run an agent that uses the [Neo4j GraphRAG context provider](https://github.com/neo4j-labs/neo4j-maf-provider) to retrieve relevant documents from Neo4j vector and fulltext indexes, optionally enriching results by traversing graph relationships.

## Features Demonstrated

- Vector search with semantic similarity using embeddings
- Fulltext search with BM25 scoring (no embedding generator required)
- Hybrid search combining vector + fulltext for best of both worlds
- Graph-enriched search using custom Cypher `RetrievalQuery` to traverse related entities

## Prerequisites

- .NET 10 SDK or later
- Neo4j database with a vector or fulltext index containing your documents
  - [Neo4j AuraDB](https://neo4j.com/cloud/auradb/) (managed) or self-hosted
- Azure OpenAI service endpoint with both a chat completion and embedding deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

**Note**: These samples use Azure OpenAI models. For more information, see [how to deploy Azure OpenAI models with Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai).

**Note**: These samples use Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource and have the `Cognitive Services OpenAI Contributor` role. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Environment Variables

```powershell
# Neo4j connection
$env:NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
$env:NEO4J_USERNAME="neo4j"
$env:NEO4J_PASSWORD="your-password"
$env:NEO4J_VECTOR_INDEX_NAME="chunkEmbeddings"        # Required for vector/hybrid search
$env:NEO4J_FULLTEXT_INDEX_NAME="chunkFulltext"         # Required for fulltext/hybrid search

# Azure OpenAI
$env:AZURE_AI_SERVICES_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_AI_MODEL_NAME="gpt-4o"                     # Chat model deployment name
$env:AZURE_AI_EMBEDDING_NAME="text-embedding-3-small"  # Embedding model deployment name
```

## Code Example

### Vector Search with Graph Enrichment

```csharp
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.OpenAI;
using Microsoft.Extensions.AI;
using Neo4j.AgentFramework.GraphRAG;
using Neo4j.Driver;

var neo4jSettings = new Neo4jSettings();

var azureClient = new AzureOpenAIClient(
    new Uri(Environment.GetEnvironmentVariable("AZURE_AI_SERVICES_ENDPOINT")!),
    new DefaultAzureCredential());

var embeddingGenerator = azureClient
    .GetEmbeddingClient(Environment.GetEnvironmentVariable("AZURE_AI_EMBEDDING_NAME"))
    .AsIEmbeddingGenerator();

await using var driver = GraphDatabase.Driver(
    neo4jSettings.Uri!, AuthTokens.Basic(neo4jSettings.Username!, neo4jSettings.Password!));

await using var provider = new Neo4jContextProvider(
    driver,
    new Neo4jContextProviderOptions
    {
        IndexName = "chunkEmbeddings",
        IndexType = IndexType.Vector,
        EmbeddingGenerator = embeddingGenerator,
        TopK = 5,
        RetrievalQuery = """
            MATCH (node)-[:FROM_DOCUMENT]->(doc:Document)<-[:FILED]-(company:Company)
            RETURN node.text AS text, score, company.name AS company, doc.title AS title
            ORDER BY score DESC
            """
    });

var chatClient = azureClient
    .GetChatClient(Environment.GetEnvironmentVariable("AZURE_AI_MODEL_NAME"))
    .AsIChatClient();

var agent = chatClient
    .AsBuilder()
    .UseAIContextProviders(provider)
    .BuildAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a financial analyst assistant.",
        },
    });

var session = await agent.CreateSessionAsync();
var response = await agent.RunAsync("What risks does Acme Corp face?", session);
Console.WriteLine(response);
```

### Fulltext Search (No Embedding Generator Required)

```csharp
await using var provider = new Neo4jContextProvider(
    driver,
    new Neo4jContextProviderOptions
    {
        IndexName = "search_chunks",
        IndexType = IndexType.Fulltext,
        TopK = 5,
    });
```

### Hybrid Search

```csharp
await using var provider = new Neo4jContextProvider(
    driver,
    new Neo4jContextProviderOptions
    {
        IndexName = "chunkEmbeddings",
        IndexType = IndexType.Hybrid,
        FulltextIndexName = "chunkFulltext",
        EmbeddingGenerator = embeddingGenerator,
        TopK = 5,
    });
```

## Run the Sample

For the full runnable sample, see the [Neo4j.Samples project](https://github.com/neo4j-labs/neo4j-maf-provider/tree/main/dotnet/samples/Neo4j.Samples).

## Additional Resources

- [Neo4j GraphRAG Provider Repository](https://github.com/neo4j-labs/neo4j-maf-provider)
- [Neo4j GraphRAG Python Library](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [Neo4j Vector Index Documentation](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
