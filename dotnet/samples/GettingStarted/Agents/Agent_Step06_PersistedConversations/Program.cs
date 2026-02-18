// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1869 // Cache and reuse 'JsonSerializerOptions' instances

// This sample shows how to create and use a simple AI agent with a conversation that can be persisted to disk.

using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create the agent
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

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
