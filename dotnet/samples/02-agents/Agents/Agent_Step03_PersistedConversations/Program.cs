// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

// Persisted Conversations — Save and restore chat history to disk
//
// This sample shows how to persist an agent conversation to disk
// so it can be resumed across process restarts.

using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// Create the agent
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .AsAIAgent(model: deploymentName, instructions: "You are good at telling jokes.", name: "Joker");

// Start a new session for the agent conversation.
AgentSession session = await agent.CreateSessionAsync();

// Run the agent with a new session.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Serialize the session state to a JsonElement, so it can be stored for later use.
JsonElement serializedSession = await agent.SerializeSessionAsync(session);

// In a real application, you would typically write the serialized session to a file or
// database for persistence, and read it back when resuming the conversation.
// Here we'll just write the serialized session to console (for demonstration purposes).
Console.WriteLine("\n--- Serialized session ---\n");
Console.WriteLine(JsonSerializer.Serialize(serializedSession, new JsonSerializerOptions { WriteIndented = true }) + "\n");

// Deserialize the session state after loading from storage.
AgentSession resumedSession = await agent.DeserializeSessionAsync(serializedSession);

// Run the agent again with the resumed session.
Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedSession));
