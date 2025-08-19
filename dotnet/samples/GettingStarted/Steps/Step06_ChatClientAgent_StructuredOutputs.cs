// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Steps;

/// <summary>
/// Demonstrates how to use structured outputs with <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class Step06_ChatClientAgent_StructuredOutputs(ITestOutputHelper output) : AgentSample(output)
{
    /// <summary>
    /// Demonstrates processing structured outputs using JSON schemas to extract information about a person.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task RunWithCustomSchema(ChatClientProviders provider)
    {
        var agentOptions = new ChatClientAgentOptions(name: "HelpfulAssistant", instructions: "You are a helpful assistant.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormatJson.ForJsonSchema(
                    schema: AIJsonUtilities.CreateJsonSchema(typeof(PersonInfo)),
                    schemaName: "PersonInfo",
                    schemaDescription: "Information about a person including their name, age, and occupation"
                )
            }
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        using var chatClient = base.GetChatClient(provider, agentOptions);

        ChatClientAgent agent = new(chatClient, agentOptions);

        var thread = agent.GetNewThread();

        const string Prompt = "Please provide information about John Smith, who is a 35-year-old software engineer.";

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

    /// <summary>
    /// Represents information about a person, including their name, age, and occupation, matched to the JSON schema used in the agent.
    /// </summary>
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
