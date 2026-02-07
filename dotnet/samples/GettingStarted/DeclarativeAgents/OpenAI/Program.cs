// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load an AI agent from a YAML file and process a prompt using Azure OpenAI as the backend.
// Unlike the ChatClient sample, this uses the OpenAIPromptAgentFactory which can create a ChatClient from the YAML model definition.

using System.ComponentModel;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;

string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");

// Read command-line arguments
if (args.Length < 2)
{
    Console.WriteLine("Usage: DeclarativeOpenAIAgents <yaml-file-path> <prompt>");
    Console.WriteLine("  <yaml-file-path>: The path to the YAML file containing the agent definition");
    Console.WriteLine("  <prompt>: The prompt to send to the agent");
    return;
}

string yamlFilePath = args[0];
string prompt = args[1];

// Verify the YAML file exists
if (!File.Exists(yamlFilePath))
{
    Console.WriteLine($"Error: File not found: {yamlFilePath}");
    return;
}

// Read the YAML content from the file
string text = await File.ReadAllTextAsync(yamlFilePath);

// Example function tool that can be used by the agent.
[Description("Get the weather for a given location.")]
static string GetWeather(
    [Description("The city and state, e.g. San Francisco, CA")] string location,
    [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
    => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

// Create the configuration with the Azure OpenAI endpoint
IConfiguration configuration = new ConfigurationBuilder()
    .AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["AzureOpenAI:Endpoint"] = endpoint,
    })
    .Build();

// Create the agent from the YAML definition.
// OpenAIPromptAgentFactory can create a ChatClient based on the model defined in the YAML file.
OpenAIPromptAgentFactory agentFactory = new(
    new Uri(endpoint),
    new AzureCliCredential(),
    [AIFunctionFactory.Create(GetWeather, "GetWeather")],
    configuration: configuration);
AIAgent? agent = await agentFactory.CreateFromYamlAsync(text);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(prompt));
