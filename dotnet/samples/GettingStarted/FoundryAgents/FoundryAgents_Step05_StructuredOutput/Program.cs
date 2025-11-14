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

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AssistantInstructions = "You are a helpful assistant that extracts structured information about people.";
const string AssistantName = "StructuredOutputAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create ChatClientAgent directly
ChatClientAgent agent = await aiProjectClient.CreateAIAgentAsync(
    model: deploymentName,
    new ChatClientAgentOptions(name: AssistantName, instructions: AssistantInstructions)
    {
        ChatOptions = new()
        {
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>()
        }
    });

// Set PersonInfo as the type parameter of RunAsync method to specify the expected structured output from the agent and invoke the agent with some unstructured input.
AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Access the structured output via the Result property of the agent response.
Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {response.Result.Name}");
Console.WriteLine($"Age: {response.Result.Age}");
Console.WriteLine($"Occupation: {response.Result.Occupation}");

// Create the ChatClientAgent with the specified name, instructions, and expected structured output the agent should produce.
ChatClientAgent agentWithPersonInfo = aiProjectClient.CreateAIAgent(
    model: deploymentName,
    new ChatClientAgentOptions(name: AssistantName, instructions: AssistantInstructions)
    {
        ChatOptions = new()
        {
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>()
        }
    });

// Invoke the agent with some unstructured input while streaming, to extract the structured information from.
IAsyncEnumerable<AgentRunResponseUpdate> updates = agentWithPersonInfo.RunStreamingAsync("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Assemble all the parts of the streamed output, since we can only deserialize once we have the full json,
// then deserialize the response into the PersonInfo class.
PersonInfo personInfo = (await updates.ToAgentRunResponseAsync()).Deserialize<PersonInfo>(JsonSerializerOptions.Web);

Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);

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
