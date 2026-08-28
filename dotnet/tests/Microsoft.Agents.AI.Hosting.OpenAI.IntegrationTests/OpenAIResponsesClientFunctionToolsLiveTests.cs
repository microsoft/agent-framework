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
/// Live integration tests for client-provided function tools passed through OpenAI Responses hosting.
/// </summary>
public sealed class OpenAIResponsesClientFunctionToolsLiveTests
{
    private const string ClientRequestJson = """
        {
          "input": "Call get_weather for Valencia. Do not answer without calling the function.",
          "tools": [
            {
              "type": "function",
              "name": "get_weather",
              "description": "Return weather from the client application.",
              "parameters": {
                "type": "object",
                "properties": {
                  "location": { "type": "string" }
                },
                "required": [ "location" ],
                "additionalProperties": false
              },
              "strict": true
            }
          ]
        }
        """;

    private static string? ApiKey => Environment.GetEnvironmentVariable(TestSettings.OpenAIApiKey);

    private static string ModelName =>
        Environment.GetEnvironmentVariable(TestSettings.OpenAIChatModelName) ?? "gpt-4o-mini";

    [Fact]
    public async Task ClientFunctionNameConflictPolicies_WorkEndToEndAsync()
    {
        // Arrange
        Assert.SkipWhen(
            string.IsNullOrEmpty(ApiKey),
            "OPENAI_API_KEY is not configured; skipping live client function tool test.");

        (ChatClientAgent rejectAgent, _) = CreateAgent();
        (ChatClientAgent ignoreAgent, Func<int> getIgnoreInvocationCount) = CreateAgent();
        (ChatClientAgent overrideAgent, Func<int> getOverrideInvocationCount) = CreateAgent();
        JsonElement requestBody = ParseBody(ClientRequestJson);

        // Act & Assert: Reject blocks the conflicting client declaration before inference.
        Assert.Throws<NotSupportedException>(() =>
            OpenAIResponses.ToAgentRunRequest(
                requestBody,
                rejectAgent,
                CreateMapOptions(OpenAIClientFunctionToolNameConflictBehavior.Reject())));

        // Act & Assert: Ignore keeps and executes the hosted function.
        OpenAIResponsesRunRequest ignoreRun = OpenAIResponses.ToAgentRunRequest(
            requestBody,
            ignoreAgent,
            CreateMapOptions(OpenAIClientFunctionToolNameConflictBehavior.Ignore()));
        AgentResponse ignoreResponse = await ignoreAgent.RunAsync(ignoreRun.Messages, options: ignoreRun.Options);
        Assert.True(getIgnoreInvocationCount() > 0);
        Assert.Contains("HOSTED_FUNCTION_RESULT", ignoreResponse.Text, StringComparison.Ordinal);

        // Act & Assert: AllowOverride returns the client function call without executing the hosted function.
        OpenAIResponsesRunRequest overrideRun = OpenAIResponses.ToAgentRunRequest(
            requestBody,
            overrideAgent,
            CreateMapOptions(OpenAIClientFunctionToolNameConflictBehavior.AllowOverride()));
        AgentResponse overrideResponse = await overrideAgent.RunAsync(
            overrideRun.Messages,
            options: overrideRun.Options);
        Assert.Equal(0, getOverrideInvocationCount());
        FunctionCallContent functionCall = Assert.Single(
            overrideResponse.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>());
        Assert.Equal("get_weather", functionCall.Name);
    }

    private static (ChatClientAgent Agent, Func<int> GetInvocationCount) CreateAgent()
    {
        int invocationCount = 0;
        var agent = new ChatClientAgent(
            new OpenAIClient(ApiKey).GetResponsesClient().AsIChatClient(ModelName),
            instructions: """
                For every weather request, call get_weather before answering.
                After receiving a function result, include it verbatim in the answer.
                """,
            name: "weather-agent",
            tools: [AIFunctionFactory.Create(GetHostedWeather, name: "get_weather")]);
        return (agent, () => invocationCount);

        string GetHostedWeather(string location)
        {
            invocationCount++;
            return $"HOSTED_FUNCTION_RESULT: {location}=18C";
        }
    }

#pragma warning disable MAAI001
    private static OpenAIResponsesMapOptions CreateMapOptions(
        OpenAIClientFunctionToolNameConflictBehavior behavior) =>
        new()
        {
            DangerouslyAllowClientFunctionTools = new(behavior)
        };
#pragma warning restore MAAI001

    private static JsonElement ParseBody(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }
}
