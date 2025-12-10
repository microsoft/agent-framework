// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create. (Prompt Agent in this case)
AgentVersionCreationOptions options = new(new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions });

// Create a server side agent version with the Azure.AI.Agents SDK client.
AgentVersion agentVersion = aiProjectClient.Agents.CreateAgentVersion(agentName: JokerName, options);

// Retrieve an AIAgent for the created server side agent version.
AIAgent jokerAgent = aiProjectClient.GetAIAgent(agentVersion);

// Invoke the agent with a multi-turn conversation, where the context is preserved in the thread object.
AgentThread thread = jokerAgent.GetNewThread();
Console.WriteLine(await jokerAgent.RunAsync("Tell me a joke about a pirate.", thread));
Console.WriteLine(await jokerAgent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the thread object.
thread = jokerAgent.GetNewThread();
await foreach (AgentRunResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate.", thread))
{
    Console.WriteLine(update);
}
await foreach (AgentRunResponseUpdate update in jokerAgent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", thread))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(jokerAgent.Name);
