// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Steps;

/// <summary>
/// Demonstrates how to use telemetry with <see cref="ChatClientAgent"/> using OpenTelemetry.
/// </summary>
public sealed class Step06_ChatClientAgent_StructuredOutputs(ITestOutputHelper output) : AgentSample(output)
{
    /// <summary>
    /// Demonstrates OpenTelemetry tracing with Agent Framework.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task RunWithTelemetry(ChatClientProviders provider)
    {
        var jsonSchema = """
        {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The full name of the person."
                },
                "age": {
                    "type": "integer",
                    "description": "The age of the person in years."
                },
                "occupation": {
                    "type": "string",
                    "description": "The primary occupation or job title of the person."
                }
            },
            "required": ["name", "age", "occupation"]
        }
        """;

        var agentOptions = new ChatClientAgentOptions(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");
        agentOptions.ChatOptions = new()
        {
            ResponseFormat = ChatResponseFormatJson.ForJsonSchema(JsonDocument.Parse(jsonSchema).RootElement, "PersonInformation", "Information about a person including their name, age, and occupation")
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        using var chatClient = base.GetChatClient(provider, agentOptions);

        ChatClientAgent agent = new(chatClient, agentOptions);

        var thread = agent.GetNewThread();

        // Prompt which allows to verify that the data was processed from file correctly and current datetime is returned.
        const string Prompt = "Please provide information about John Smith, who is a 35-year-old software engineer.";

        var assistantOutput = new StringBuilder();
        var codeInterpreterOutput = new StringBuilder();

        var updates = agent.RunStreamingAsync(Prompt, thread);
        var agentResponse = await updates.ToAgentRunResponseAsync();

        var personInfo = agentResponse.Deserialize<PersonInfo>(JsonSerializerOptions.Web);

        Console.WriteLine("Assistant Output:");
        Console.WriteLine($"Name: {personInfo.Name}");
        Console.WriteLine($"Age: {personInfo.Age}");
        Console.WriteLine($"Occupation: {personInfo.Occupation}");

        // Clean up the server-side agent after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }

    public class PersonInfo
    {
        [JsonPropertyName("name")]
        public string? Name { get; set; }

        [JsonPropertyName("age")]
        public int? Age { get; set; }

        [JsonPropertyName("occupation")]
        public string? Occupation { get; set; }
    }
}
