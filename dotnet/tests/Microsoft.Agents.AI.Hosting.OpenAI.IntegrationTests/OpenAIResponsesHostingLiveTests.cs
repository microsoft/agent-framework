// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.Hosting.OpenAI.IntegrationTests;

/// <summary>
/// Live integration tests for the app-owned routing helper surface (<see cref="OpenAIResponses"/> plus
/// <see cref="AgentSessionStore"/>) exercised against a real OpenAI model. These confirm the crucial
/// consumption paths — request conversion, an agent run, response rendering, and multi-turn session
/// continuity — behave correctly end to end with a real chat client.
/// </summary>
/// <remarks>
/// Skipped unless the OpenAI configuration is present (<c>OPENAI_API_KEY</c>), so runs without secrets stay
/// green. The in-process, in-memory (no live model) coverage lives in the
/// <c>Microsoft.Agents.AI.Hosting.OpenAI.UnitTests</c> project (<c>OpenAIResponsesHostingTests</c>).
/// </remarks>
public sealed class OpenAIResponsesHostingLiveTests
{
    private static string? ApiKey => Environment.GetEnvironmentVariable(TestSettings.OpenAIApiKey);
    private static string ModelName => Environment.GetEnvironmentVariable(TestSettings.OpenAIChatModelName) ?? "gpt-4o-mini";

    [Fact]
    public async Task NonStreamingRun_RendersResponsesShapedPayloadAsync()
    {
        // Arrange
        Assert.SkipWhen(string.IsNullOrEmpty(ApiKey), "OPENAI_API_KEY is not configured; skipping live hosting test.");
        AIAgent agent = CreateAgent();
        AgentSessionStore sessionStore = new InMemoryAgentSessionStore();
        JsonElement body = ParseBody("""{ "input": "Reply with exactly the word: apple" }""");

        // Act
        OpenAIResponsesRunRequest run = OpenAIResponses.ToAgentRunRequest(body);
        string sessionStoreId = OpenAIResponses.GetSessionStoreId(run) ?? OpenAIResponses.CreateResponseId();
        AgentSession session = await sessionStore.GetSessionAsync(agent, sessionStoreId);
        string responseId = OpenAIResponses.CreateResponseId();
        AgentResponse result = await agent.RunAsync(run.Messages, session, run.Options);
        JsonElement payload = OpenAIResponses.WriteResponse(result, responseId, responseId);

        // Assert
        Assert.Equal(responseId, payload.GetProperty("id").GetString());
        Assert.Equal("response", payload.GetProperty("object").GetString());
        Assert.Contains("output", payload.EnumerateObject().Select(p => p.Name));
    }

    [Fact]
    public async Task MultiTurn_ContinuesSessionAcrossTurnsAsync()
    {
        // Arrange
        Assert.SkipWhen(string.IsNullOrEmpty(ApiKey), "OPENAI_API_KEY is not configured; skipping live hosting test.");
        AIAgent agent = CreateAgent();
        AgentSessionStore sessionStore = new InMemoryAgentSessionStore();

        // Act: first turn establishes context, second turn continues from the first response id.
        string firstResponseId = await RunTurnAsync(agent, sessionStore, """{ "input": "Remember the number 7." }""");
        JsonElement secondBody = ParseBody($$"""{ "input": "What number did I ask you to remember?", "previous_response_id": "{{firstResponseId}}" }""");
        OpenAIResponsesRunRequest secondRun = OpenAIResponses.ToAgentRunRequest(secondBody);
        string secondSessionStoreId = OpenAIResponses.GetSessionStoreId(secondRun)!;
        AgentSession session = await sessionStore.GetSessionAsync(agent, secondSessionStoreId);
        AgentResponse secondResult = await agent.RunAsync(secondRun.Messages, session, secondRun.Options);

        // Assert: continuation succeeded and the model produced a textual answer.
        Assert.Equal(secondSessionStoreId, firstResponseId);
        Assert.False(string.IsNullOrWhiteSpace(secondResult.Text));
    }

    private static async Task<string> RunTurnAsync(AIAgent agent, AgentSessionStore sessionStore, string bodyJson)
    {
        JsonElement body = ParseBody(bodyJson);
        OpenAIResponsesRunRequest run = OpenAIResponses.ToAgentRunRequest(body);
        string sessionStoreId = OpenAIResponses.GetSessionStoreId(run) ?? OpenAIResponses.CreateResponseId();
        AgentSession session = await sessionStore.GetSessionAsync(agent, sessionStoreId);
        string responseId = OpenAIResponses.CreateResponseId();
        _ = await agent.RunAsync(run.Messages, session, run.Options);
        await sessionStore.SaveSessionAsync(agent, responseId, session);
        return responseId;
    }

    private static ChatClientAgent CreateAgent() =>
        new(
            new OpenAIClient(ApiKey).GetChatClient(ModelName).AsIChatClient(),
            instructions: "You are a concise assistant.",
            name: "assistant");

    private static JsonElement ParseBody(string json)
    {
        using JsonDocument doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }
}
