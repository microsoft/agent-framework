// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to configure an agent to produce structured output.

using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using SampleApp;

#pragma warning disable CA5399

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AIAgent agent = aiProjectClient.AsAIAgent(new ChatClientAgentOptions
{
    Name = "StructuredOutputAssistant",
    ChatOptions = new()
    {
        ModelId = deploymentName,
        Instructions = "You are a helpful assistant that extracts structured information about people.",
        ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>()
    }
});

// Set PersonInfo as the type parameter of RunAsync method to specify the expected structured output.
AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Access the structured output via the Result property of the agent response.
Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {response.Result.Name}");
Console.WriteLine($"Age: {response.Result.Age}");
Console.WriteLine($"Occupation: {response.Result.Occupation}");

// Invoke the agent with streaming support, then deserialize the assembled response.
IAsyncEnumerable<AgentResponseUpdate> updates = agent.RunStreamingAsync("Please provide information about Jane Doe, who is a 28-year-old data scientist.");

PersonInfo personInfo = JsonSerializer.Deserialize<PersonInfo>((await updates.ToAgentResponseAsync()).Text, JsonSerializerOptions.Web)
    ?? throw new InvalidOperationException("Failed to deserialize the streamed response into PersonInfo.");

Console.WriteLine("\nStreaming Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

namespace SampleApp
{
    /// <summary>
    /// Represents information about a person.
    /// </summary>
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
