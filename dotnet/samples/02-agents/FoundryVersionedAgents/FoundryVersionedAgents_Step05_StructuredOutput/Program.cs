// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to configure an agent to produce structured output.

using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using SampleApp;

#pragma warning disable CA5399

const string AssistantInstructions = "You are a helpful assistant that extracts structured information about people.";
const string AssistantName = "StructuredOutputAssistant";

// Create FoundryVersionedAgent directly
FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(
    new ChatClientAgentOptions()
    {
        Name = AssistantName,
        ChatOptions = new()
        {
            Instructions = AssistantInstructions,
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>()
        }
    });

// Set PersonInfo as the type parameter of RunAsync method to specify the expected structured output from the agent and invoke the agent with some unstructured input.
AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Access the structured output via the Result property of the agent response.
Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {response.Result.Name}");
Console.WriteLine($"Age: {response.Result.Age}");
Console.WriteLine($"Occupation: {response.Result.Occupation}");

// Create the FoundryVersionedAgent with the specified name, instructions, and expected structured output the agent should produce.
FoundryVersionedAgent agentWithPersonInfo = await FoundryVersionedAgent.CreateAIAgentAsync(
    new ChatClientAgentOptions()
    {
        Name = AssistantName,
        ChatOptions = new()
        {
            Instructions = AssistantInstructions,
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>()
        }
    });

// Invoke the agent with some unstructured input while streaming, to extract the structured information from.
IAsyncEnumerable<AgentResponseUpdate> updates = agentWithPersonInfo.RunStreamingAsync("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Assemble all the parts of the streamed output, since we can only deserialize once we have the full json,
// then deserialize the response into the PersonInfo class.
PersonInfo personInfo = JsonSerializer.Deserialize<PersonInfo>((await updates.ToAgentResponseAsync()).Text, JsonSerializerOptions.Web)
    ?? throw new InvalidOperationException("Failed to deserialize the streamed response into PersonInfo.");

Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

// Cleanup by agent name removes the agent version created.
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);

namespace SampleApp
{
    /// <summary>
    /// Represents information about a person, including their name, age, and occupation, matched to the JSON schema used in the agent.
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
