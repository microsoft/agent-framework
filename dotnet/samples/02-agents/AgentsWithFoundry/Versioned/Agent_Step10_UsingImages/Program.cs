// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Image Multi-Modality with an AI agent.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

const string VisionInstructions = "You are a helpful agent that can analyze images";
const string VisionName = "VisionAgent";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Define the agent you want to create. (Prompt Agent in this case)
AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    VisionName,
    new AgentVersionCreationOptions(new PromptAgentDefinition(model: deploymentName) { Instructions = VisionInstructions }));
ChatClientAgent agent = aiProjectClient.AsAIAgent(agentVersion);

ChatMessage message = new(ChatRole.User, [
    new TextContent("What do you see in this image?"),
    await DataContent.LoadFromAsync("assets/walkway.jpg"),
]);

AgentSession session = await agent.CreateSessionAsync();

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(message, session))
{
    Console.WriteLine(update);
}

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
