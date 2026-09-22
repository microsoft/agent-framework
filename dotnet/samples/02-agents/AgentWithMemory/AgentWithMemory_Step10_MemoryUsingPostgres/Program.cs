// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to persist typed, cross-session agent memory in PostgreSQL using
// PostgresMemoryClient and PostgresMemoryContextProvider.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Postgres;
using Microsoft.Extensions.AI;
using Npgsql;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";
// The model and dimensions must match: text-embedding-3-small produces 1,536 dimensions by default,
// while text-embedding-3-large produces 3,072. PostgresMemoryClient currently supports up to 2,000.
var embeddingDeploymentName = Environment.GetEnvironmentVariable("FOUNDRY_EMBEDDING_MODEL") ?? "text-embedding-3-small";
var rerankerDeploymentName = Environment.GetEnvironmentVariable("FOUNDRY_RERANKER_MODEL") ?? "cohere-rerank-v3.5";
var postgresConnectionString = Environment.GetEnvironmentVariable("POSTGRES_MEMORY_CONNECTION_STRING") ?? throw new InvalidOperationException("POSTGRES_MEMORY_CONNECTION_STRING is not set.");
var embeddingDimensions = 1536;
if (Environment.GetEnvironmentVariable("FOUNDRY_EMBEDDING_DIMENSIONS") is string embeddingDimensionsValue &&
    (!int.TryParse(embeddingDimensionsValue, out embeddingDimensions) || embeddingDimensions <= 0))
{
    throw new InvalidOperationException("FOUNDRY_EMBEDDING_DIMENSIONS must be a positive integer.");
}

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
DefaultAzureCredential credential = new();
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);
var openAIClient = aiProjectClient.GetProjectOpenAIClient();
IChatClient chatClient = openAIClient.GetChatClient(deploymentName).AsIChatClient();
IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator = openAIClient
    .GetEmbeddingClient(embeddingDeploymentName)
    .AsIEmbeddingGenerator();

NpgsqlDataSourceBuilder dataSourceBuilder = new(postgresConnectionString);
dataSourceBuilder.UseVector();
await using NpgsqlDataSource dataSource = dataSourceBuilder.Build();

if (args.Contains("--azure", StringComparer.OrdinalIgnoreCase))
{
    await RunAzureDemoAsync(
        dataSource,
        embeddingGenerator,
        chatClient,
        rerankerDeploymentName,
        embeddingDimensions);
}
else if (args.Contains("--advanced", StringComparer.OrdinalIgnoreCase))
{
    await RunAdvancedDemoAsync(dataSource, embeddingGenerator, chatClient, deploymentName, embeddingDimensions);
}
else
{
    await RunSimpleDemoAsync(dataSource, embeddingGenerator, chatClient, deploymentName, embeddingDimensions);
}


static async Task RunSimpleDemoAsync(
    NpgsqlDataSource dataSource,
    IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator,
    IChatClient chatClient,
    string deploymentName,
    int embeddingDimensions)
{
    var userId = $"sample-{Guid.NewGuid():N}";

    // This constructor creates and owns the PostgresMemoryClient. AutoProcess is enabled by default.
    await using PostgresMemoryContextProvider memoryProvider = new(
        dataSource,
        embeddingGenerator,
        chatClient,
        _ => new PostgresMemoryContextProvider.State(
            new PostgresMemoryScope
            {
                UserId = userId,
                ThreadId = Guid.NewGuid().ToString("N"),
            }),
        clientOptions: new PostgresMemoryClientOptions
        {
            EmbeddingDimensions = embeddingDimensions,
        });

    AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are good at telling jokes." },
        Name = "Joker",
        AIContextProviders = [memoryProvider],
    });

    Console.WriteLine("First session:");
    AgentSession firstSession = await agent.CreateSessionAsync();
    Console.WriteLine(await agent.RunAsync(
        "Elephants are my favorite animals. Tell me a joke about an elephant.",
        firstSession));

    // Turn writes schedule memory extraction in the background. Wait for it before testing recall.
    await memoryProvider.FlushAsync();

    Console.WriteLine("\nSecond session (recalling memory processed in the background):");
    AgentSession secondSession = await agent.CreateSessionAsync();
    Console.WriteLine(await agent.RunAsync("Tell me a joke that I might like.", secondSession));
}

