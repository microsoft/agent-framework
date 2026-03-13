// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a conversation that can be persisted to disk.

using System.Text.Json;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    JokerName,
    new AgentVersionCreationOptions(new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions }));
ChatClientAgent agent = aiProjectClient.AsAIAgent(agentVersion);

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

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
