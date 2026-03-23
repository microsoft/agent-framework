// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an Microsoft Foundry Agents AI agent as a function tool.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string WeatherInstructions = "You answer questions about the weather.";
const string WeatherName = "WeatherAgent";
const string MainInstructions = "You are a helpful assistant who responds in French.";
const string MainName = "MainAgent";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the weather agent with function tools.
AITool weatherTool = AIFunctionFactory.Create(GetWeather);
PromptAgentDefinition weatherAgentDefinition = new(model: deploymentName)
{
    Instructions = WeatherInstructions,
    Tools = { weatherTool.GetService<ResponseTool>() ?? weatherTool.AsOpenAIResponseTool() ?? throw new InvalidOperationException("Unable to convert weather tool to a ResponseTool.") }
};
AgentVersion weatherAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(WeatherName, new AgentVersionCreationOptions(weatherAgentDefinition));
ChatClientAgent weatherAgent = aiProjectClient.AsAIAgent(weatherAgentVersion, [weatherTool]);

// Create the main agent, and provide the weather agent as a function tool.
AITool weatherAgentTool = weatherAgent.AsAIFunction();
PromptAgentDefinition mainAgentDefinition = new(model: deploymentName)
{
    Instructions = MainInstructions,
    Tools = { weatherAgentTool.GetService<ResponseTool>() ?? weatherAgentTool.AsOpenAIResponseTool() ?? throw new InvalidOperationException("Unable to convert weather agent tool to a ResponseTool.") }
};
AgentVersion mainAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(MainName, new AgentVersionCreationOptions(mainAgentDefinition));
ChatClientAgent agent = aiProjectClient.AsAIAgent(mainAgentVersion, [weatherAgentTool]);

// Invoke the agent and output the text result.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?", session));

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
await aiProjectClient.Agents.DeleteAgentAsync(weatherAgent.Name);
