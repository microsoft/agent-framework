// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load an AI agent from a YAML file and process a prompt using Azure OpenAI as the backend.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the chat client
IChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
     .GetChatClient(deploymentName)
     .AsIChatClient();

// Read command-line arguments
if (args.Length < 2)
{
    Console.WriteLine("Usage: DeclarativeAgents <yaml-file-path> <prompt>");
    Console.WriteLine("  <yaml-file-path>: The path to the YAML file containing the agent definition");
    Console.WriteLine("  <prompt>: The prompt to send to the agent");
    return;
}

var yamlFilePath = args[0];
var prompt = args[1];

// Verify the YAML file exists
if (!File.Exists(yamlFilePath))
{
    Console.WriteLine($"Error: File not found: {yamlFilePath}");
    return;
}

// Read the YAML content from the file
var text = await File.ReadAllTextAsync(yamlFilePath);

// Example function tool that can be used by the agent.
[Description("Get the weather for a given location.")]
static string GetWeather(
    [Description("The city and state, e.g. San Francisco, CA")] string location,
    [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
    => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

// Create the agent from the YAML definition.
var agentFactory = new ChatClientPromptAgentFactory(chatClient, [AIFunctionFactory.Create(GetWeather, "GetWeather")]);
var agent = await agentFactory.CreateFromYamlAsync(text);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(prompt));
