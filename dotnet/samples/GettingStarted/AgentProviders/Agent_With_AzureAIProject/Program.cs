// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a AI agents with Azure Foundry Agents as the backend.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
var aiProjectClient = new AIProjectClient(new Uri(endpoint), new AzureCliCredential());

// Define the agent you want to create. (Prompt Agent in this case)
var agentVersionCreationOptions = new AgentVersionCreationOptions(new PromptAgentDefinition(model: deploymentName) { Instructions = "You are good at telling jokes." });
// Azure.AI.Agents SDK creates and manages agent by name and versions.
// You can create a server side agent version with the Azure.AI.Agents SDK client below.
var createdAgentVersion = aiProjectClient.Agents.CreateAgentVersion(agentName: JokerName, options: agentVersionCreationOptions);

// Note:
//      agentVersion.Id = "<agentName>:<versionNumber>",
//      agentVersion.Version = <versionNumber>,
//      agentVersion.Name = <agentName>

// You can retrieve an AIAgent for an already created server side agent version.
AIAgent existingJokerAgent = aiProjectClient.GetAIAgent(createdAgentVersion);

// You can also create another AIAgent version by providing the same name with a different definition.
AIAgent newJokerAgent = aiProjectClient.CreateAIAgent(name: JokerName, model: deploymentName, instructions: "You are extremely hilarious at telling jokes.");

// You can also get the AIAgent latest version just providing its name.
AIAgent jokerAgentLatest = aiProjectClient.GetAIAgent(name: JokerName);
var latestAgentVersion = jokerAgentLatest.GetService<AgentVersion>()!;

// The AIAgent version can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestAgentVersion.Id}");

// Once you have the AIAgent, you can invoke it like any other AIAgent.
AgentThread thread = jokerAgentLatest.GetNewThread();
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate.", thread));

// This will use the same thread to continue the conversation.
Console.WriteLine(await jokerAgentLatest.RunAsync("Now tell me a joke about a cat and a dog using last joke as the anchor.", thread));

// Cleanup by agent name removes both agent versions created.
aiProjectClient.Agents.DeleteAgent(existingJokerAgent.Name);
