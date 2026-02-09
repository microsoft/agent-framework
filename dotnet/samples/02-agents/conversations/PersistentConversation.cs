// Copyright (c) Microsoft. All rights reserved.

// Persisted Conversations
// Serialize and deserialize agent sessions so conversations can be saved and resumed.
// Works with both Azure AI Foundry and ChatClient-based agents.
//
// For docs: https://learn.microsoft.com/agent-framework/agents/conversations

using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(name: "JokerAgent", model: deploymentName, instructions: "You are good at telling jokes.");

// <persist_session>
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Serialize the session state for storage
JsonElement serializedSession = agent.SerializeSession(session);

// Save to file (or database, etc.)
string tempFilePath = Path.GetTempFileName();
await File.WriteAllTextAsync(tempFilePath, JsonSerializer.Serialize(serializedSession));
// </persist_session>

// <resume_session>
// Later: Load and resume the session
JsonElement reloadedSession = JsonElement.Parse(await File.ReadAllTextAsync(tempFilePath))!;
AgentSession resumedSession = await agent.DeserializeSessionAsync(reloadedSession);

Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis.", resumedSession));
// </resume_session>

await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
