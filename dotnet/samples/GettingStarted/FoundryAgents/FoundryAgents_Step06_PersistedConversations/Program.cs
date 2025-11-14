// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a conversation that can be persisted to disk.

using System.Text.Json;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

AIAgent agent = await aiProjectClient.CreateAIAgentAsync(name: JokerName, model: deploymentName, instructions: JokerInstructions);

// Start a new thread for the agent conversation.
AgentThread thread = agent.GetNewThread();

// Run the agent with a new thread.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

// Serialize the thread state to a JsonElement, so it can be stored for later use.
JsonElement serializedThread = thread.Serialize();

// Save the serialized thread to a temporary file (for demonstration purposes).
string tempFilePath = Path.GetTempFileName();
await File.WriteAllTextAsync(tempFilePath, JsonSerializer.Serialize(serializedThread));

// Load the serialized thread from the temporary file (for demonstration purposes).
JsonElement reloadedSerializedThread = JsonSerializer.Deserialize<JsonElement>(await File.ReadAllTextAsync(tempFilePath))!;

// Deserialize the thread state after loading from storage.
AgentThread resumedThread = agent.DeserializeThread(reloadedSerializedThread);

// Run the agent again with the resumed thread.
Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
