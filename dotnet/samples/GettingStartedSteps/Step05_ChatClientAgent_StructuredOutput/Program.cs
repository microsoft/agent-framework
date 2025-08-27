// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend, to produce structured output using JSON schema from a class.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI;
using SampleApp;

var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAIDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the agent options, specifying the response format to use a JSON schema based on the PersonInfo class.
ChatClientAgentOptions agentOptions = new(name: "HelpfulAssistant", instructions: "You are a helpful assistant.")
{
    ChatOptions = new()
    {
        ResponseFormat = ChatResponseFormatJson.ForJsonSchema(
            schema: AIJsonUtilities.CreateJsonSchema(typeof(PersonInfo)),
            schemaName: "PersonInfo",
            schemaDescription: "Information about a person including their name, age, and occupation")
    }
};

// Create the agent using Azure OpenAI.
AIAgent agent = new AzureOpenAIClient(
    new Uri(azureOpenAIEndpoint),
    new AzureCliCredential())
        .GetChatClient(azureOpenAIDeploymentName)
        .CreateAIAgent(agentOptions);

Console.WriteLine("\n--- Run with structured output ---\n");

// Invoke the agent with some unstructured input, to extract the structured information from.
var response = await agent.RunAsync("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Deserialize the response into the PersonInfo class.
var personInfo = response.Deserialize<PersonInfo>(JsonSerializerOptions.Web);

Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

Console.WriteLine("\n--- Run with structured output and streaming ---\n");

// Invoke the agent with some unstructured input, to extract the structured information from.
var updates = agent.RunStreamingAsync("Please provide information about John Smith, who is a 35-year-old software engineer.");

// Assemble all the parts of the streamed output, since we can only deserialize once we have the full json,
// then deserialize the response into the PersonInfo class.
personInfo = (await updates.ToAgentRunResponseAsync()).Deserialize<PersonInfo>(JsonSerializerOptions.Web);

Console.WriteLine("Assistant Output:");
Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");

namespace SampleApp
{
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
