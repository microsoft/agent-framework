// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load an AI agent from a YAML file and process a prompt using Azure OpenAI as the backend.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_APIKEY") ?? throw new InvalidOperationException("OPENAI_APIKEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

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

// TODO: Remove this workaround when the agent framework supports environment variable substitution in YAML files.
text = text.Replace("=Env.OPENAI_APIKEY", apiKey, StringComparison.OrdinalIgnoreCase);
text = text.Replace("=Env.OPENAI_MODEL", model, StringComparison.OrdinalIgnoreCase);

// Example function tool that can be used by the agent.
[Description("Get the weather for a given location.")]
static string GetWeather(
    [Description("The city and state, e.g. San Francisco, CA")] string location,
    [Description("The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.")] string unit)
    => $"The weather in {location} is cloudy with a high of {(unit.Equals("celsius", StringComparison.Ordinal) ? "15°C" : "59°F")}.";
List<AIFunction> functions = [AIFunctionFactory.Create(GetWeather, "GetWeather")];

// Create the agent from the YAML definition.
var agentFactory = new OpenAIChatAgentFactory(functions); // TODO: Aggregate all of the OpenAI agent factories into a single factory.
var agent = await agentFactory.CreateFromYamlAsync(text);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(prompt));