static async Task RunAdvancedDemoAsync(
    NpgsqlDataSource dataSource,
    IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator,
    IChatClient chatClient,
    string deploymentName,
    int embeddingDimensions)
{

    await using PostgresMemoryClient memoryClient = new(
        dataSource,
        embeddingGenerator,
        chatClient,
        new PostgresMemoryClientOptions
        {
            EmbeddingDimensions = embeddingDimensions,
            // Process explicitly below so each stage of the memory pipeline is visible in the sample.
            AutoProcess = false,
        });

    var userId = $"sample-{Guid.NewGuid():N}";
    PostgresMemoryScope profileScope = CreateScope(userId, "elephant-profile");
    PostgresMemoryScope recallScope = CreateScope(userId, "first-recall");
    PostgresMemoryScope updateScope = CreateScope(userId, "favorite-update");
    PostgresMemoryScope finalRecallScope = CreateScope(userId, "final-recall");
    Queue<PostgresMemoryScope> sessionScopes = new(
        [profileScope, recallScope, updateScope, finalRecallScope]);

    await using PostgresMemoryContextProvider memoryProvider = new(
        memoryClient,
        _ =>
        {
            if (!sessionScopes.TryDequeue(out PostgresMemoryScope? scope))
            {
                throw new InvalidOperationException("No PostgreSQL memory scope is configured for this session.");
            }

            return new PostgresMemoryContextProvider.State(scope);
        },
        new PostgresMemoryContextProviderOptions
        {
            MinConfidence = 0,
            MemoryTypes =
            [
                PostgresMemoryType.Fact,
                PostgresMemoryType.Procedural,
                PostgresMemoryType.Episodic,
            ],
        });

    AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are good at telling jokes." },
        Name = "Joker",
        AIContextProviders = [memoryProvider],
    });

    Console.WriteLine("1. Store turns and extract fact, procedural, and episodic memories");
    AgentSession profileSession = await agent.CreateSessionAsync();
    Console.WriteLine(await agent.RunAsync(
        """
        Elephants are my favorite animals. When I ask for a database mascot, always suggest an elephant.
        At last year's database meetup, I used an elephant puzzle as the audience activity and attendees loved it.
        Suggest a theme for my next PostgreSQL meetup.
        """,
        profileSession));

    // ProcessNowAsync runs extraction, thread summarization, user summarization, and reconciliation.
    await memoryProvider.ProcessNowAsync(profileSession);

    PrintRecords("Stored turns", await memoryClient.GetThreadAsync(profileScope));
    PrintRecords(
        "Active typed memories",
        await memoryClient.GetMemoriesAsync(
            new PostgresMemoryScope { UserId = userId },
            [PostgresMemoryType.Fact, PostgresMemoryType.Procedural, PostgresMemoryType.Episodic],
            minConfidence: 0));
    PrintRecord("Thread summary", await memoryClient.GenerateThreadSummaryAsync(profileScope));
    PrintRecord(
        "Cross-thread user summary",
        await memoryClient.GetUserSummaryAsync(new PostgresMemoryScope { UserId = userId }));

    Console.WriteLine("\n2. Recall all memory types in a new thread");
    AgentSession recallSession = await agent.CreateSessionAsync();
    Console.WriteLine(await agent.RunAsync(
        "Suggest a database mascot and an audience activity that fit what you know about me.",
        recallSession));

    Console.WriteLine("\n3. Store a contradictory preference and reconcile it");
    AgentSession updateSession = await agent.CreateSessionAsync();
    Console.WriteLine(await agent.RunAsync(
        "My favorite animal has changed: giraffes are now my favorite, not elephants. From now on, always suggest a giraffe when I ask for a database mascot.",
        updateSession));

    _ = await memoryClient.ExtractMemoriesAsync(updateScope);
    PrintRecord("Updated thread summary", await memoryClient.GenerateThreadSummaryAsync(updateScope));
    var reconciledCount = await memoryClient.ReconcileAsync(new PostgresMemoryScope { UserId = userId });
    PrintRecord(
        "Updated user summary",
        await memoryClient.GenerateUserSummaryAsync(new PostgresMemoryScope { UserId = userId }));
    Console.WriteLine($"Reconciliation superseded {reconciledCount} conflicting memory record(s).");

    PrintRecords(
        "Active memories after reconciliation",
        await memoryClient.GetMemoriesAsync(
            new PostgresMemoryScope { UserId = userId },
            [PostgresMemoryType.Fact, PostgresMemoryType.Procedural, PostgresMemoryType.Episodic],
            minConfidence: 0));

    Console.WriteLine("\n4. Verify the updated preference in another new thread");
    AgentSession finalRecallSession = await agent.CreateSessionAsync();
    Console.WriteLine(await agent.RunAsync(
        "Which animal should I use as the mascot for my next database meetup?",
        finalRecallSession));
}

