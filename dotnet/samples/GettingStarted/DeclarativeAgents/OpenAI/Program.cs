// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load an AI agent from a YAML file and process a prompt using OpenAI as the backend.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_APIKEY") ?? throw new InvalidOperationException("OPENAI_APIKEY is not set.");

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

// Set up configuration with the OpenAI API key
IConfiguration configuration = new ConfigurationBuilder()
    .AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["OPENAI_APIKEY"] = apiKey
    })
    .Build();

// Create the agent from the YAML definition.
var agentFactory = new AggregatorAgentFactory(
    [
        new OpenAIChatAgentFactory(configuration: configuration),
        new OpenAIResponseAgentFactory(configuration: configuration),
        new OpenAIAssistantAgentFactory(configuration: configuration)
    ]);
var agent = await agentFactory.CreateFromYamlAsync(text);

// Example function tool that can be used by the agent.
[Description("Get the weather for a given location.")]
static string GetWeather(
    [Description("The city and state, e.g. San Francisco, CA")] string location,
    [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
    => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";

// Create agent run options
var options = new ChatClientAgentRunOptions(new()
{
    Tools = [AIFunctionFactory.Create(GetWeather, name: nameof(GetWeather))]
});

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(prompt, options: options));
