// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to persist and resume conversations using the Responses API directly.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;

// Create a FoundryAgentClient using environment variable auto-discovery.
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use.
FoundryAgentClient agent = new(
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

// Start a new session for the agent conversation.
AgentSession session = await agent.CreateSessionAsync();

// Run the agent with a new session.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Serialize the session state to a JsonElement, so it can be stored for later use.
JsonElement serializedSession = await agent.SerializeSessionAsync(session);

// Save the serialized session to a temporary file (for demonstration purposes).
string tempFilePath = Path.GetTempFileName();
await File.WriteAllTextAsync(tempFilePath, JsonSerializer.Serialize(serializedSession));

// Load the serialized session from the temporary file (for demonstration purposes).
JsonElement reloadedSerializedSession = JsonElement.Parse(await File.ReadAllTextAsync(tempFilePath))!;

// Deserialize the session state after loading from storage.
AgentSession resumedSession = await agent.DeserializeSessionAsync(reloadedSerializedSession);

// Run the agent again with the resumed session.
Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedSession));
