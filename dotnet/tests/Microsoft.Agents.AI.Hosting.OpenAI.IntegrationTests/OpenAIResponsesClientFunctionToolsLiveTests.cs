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
    public async Task AllowedClientFunction_ReturnsFunctionCallAsync()
    {
        // Arrange
        Assert.SkipWhen(
            string.IsNullOrEmpty(ApiKey),
            "OPENAI_API_KEY is not configured; skipping live client function tool test.");

        using IChatClient chatClient = new OpenAIClient(ApiKey).GetResponsesClient().AsIChatClient(ModelName);
        var agent = new ChatClientAgent(
            chatClient,
            instructions: "For every weather request, call get_weather before answering.",
            name: "weather-agent");
        JsonElement requestBody = ParseBody(ClientRequestJson);
#pragma warning disable MAAI001
        var mapOptions = new OpenAIResponsesMapOptions { DangerouslyAllowClientFunctionTools = true };
#pragma warning restore MAAI001

        // Act
        OpenAIResponsesRunRequest run = OpenAIResponses.ToAgentRunRequest(requestBody, mapOptions);
        AgentResponse response = await agent.RunAsync(run.Messages, options: run.Options);

        // Assert
        FunctionCallContent functionCall = Assert.Single(
            response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>());
        Assert.Equal("get_weather", functionCall.Name);
    }

    private static JsonElement ParseBody(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }
}
