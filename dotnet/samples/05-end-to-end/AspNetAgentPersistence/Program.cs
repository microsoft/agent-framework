// Copyright (c) Microsoft. All rights reserved.

// Persist local agent sessions in SQLite and resume them through a .NET API.
using AspNetAgentPersistence;
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;

var builder = WebApplication.CreateBuilder(args);

// This anonymous sample is for local development only.
builder.WebHost.UseUrls("http://localhost:5130");
string apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is required.");
string model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-5.4-mini";
string databasePath = Environment.GetEnvironmentVariable("AGENT_DATABASE_PATH") ?? "conversations.db";

AIAgent agent = new OpenAIClient(apiKey).GetChatClient(model)
    .AsAIAgent(instructions: "You are a helpful business assistant.");
var conversations = new ConversationStore(databasePath);
// Serialize local requests to avoid lost updates across the load/run/save cycle.
using SemaphoreSlim turnLock = new(1, 1);

var app = builder.Build();
app.MapPost("/conversations", () => Results.Ok(new { conversationId = Guid.NewGuid() }));
app.MapPost("/conversations/{conversationId:guid}/messages", async (Guid conversationId, ChatRequest request, CancellationToken cancellationToken) =>
{
    if (string.IsNullOrWhiteSpace(request.Message))
    {
        return Results.BadRequest("Message is required.");
    }

    await turnLock.WaitAsync(cancellationToken);
    try
    {
        AgentSession session = await conversations.LoadAsync(agent, conversationId, cancellationToken);
        AgentResponse response = await agent.RunAsync(request.Message, session, cancellationToken: cancellationToken);
        // Save only after a successful turn. Failed runs leave the last committed session intact.
        // A disconnected client must not cancel persistence of an already completed turn.
        await conversations.SaveAsync(agent, conversationId, session, CancellationToken.None);
        return Results.Ok(new { conversationId, response = response.Text });
    }
    finally
    {
        turnLock.Release();
    }
});

await app.RunAsync();

internal sealed record ChatRequest(string Message);
