// Copyright (c) Microsoft. All rights reserved.

// Store hosted agent chat history in PostgreSQL and exercise it through DevUI.
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using DevUIWithPostgresPersistence.AgentService;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

builder.AddDevUI();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is required.");
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL")
    ?? Environment.GetEnvironmentVariable("FOUNDRY_MODEL_NAME")
    ?? "gpt-5.4-mini";
string connectionString = builder.Configuration.GetConnectionString("conversations")
    ?? throw new InvalidOperationException("Connection string 'conversations' is required.");

PostgresAgentSessionStore store = await PostgresAgentSessionStore.CreateAsync(connectionString);
var historyProvider = new DatabaseChatHistoryProvider(store);

IChatClient CreateChatClient() =>
    // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
    // In production, consider using a specific credential (e.g. ManagedIdentityCredential) to avoid
    // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
    new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
        .GetProjectOpenAIClient()
        .GetProjectResponsesClient()
        .AsIChatClientWithStoredOutputDisabled(model);

IHostedAgentBuilder agentBuilder = builder.AddAIAgent("assistant", (_, name) =>
    CreateChatClient().AsAIAgent(new ChatClientAgentOptions
    {
        Name = name,
        ChatOptions = new ChatOptions
        {
            ModelId = model,
            Instructions = "You are a helpful assistant. Answer concisely.",
        },
        ChatHistoryProvider = historyProvider,
    }))
    // The session stores the database history key that belongs to the OpenAI conversation ID.
    .WithSessionStore(store, withIsolation: false);
AIAgent chatCompletionsAgent = CreateChatClient().AsAIAgent(
    instructions: "You are a helpful assistant. Answer concisely.",
    name: "assistant");

builder.Services.AddOpenAIChatCompletions();
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

WebApplication app = builder.Build();
app.Lifetime.ApplicationStopped.Register(store.Dispose);

app.MapOpenAIResponses();
app.MapOpenAIConversations();
app.MapOpenAIChatCompletions(chatCompletionsAgent);
app.MapDevUI();

await app.RunAsync();
