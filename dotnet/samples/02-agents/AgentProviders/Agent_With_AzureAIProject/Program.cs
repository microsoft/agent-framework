// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a AI agents with Azure Foundry Agents as the backend.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var aiProjectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());

// Define the agent you want to create. (Prompt Agent in this case)
var agentVersionCreationOptions = new AgentVersionCreationOptions(new PromptAgentDefinition(model: deploymentName) { Instructions = "You are good at telling jokes." });
// Azure.AI.Agents SDK creates and manages agent by name and versions.
// You can create a server side agent version with the Azure.AI.Agents SDK client below.
var createdAgentVersion = aiProjectClient.Agents.CreateAgentVersion(agentName: JokerName, options: agentVersionCreationOptions);

// Note:
//      agentVersion.Id = "<agentName>:<versionNumber>",
//      agentVersion.Version = <versionNumber>,
//      agentVersion.Name = <agentName>

// You can use an AIAgent with an already created server side agent version.
FoundryAgent existingJokerAgent = aiProjectClient.AsAIAgent(createdAgentVersion);

// You can also create another AIAgent version by providing the same name with a different definition.
AgentVersion newJokerAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    JokerName,
    new AgentVersionCreationOptions(new PromptAgentDefinition(model: deploymentName) { Instructions = "You are extremely hilarious at telling jokes." }));
FoundryAgent newJokerAgent = aiProjectClient.AsAIAgent(newJokerAgentVersion);

// You can also get the AIAgent latest version just providing its name.
AgentRecord jokerAgentRecord = await aiProjectClient.Agents.GetAgentAsync(JokerName);
FoundryAgent jokerAgentLatest = aiProjectClient.AsAIAgent(jokerAgentRecord);
AgentVersion latestAgentVersion = jokerAgentRecord.GetLatestVersion();

// The AIAgent version can be accessed via the GetService method.
Console.WriteLine($"Latest agent version id: {latestAgentVersion.Id}");

// Once you have the AIAgent, you can invoke it like any other AIAgent.
AgentSession session = await jokerAgentLatest.CreateSessionAsync();
Console.WriteLine(await jokerAgentLatest.RunAsync("Tell me a joke about a pirate.", session));

// This will use the same session to continue the conversation.
Console.WriteLine(await jokerAgentLatest.RunAsync("Now tell me a joke about a cat and a dog using last joke as the anchor.", session));

// Cleanup by agent name removes both agent versions created.
aiProjectClient.Agents.DeleteAgent(existingJokerAgent.Name);
