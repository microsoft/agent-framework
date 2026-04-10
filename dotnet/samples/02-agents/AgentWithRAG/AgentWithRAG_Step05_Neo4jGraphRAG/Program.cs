// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Neo4j.AgentFramework.GraphRAG;
using Neo4j.Driver;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
var neo4jUri = Environment.GetEnvironmentVariable("NEO4J_URI") ?? throw new InvalidOperationException("NEO4J_URI is not set.");
var neo4jUsername = Environment.GetEnvironmentVariable("NEO4J_USERNAME") ?? "neo4j";
var neo4jPassword = Environment.GetEnvironmentVariable("NEO4J_PASSWORD") ?? throw new InvalidOperationException("NEO4J_PASSWORD is not set.");
var fulltextIndex = Environment.GetEnvironmentVariable("NEO4J_FULLTEXT_INDEX_NAME") ?? "search_chunks";

const string RetrievalQuery = """
    MATCH (node)-[:FROM_DOCUMENT]->(doc:Document)<-[:FILED]-(company:Company)
    OPTIONAL MATCH (company)-[:FACES_RISK]->(risk:RiskFactor)
    WITH node, score, company, doc, collect(DISTINCT risk.name)[0..5] AS risks
    OPTIONAL MATCH (company)-[:MENTIONS]->(product:Product)
    WITH node, score, company, doc, risks, collect(DISTINCT product.name)[0..5] AS products
    RETURN
        node.text AS text,
        score,
        company.name AS company,
        company.ticker AS ticker,
        doc.title AS title,
        risks,
        products
    ORDER BY score DESC
    """;

await using var driver = GraphDatabase.Driver(new Uri(neo4jUri), AuthTokens.Basic(neo4jUsername, neo4jPassword));
await driver.VerifyConnectivityAsync();

await using var provider = new Neo4jContextProvider(
    driver,
    new Neo4jContextProviderOptions
    {
        IndexName = fulltextIndex,
        IndexType = IndexType.Fulltext,
        RetrievalQuery = RetrievalQuery,
        TopK = 5,
        ContextPrompt = "Use the retrieved Neo4j graph context to answer accurately and call out when context is missing."
    });

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant that answers questions using Neo4j graph context."
        },
        AIContextProviders = [provider]
    });

AgentSession session = await agent.CreateSessionAsync();

foreach (var question in new[]
{
    "What products does Microsoft offer?",
    "What risks does Apple face?",
    "Tell me about NVIDIA's AI business and risk factors."
})
{
    Console.WriteLine($">> {question}\n");
    Console.WriteLine(await agent.RunAsync(question, session));
    Console.WriteLine();
}
