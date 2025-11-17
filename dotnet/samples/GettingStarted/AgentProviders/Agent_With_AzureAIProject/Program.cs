// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a AI agents with Azure Foundry Agents as the backend.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
var aiProjectClient = new AIProjectClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create. (Prompt Agent in this case)
var agentVersionCreationOptions = new AgentVersionCreationOptions(new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions });
// Azure.AI.Agents SDK creates and manages agent by name and versions.
// You can create a server side agent version with the Azure.AI.Agents SDK client below.
var agentVersion = aiProjectClient.Agents.CreateAgentVersion(agentName: JokerName, options: agentVersionCreationOptions);

// Note:
//      agentVersion.Id = "<agentName>:<versionNumber>",
//      agentVersion.Version = <versionNumber>,
//      agentVersion.Name = <agentName>

// You can retrieve an AIAgent for a already created server side agent version.
AIAgent jokerAgentV1 = aiProjectClient.GetAIAgent(agentVersion);

// You can also create another AIAgent version (V2) by providing the same name with a different definition.
AIAgent jokerAgentV2 = aiProjectClient.CreateAIAgent(name: JokerName, model: deploymentName, instructions: JokerInstructions + "V2");

// You can also get the AIAgent latest version just providing its name.
AIAgent jokerAgentLatest = aiProjectClient.GetAIAgent(name: JokerName);
var latestVersion = jokerAgentLatest.GetService<AgentVersion>()!;

// The AIAgent version can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestVersion.Id}");

// Once you have the AIAgent, you can invoke it like any other AIAgent.
AgentThread thread = jokerAgentLatest.GetNewThread();
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate.", thread));

// This will use the same thread to continue the conversation.
Console.WriteLine(await jokerAgentLatest.RunAsync("Now tell me a joke about a cat and a dog using last joke as the anchor.", thread));

// Cleanup by agent name removes both agent versions created (jokerAgentV1 + jokerAgentV2).
aiProjectClient.Agents.DeleteAgent(jokerAgentV1.Name);
