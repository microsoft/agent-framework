// Copyright (c) Microsoft. All rights reserved.

// Persist DevUI conversations, agent sessions, and chat history in SQLite.
using DevUIWithSqlitePersistence;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);

builder.WebHost.UseUrls("http://localhost:5130");
builder.AddDevUI();

string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is required.");
string model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-5.4-mini";
string databasePath = Environment.GetEnvironmentVariable("AGENT_DATABASE_PATH") ?? "conversations.db";
string? endpoint = Environment.GetEnvironmentVariable("OPENAI_ENDPOINT");

var clientOptions = new OpenAIClientOptions();
if (!string.IsNullOrWhiteSpace(endpoint))
{
    clientOptions.Endpoint = new Uri(endpoint);
}

var openAIClient = new OpenAIClient(new System.ClientModel.ApiKeyCredential(apiKey), clientOptions)
    .GetChatClient(model)
    .AsIChatClient();
var database = new SqliteConversationDatabase(databasePath);
var historyProvider = new SqliteChatHistoryProvider(database);

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
    // DevUI sends requests sequentially in this local sample. Production hosts should enable
    // caller isolation and coordinate concurrent turns for the same conversation.
    .WithSessionStore(database, withIsolation: false);

builder.Services.AddOpenAIChatCompletions();
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();
builder.Services.UseOpenAIConversationStore(database);

WebApplication app = builder.Build();

app.MapOpenAIResponses();
app.MapOpenAIConversations();
app.MapOpenAIChatCompletions(agentBuilder);
app.MapDevUI();

await app.RunAsync();
