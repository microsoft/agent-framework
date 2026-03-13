// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use versioned AI agents with AIProjectClient.Agents.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "JokerAgent";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a server-side agent version explicitly.
AgentVersion jokerAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    JokerName,
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = "You are good at telling jokes."
        }));

// You can also create another version by providing the same name with a different instruction.
AgentVersion newJokerAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    JokerName,
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = "You are extremely hilarious at telling jokes."
        }));

// You can also get the latest version by just providing its name.
AgentRecord jokerAgentRecord = await aiProjectClient.Agents.GetAgentAsync(JokerName);
AgentVersion latestAgentVersion = jokerAgentRecord.Versions.Latest;
ChatClientAgent jokerAgentLatest = aiProjectClient.AsAIAgent(jokerAgentRecord);

// The AgentVersion can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestAgentVersion.Id}");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate."));

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(JokerName);
