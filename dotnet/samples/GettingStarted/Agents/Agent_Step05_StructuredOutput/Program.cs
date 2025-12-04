// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to configure ChatClientAgent to produce structured output.

using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI;
using OpenAI.Chat;
using SampleApp;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create chat client to be used by chat client agents.
ChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
        .GetChatClient(deploymentName);

// Create the ChatClientAgent with the specified name and instructions.
ChatClientAgent agent = chatClient.CreateAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

// Set PersonInfo as the type parameter of RunAsync method to specify the expected structured output from the agent and invoke the agent with some unstructured input.
AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Access the structured output via the Result property of the agent response.
Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {response.Result.Name}");
Console.WriteLine($"Age: {response.Result.Age}");
Console.WriteLine($"Occupation: {response.Result.Occupation}");

// Create the ChatClientAgent with the specified name, instructions, and expected structured output the agent should produce.
ChatClientAgent agentWithPersonInfo = chatClient.CreateAIAgent(new ChatClientAgentOptions()
{
    Name = "HelpfulAssistant",
    ChatOptions = new() { Instructions = "You are a helpful assistant.", ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<PersonInfo>() }
});

// Invoke the agent with some unstructured input while streaming, to extract the structured information from.
var updates = agentWithPersonInfo.RunStreamingAsync("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Assemble all the parts of the streamed output, since we can only deserialize once we have the full json,
// then deserialize the response into the PersonInfo class.
PersonInfo personInfo = (await updates.ToAgentRunResponseAsync()).Deserialize<PersonInfo>(JsonSerializerOptions.Web);

Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

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
