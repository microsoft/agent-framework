// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a conversation that can be persisted to disk.

using System;
using System.IO;
using System.Text.Json;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAIDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

// Create the agent
AIAgent agent = new AzureOpenAIClient(
    new Uri(azureOpenAIEndpoint),
    new AzureCliCredential())
     .GetChatClient(azureOpenAIDeploymentName)
     .CreateAIAgent(JokerInstructions, JokerName);

// Start a new thread for the agent conversation.
AgentThread thread = agent.GetNewThread();

Console.WriteLine("--- Run the agent (context preserved) ---\n");

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

// Serialize the thread state to a JsonElement, so it can be stored for later use.
JsonElement serializedThread = await thread.SerializeAsync();

// Save the serialized thread to a temporary file (for demonstration purposes).
string tempFilePath = Path.GetTempFileName();
await File.WriteAllTextAsync(tempFilePath, JsonSerializer.Serialize(serializedThread));

Console.WriteLine("\n--- Resume the conversation (with previously stored context) ---\n");

// Load the serialized thread from the temporary file (for demonstration purposes).
JsonElement reloadedSerializedThread = JsonSerializer.Deserialize<JsonElement>(await File.ReadAllTextAsync(tempFilePath));

// Deserialize the thread state after loading from storage.
AgentThread resumedThread = await agent.DeserializeThreadAsync(reloadedSerializedThread);

Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));
