// Copyright (c) Microsoft. All rights reserved.

// Step 2: Add Tools
// Give your agent the ability to call functions (tools) to retrieve external data.
// This sample adds a weather function tool and demonstrates automatic tool invocation.
//
// For tools deep dive, see: ../02-agents/tools/
// For docs: https://learn.microsoft.com/agent-framework/agents/tools

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// <define_tool>
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";
// </define_tool>

// <create_agent_with_tools>
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

AITool tool = AIFunctionFactory.Create(GetWeather);
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "WeatherAssistant",
    model: deploymentName,
    instructions: "You are a helpful assistant that can get weather information.",
    tools: [tool]);
// </create_agent_with_tools>

// <invoke_with_tools>
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));
// </invoke_with_tools>

// Streaming with tools
session = await agent.CreateSessionAsync();
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("What is the weather like in Amsterdam?", session))
{
    Console.Write(update);
}
Console.WriteLine();

// Cleanup
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
