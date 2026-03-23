// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use function tools.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AssistantInstructions = "You are a helpful assistant that can get weather information.";
const string AssistantName = "WeatherAssistant";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Define the agent with function tools.
AITool tool = AIFunctionFactory.Create(GetWeather);
BinaryData toolParameters = BinaryData.FromString(
    """
    {
      "type": "object",
      "properties": {
        "location": {
          "type": "string",
          "description": "The location to get the weather for."
        }
      },
      "required": ["location"],
      "additionalProperties": false
    }
    """);

// Create a server-side agent version and then wrap it as a ChatClientAgent.
AgentVersion newAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    AssistantName,
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = AssistantInstructions,
            Tools = { ResponseTool.CreateFunctionTool(nameof(GetWeather), toolParameters, strictModeEnabled: false, functionDescription: "Get the weather for a given location.") }
        }));
ChatClientAgent newAgent = aiProjectClient.AsAIAgent(newAgentVersion, tools: [tool]);

// Getting an already existing agent by name with tools.
/* 
 * IMPORTANT: Since agents that are stored in the server only know the definition of the function tools (JSON Schema),
 * you need to provided all invocable function tools when retrieving the agent so it can invoke them automatically.
 * If no invocable tools are provided, the function calling needs to handled manually.
 */
AgentRecord existingAgentRecord = await aiProjectClient.Agents.GetAgentAsync(AssistantName);
ChatClientAgent existingAgent = aiProjectClient.AsAIAgent(existingAgentRecord, tools: [tool]);

AgentSession session = await existingAgent.CreateSessionAsync();
Console.WriteLine(await existingAgent.RunAsync("What is the weather like in Amsterdam?", session));

// Streaming agent interaction with function tools.
session = await existingAgent.CreateSessionAsync();
await foreach (AgentResponseUpdate update in existingAgent.RunStreamingAsync("What is the weather like in Amsterdam?", session))
{
    Console.WriteLine(update);
}

// Cleanup by agent removes the agent.
await aiProjectClient.Agents.DeleteAgentAsync(existingAgent.Name);
