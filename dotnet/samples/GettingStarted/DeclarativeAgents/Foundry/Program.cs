// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load an AI agent from a YAML file and process a prompt using Azure OpenAI as the backend.

using System.ComponentModel;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4.1-mini";

// Get a client to create/retrieve server side agents with.
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Set up dependency injection to provide the PersistentAgentsClient
var serviceCollection = new ServiceCollection();
serviceCollection.AddTransient((sp) => persistentAgentsClient);
IServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();

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

// Create run options to configure the agent invocation.
var runOptions = new ChatClientAgentRunOptions()
{
    ChatOptions = new()
    {
        RawRepresentationFactory = (_) => new ThreadAndRunOptions()
        {
            ToolResources = new MCPToolResource(serverLabel: "microsoft_learn")
            {
                RequireApproval = new MCPApproval("never"),
            }.ToToolResources()
        }
    }
};

// Create the agent from the YAML definition.
var agentFactory = new ChatClientAgentFactory(); //AzureFoundryAgentFactory();
var agent = await agentFactory.CreateFromYamlAsync(text, new() { Model = model, ServiceProvider = serviceProvider, Tools = [AIFunctionFactory.Create(GetWeather, "GetWeather")] });

// Tools = [AIFunctionFactory.Create(GetWeather, "GetWeather")]

// Invoke the agent and output the text result.
Console.WriteLine(await agent!.RunAsync(prompt));
