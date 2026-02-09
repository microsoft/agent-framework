// Copyright (c) Microsoft. All rights reserved.

// Declarative Agents
// Load an agent definition from a YAML file and run it.
// Enables no-code/low-code agent definitions with optional function tools.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/declarative-agents

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

IChatClient chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetChatClient(deploymentName)
    .AsIChatClient();

if (args.Length < 2)
{
    Console.WriteLine("Usage: DeclarativeAgents <yaml-file-path> <prompt>");
    return;
}

var yamlFilePath = args[0];
var prompt = args[1];

if (!File.Exists(yamlFilePath))
{
    Console.WriteLine($"Error: File not found: {yamlFilePath}");
    return;
}

// <declarative_agent>
[Description("Get the weather for a given location.")]
static string GetWeather(
    [Description("The city and state, e.g. San Francisco, CA")] string location,
    [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
    => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

var text = await File.ReadAllTextAsync(yamlFilePath);
var agentFactory = new ChatClientPromptAgentFactory(chatClient, [AIFunctionFactory.Create(GetWeather, "GetWeather")]);
var agent = await agentFactory.CreateFromYamlAsync(text);

Console.WriteLine(await agent!.RunAsync(prompt));
// </declarative_agent>
