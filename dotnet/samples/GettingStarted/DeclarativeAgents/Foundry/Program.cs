// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load an AI agent from a YAML file and process a prompt using Foundry Agents as the backend.

using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.Configuration;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");

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

// Set up configuration with the Azure Foundry project endpoint
IConfiguration configuration = new ConfigurationBuilder()
    .AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["AZURE_FOUNDRY_PROJECT_ENDPOINT"] = endpoint
    })
    .Build();

// Create the agent from the YAML definition.
var agentFactory = new FoundryAgentFactory(new AzureCliCredential(), configuration);
var agent = await agentFactory.CreateFromYamlAsync(text);

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(prompt));
