// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to configure an agent to produce structured output.

using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;
using SampleApp;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AssistantInstructions = "You are a helpful assistant that extracts structured information about people.";
const string AssistantName = "StructuredOutputAssistant";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());
AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    AssistantName,
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(model: deploymentName)
        {
            Instructions = AssistantInstructions
        }));
FoundryAgent agent = aiProjectClient.AsAIAgent(agentVersion);
ChatClientAgentRunOptions runOptions = new(
    new ChatOptions
    {
        ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>()
    });

// Set PersonInfo as the type parameter of RunAsync method to specify the expected structured output from the agent and invoke the agent with some unstructured input.
AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>(
    "Please provide information about John Smith, who is a 35-year-old software engineer.",
    session: null,
    serializerOptions: JsonSerializerOptions.Web,
    options: runOptions);

// Access the structured output via the Result property of the agent response.
Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {response.Result.Name}");
Console.WriteLine($"Age: {response.Result.Age}");
Console.WriteLine($"Occupation: {response.Result.Occupation}");

// Invoke the agent with some unstructured input while streaming, to extract the structured information from.
IAsyncEnumerable<AgentResponseUpdate> updates = agent.RunStreamingAsync(
    "Please provide information about John Smith, who is a 35-year-old software engineer.",
    session: null,
    options: runOptions);

// Assemble all the parts of the streamed output, since we can only deserialize once we have the full json,
// then deserialize the response into the PersonInfo class.
PersonInfo personInfo = JsonSerializer.Deserialize<PersonInfo>((await updates.ToAgentResponseAsync()).Text, JsonSerializerOptions.Web)
    ?? throw new InvalidOperationException("Failed to deserialize the streamed response into PersonInfo.");

Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

// Cleanup: deletes the agent and all its versions.
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
