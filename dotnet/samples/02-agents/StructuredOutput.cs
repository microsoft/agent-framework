// Copyright (c) Microsoft. All rights reserved.

// Structured Output
// Configure an agent to produce structured (typed) JSON output.
// Demonstrates both RunAsync<T> and streaming with deserialization.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/structured-output

using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using SampleApp;

#pragma warning disable CA5399

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// <structured_output>
ChatClientAgent agent = await aiProjectClient.CreateAIAgentAsync(
    model: deploymentName,
    new ChatClientAgentOptions()
    {
        Name = "StructuredOutputAssistant",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant that extracts structured information about people.",
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>()
        }
    });

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>(
    "Please provide information about John Smith, who is a 35-year-old software engineer.");

Console.WriteLine($"Name: {response.Result.Name}");
Console.WriteLine($"Age: {response.Result.Age}");
Console.WriteLine($"Occupation: {response.Result.Occupation}");
// </structured_output>

// <structured_output_streaming>
IAsyncEnumerable<AgentResponseUpdate> updates = agent.RunStreamingAsync(
    "Please provide information about Jane Doe, who is a 28-year-old data scientist.");

PersonInfo personInfo = (await updates.ToAgentResponseAsync()).Deserialize<PersonInfo>(JsonSerializerOptions.Web);
Console.WriteLine($"Name: {personInfo.Name}, Age: {personInfo.Age}, Occupation: {personInfo.Occupation}");
// </structured_output_streaming>

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);

namespace SampleApp
{
    [Description("Information about a person including their name, age, and occupation")]
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