static async Task RunAzureDemoAsync(
    NpgsqlDataSource dataSource,
    IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator,
    IChatClient chatClient,
    string rerankerDeploymentName,
    int embeddingDimensions)
{
    var userId = $"azure-sample-{Guid.NewGuid():N}";
    PostgresMemoryScope sourceScope = CreateScope(userId, "database-preferences");
    PostgresMemoryScope searchScope = new() { UserId = userId };

    await using PostgresMemoryClient hybridClient = new(
        dataSource,
        embeddingGenerator,
        chatClient,
        new PostgresMemoryClientOptions
        {
            EmbeddingDimensions = embeddingDimensions,
            VectorIndexKind = PostgresMemoryVectorIndexKind.DiskAnn,
            AutoProcess = false,
        });

    string[] statements =
    [
        "I prefer PostgreSQL for durable agent memory because I need relational filters and vector search together.",
        "I previously evaluated Ingres for short-lived caching.",
        "For analytics archives, I export historical data to object storage.",
        "When choosing a database, operational simplicity matters more to me than benchmark wins.",
    ];
    foreach (var statement in statements)
    {
        await hybridClient.UpsertMemoryAsync(sourceScope, "user", statement);
        _ = await hybridClient.ExtractMemoriesAsync(sourceScope);
    }

    Console.WriteLine("Managed Azure vector index:");
    await PrintDiskAnnIndexesAsync(dataSource);

    const string Query = "Which database does the user prefer for durable agent memory, and why?";
    var hybridResults = await hybridClient.SearchAsync(searchScope, Query, topK: 5, minConfidence: 0);
    PrintSearchResults("Hybrid retrieval before semantic reranking", hybridResults);

    await using PostgresMemoryClient rerankedClient = new(
        dataSource,
        embeddingGenerator,
        chatClient,
        new PostgresMemoryClientOptions
        {
            EmbeddingDimensions = embeddingDimensions,
            VectorIndexKind = PostgresMemoryVectorIndexKind.DiskAnn,
            EnableAzureAiReranking = true,
            AzureAiRerankerModel = rerankerDeploymentName,
            RerankingCandidateCount = 25,
            AutoProcess = false,
        });

    var rerankedResults = await rerankedClient.SearchAsync(searchScope, Query, topK: 5, minConfidence: 0);
    PrintSearchResults("Same candidates after azure_ai.rank()", rerankedResults);
}

static async Task PrintDiskAnnIndexesAsync(NpgsqlDataSource dataSource)
{
    const string Sql = """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'agent_memories_memories'
          AND indexdef ILIKE '% USING diskann %'
        ORDER BY indexname;
        """;

    await using NpgsqlCommand command = dataSource.CreateCommand(Sql);
    await using NpgsqlDataReader reader = await command.ExecuteReaderAsync();
    while (await reader.ReadAsync())
    {
        Console.WriteLine($"- {reader.GetString(0)}: {reader.GetString(1)}");
    }
}

static void PrintSearchResults(string heading, IReadOnlyList<PostgresMemoryRecord> records)
{
    Console.WriteLine($"\n{heading}:");
    foreach (PostgresMemoryRecord record in records)
    {
        var rrfScore = record.Score?.ToString("F4") ?? "n/a";
        var rerankerScore = record.RerankerScore?.ToString("F4") ?? "n/a";
        Console.WriteLine($"- RRF={rrfScore}, reranker={rerankerScore}: {record.Content}");
    }
}

static PostgresMemoryScope CreateScope(string userId, string threadId) =>
    new()
    {
        UserId = userId,
        ThreadId = threadId,
    };

static void PrintRecords(string heading, IReadOnlyList<PostgresMemoryRecord> records)
{
    Console.WriteLine($"\n{heading} ({records.Count}):");
    foreach (PostgresMemoryRecord record in records)
    {
        var role = string.IsNullOrWhiteSpace(record.Role) ? string.Empty : $"/{record.Role}";
        Console.WriteLine($"- [{record.MemoryType}{role}] {record.Content}");
    }
}

static void PrintRecord(string heading, PostgresMemoryRecord? record)
{
    Console.WriteLine($"\n{heading}:");
    Console.WriteLine(record?.Content ?? "(none)");
}
