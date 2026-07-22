// Copyright (c) Microsoft. All rights reserved.

// This sample shows how an application can own its own ASP.NET Core route and expose an AIAgent over the
// OpenAI Responses protocol by calling the Agent Framework OpenAIResponses conversion helpers, instead of
// using the batteries-included MapOpenAIResponses server. The application keeps control of routing, auth,
// and session storage; the helpers provide only the protocol <-> agent conversion.

using System.ComponentModel;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Extensions.AI;

var builder = WebApplication.CreateBuilder(args);

// Configuration via environment variables (never hardcode secrets).
string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// A deterministic weather tool.
[Description("Return a deterministic weather report for a city.")]
static string LookupWeather([Description("The city to look up weather for.")] string location)
{
    int highTemp = 5 + (System.Text.Encoding.UTF8.GetBytes(location).Sum(b => b) % 21);
    return location switch
    {
        "Seattle" => $"Seattle is rainy with a high of {highTemp}°C.",
        "Amsterdam" => $"Amsterdam is cloudy with a high of {highTemp}°C.",
        "Tokyo" => $"Tokyo is clear with a high of {highTemp}°C.",
        _ => $"{location} is sunny with a high of {highTemp}°C.",
    };
}

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(
        model: model,
        instructions: "You are a friendly weather assistant. Use the lookup_weather tool for any weather " +
            "question and answer in one short sentence.",
        name: "WeatherAgent",
        tools: [AIFunctionFactory.Create(LookupWeather, name: "lookup_weather")]);

// The application owns session storage directly. The in-memory store's GetSessionAsync creates a session
// on first use and returns an independent instance per call; no shared holder is needed. A real app that
// runs concurrent turns against the same session id owns any coordination it needs.
AgentSessionStore sessionStore = new InMemoryAgentSessionStore();

var app = builder.Build();

// The application owns this route. It parses the OpenAI Responses body with the helpers, runs the agent
// itself, and renders the response with the helpers. Binding the body as JsonElement lets ASP.NET Core
// deserialize the JSON request body directly, so there is no JsonDocument to own or dispose.
app.MapPost("/responses", async (JsonElement body, HttpContext http, CancellationToken cancellationToken) =>
{
    // Parse the request first, then read the continuation id off the parsed request (no second parse).
    OpenAIResponsesRunRequest run = OpenAIResponses.ToAgentRunRequest(body);

    // The candidate continuation id is untrusted. A real app authenticates the caller and authorizes/binds
    // this key to the principal before using it. This sample simply falls back to a fresh id.
    string? candidateSessionStoreId = OpenAIResponses.GetSessionStoreId(run);
    string sessionStoreId = Authorize(http, candidateSessionStoreId) ?? OpenAIResponses.CreateResponseId();

    AgentSession session = await sessionStore.GetSessionAsync(agent, sessionStoreId, cancellationToken).ConfigureAwait(false);
    string responseId = OpenAIResponses.CreateResponseId();

    // Choose where to persist the post-run session, which depends on how the caller continued the thread:
    // - A stable "conversation" id is a MUTABLE HEAD: write the advanced session back under the same id so
    //   the next turn on that conversation sees this turn. Concurrent runs against one conversation id are
    //   NOT serialized here; a production app must provide its own per-conversation single-writer coordination.
    // - Otherwise (a "previous_response_id" continuation or a first turn) the new response id is an IMMUTABLE
    //   SNAPSHOT: persist under it so a later previous_response_id can branch from this exact point, and two
    //   branches from the same prior response stay independent.
    string? conversationId = run.ConversationId is { Length: > 0 } cid && cid == sessionStoreId ? cid : null;
    string saveId = conversationId ?? responseId;

    bool stream = body.TryGetProperty("stream", out JsonElement streamProp) && streamProp.ValueKind == JsonValueKind.True;

    if (stream)
    {
        http.Response.ContentType = "text/event-stream";
        var updates = agent.RunStreamingAsync(run.Messages, session, run.Options, cancellationToken);
        await foreach (string frame in OpenAIResponses.WriteResponseStreamAsync(updates, responseId, responseId, cancellationToken).ConfigureAwait(false))
        {
            await http.Response.WriteAsync(frame, cancellationToken).ConfigureAwait(false);
            await http.Response.Body.FlushAsync(cancellationToken).ConfigureAwait(false);
        }

        // Persist the post-run session under the selected continuation id (see saveId above).
        await sessionStore.SaveSessionAsync(agent, saveId, session, cancellationToken).ConfigureAwait(false);

        // The SSE body was already written straight to http.Response above, so return an empty result:
        // this returns from the handler (the non-streaming code below does not run) without writing a body.
        return Results.Empty;
    }

    AgentResponse result = await agent.RunAsync(run.Messages, session, run.Options, cancellationToken).ConfigureAwait(false);
    await sessionStore.SaveSessionAsync(agent, saveId, session, cancellationToken).ConfigureAwait(false);
    return Results.Json(OpenAIResponses.WriteResponse(result, responseId, responseId));
});

// Bind to a fixed local URL so the paired client sample has a deterministic default.
// Override with the ASPNETCORE_URLS environment variable when needed.
app.Run("http://localhost:5000");

// Application-owned trust decision. Replace with real authentication + authorization: verify the caller,
// then authorize/bind the candidate id to the authenticated principal before returning it.
static string? Authorize(HttpContext http, string? candidateSessionStoreId) => candidateSessionStoreId;
