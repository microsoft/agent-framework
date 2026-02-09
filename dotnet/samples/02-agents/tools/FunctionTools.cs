// Copyright (c) Microsoft. All rights reserved.

// Function Tools
// Create an agent with function tools for automatic invocation.
// Shows both Azure AI Foundry and Azure OpenAI ChatClient approaches.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <define_function>
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";
// </define_function>

// <create_with_tools>
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

AITool tool = AIFunctionFactory.Create(GetWeather);
var agent = await aiProjectClient.CreateAIAgentAsync(
    name: "WeatherAssistant",
    model: deploymentName,
    instructions: "You are a helpful assistant that can get weather information.",
    tools: [tool]);
// </create_with_tools>

// <retrieve_with_tools>
// When retrieving an existing agent, provide invocable tools so the agent can invoke them automatically.
var existingAgent = await aiProjectClient.GetAIAgentAsync(name: "WeatherAssistant", tools: [tool]);
// </retrieve_with_tools>

AgentSession session = await existingAgent.CreateSessionAsync();
Console.WriteLine(await existingAgent.RunAsync("What is the weather like in Amsterdam?", session));

await aiProjectClient.Agents.DeleteAgentAsync(existingAgent.Name);
