// Copyright (c) Microsoft. All rights reserved.

// Store hosted agent chat history in PostgreSQL and exercise it through DevUI.
using DevUIWithPostgresPersistence.AgentService;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

builder.AddDevUI();

string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is required.");
string model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-5.4-mini";
string? endpoint = Environment.GetEnvironmentVariable("OPENAI_ENDPOINT");
string connectionString = builder.Configuration.GetConnectionString("conversations")
    ?? throw new InvalidOperationException("Connection string 'conversations' is required.");

var clientOptions = new OpenAIClientOptions();
if (!string.IsNullOrWhiteSpace(endpoint))
{
    clientOptions.Endpoint = new Uri(endpoint);
}

var openAIClient = new OpenAIClient(new System.ClientModel.ApiKeyCredential(apiKey), clientOptions)
    .GetChatClient(model)
    .AsIChatClient();
PostgresConversationStore store = await PostgresConversationStore.CreateAsync(connectionString);
var historyProvider = new DatabaseChatHistoryProvider(store);

IHostedAgentBuilder agentBuilder = builder.AddAIAgent("assistant", (_, name) =>
    openAIClient.AsAIAgent(new ChatClientAgentOptions
    {
        Name = name,
        ChatOptions = new ChatOptions
        {
            Instructions = "You are a helpful assistant. Answer concisely.",
        },
        ChatHistoryProvider = historyProvider,
    }))
    // The session stores the database history key that belongs to the OpenAI conversation ID.
    .WithSessionStore(store, withIsolation: false);

builder.Services.AddOpenAIChatCompletions();
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

WebApplication app = builder.Build();
app.Lifetime.ApplicationStopped.Register(store.Dispose);

app.MapOpenAIResponses();
app.MapOpenAIConversations();
app.MapOpenAIChatCompletions(agentBuilder);
app.MapDevUI();

await app.RunAsync();
