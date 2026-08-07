// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to persist chat history in Azure Cosmos DB for NoSQL using the ChatHistoryMemoryProvider.
// The agent can then use chat history from prior conversations to inform responses in new conversations.

using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using CommunityToolkit.VectorData.CosmosNoSql;
using Microsoft.Agents.AI;
using Microsoft.Azure.Cosmos;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.VectorData;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
var embeddingDeploymentName = Environment.GetEnvironmentVariable("FOUNDRY_EMBEDDING_MODEL") ?? "text-embedding-3-large";
var embeddingDimensions = 3072;
if (Environment.GetEnvironmentVariable("FOUNDRY_EMBEDDING_DIMENSIONS") is string embeddingDimensionsValue &&
    (!int.TryParse(embeddingDimensionsValue, out embeddingDimensions) || embeddingDimensions <= 0))
{
    throw new InvalidOperationException("FOUNDRY_EMBEDDING_DIMENSIONS must be a positive integer.");
}
var cosmosEndpoint = Environment.GetEnvironmentVariable("COSMOS_ENDPOINT") ?? throw new InvalidOperationException("COSMOS_ENDPOINT is not set.");
var cosmosDatabaseName = Environment.GetEnvironmentVariable("COSMOS_DATABASE_NAME") ?? "agent-memory";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
DefaultAzureCredential credential = new();
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

using CosmosClient cosmosClient = new(
    cosmosEndpoint,
    credential,
    new CosmosClientOptions
    {
        UseSystemTextJsonSerializerWithOptions = JsonSerializerOptions.Default,
    });

DatabaseResponse databaseResponse = await cosmosClient.CreateDatabaseIfNotExistsAsync(cosmosDatabaseName);

VectorStore vectorStore = new CosmosNoSqlVectorStore(
    databaseResponse.Database,
    new CosmosNoSqlVectorStoreOptions
    {
        JsonSerializerOptions = JsonSerializerOptions.Default,
        EmbeddingGenerator = aiProjectClient
            .GetProjectOpenAIClient()
            .GetEmbeddingClient(embeddingDeploymentName)
            .AsIEmbeddingGenerator(),
    });

var userId = $"sample-{Guid.NewGuid():N}";

// Create the agent and add the ChatHistoryMemoryProvider to store chat messages in Cosmos DB.
AIAgent agent = aiProjectClient
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are good at telling jokes." },
        Name = "Joker",
        AIContextProviders = [new ChatHistoryMemoryProvider(
            vectorStore,
            collectionName: "chathistory",
            vectorDimensions: embeddingDimensions,
            // Callback to configure the initial state of the ChatHistoryMemoryProvider.
            // The ChatHistoryMemoryProvider stores its state in the AgentSession and this callback
            // will be called whenever the ChatHistoryMemoryProvider cannot find existing state in the session,
            // typically the first time it is used with a new session.
            _ => new ChatHistoryMemoryProvider.State(
                // Configure the scope values under which chat messages will be stored.
                // In this case, we are using a per-run user ID and a unique session ID for each new session.
                storageScope: new() { UserId = userId, SessionId = Guid.NewGuid().ToString("N") },
                // Configure the scope which would be used to search for relevant prior messages.
                // In this case, we are searching for any messages for the user across all sessions.
                searchScope: new() { UserId = userId }))]
    });

// Start a new session for the agent conversation.
AgentSession session = await agent.CreateSessionAsync();

// Run the agent with the session that stores conversation history in Cosmos DB.
Console.WriteLine("First session:");
Console.WriteLine(await agent.RunAsync("I like jokes about Pirates. Tell me a joke about a pirate.", session));

// Start a second session. Since we configured the search scope to be across all sessions for the user,
// the agent should remember that the user likes pirate jokes.
AgentSession session2 = await agent.CreateSessionAsync();

// Run the agent with the second session.
Console.WriteLine("Second session (recalling prior chat history from Cosmos DB):");
Console.WriteLine(await agent.RunAsync("Tell me a joke that I might like.", session2));
