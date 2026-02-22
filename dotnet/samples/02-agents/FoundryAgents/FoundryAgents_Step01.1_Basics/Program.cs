// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use AI agents with Azure Foundry Agents as the backend.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Define the agent you want to create. (Prompt Agent in this case)
AgentVersionCreationOptions options = new(new PromptAgentDefinition(model: deploymentName) { Instructions = "You are good at telling jokes." });

// Azure.AI.Agents SDK creates and manages agent by name and versions.
// You can create a server side agent version with the Azure.AI.Agents SDK client below.
AgentVersion createdAgentVersion = aiProjectClient.Agents.CreateAgentVersion(agentName: JokerName, options);

// Note:
//      agentVersion.Id = "<agentName>:<versionNumber>",
//      agentVersion.Version = <versionNumber>,
//      agentVersion.Name = <agentName>

// You can use an AIAgent with an already created server side agent version.
AIAgent existingJokerAgent = aiProjectClient.AsAIAgent(createdAgentVersion);

// You can also create another AIAgent version by providing the same name with a different definition/instruction.
AIAgent newJokerAgent = await aiProjectClient.CreateAIAgentAsync(name: JokerName, model: deploymentName, instructions: "You are extremely hilarious at telling jokes.");

// You can also get the AIAgent latest version by just providing its name.
AIAgent jokerAgentLatest = await aiProjectClient.GetAIAgentAsync(name: JokerName);
AgentVersion latestAgentVersion = jokerAgentLatest.GetService<AgentVersion>()!;

// The AIAgent version can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestAgentVersion.Id}");

// Once you have the AIAgent, you can invoke it like any other AIAgent.
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate."));

// Cleanup by agent name removes both agent versions created.
await aiProjectClient.Agents.DeleteAgentAsync(existingJokerAgent.Name);
