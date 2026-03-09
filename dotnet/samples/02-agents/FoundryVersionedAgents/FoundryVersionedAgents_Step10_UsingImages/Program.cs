// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use Image Multi-Modality with an AI agent.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.AI;

const string VisionInstructions = "You are a helpful agent that can analyze images";
const string VisionName = "VisionAgent";

// Define the agent you want to create. (Prompt Agent in this case)
FoundryVersionedAgent agent = await FoundryVersionedAgent.CreateAIAgentAsync(name: VisionName, instructions: VisionInstructions);

ChatMessage message = new(ChatRole.User, [
    new TextContent("What do you see in this image?"),
    await DataContent.LoadFromAsync("Assets/walkway.jpg"),
]);

AgentSession session = await agent.CreateSessionAsync();

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(message, session))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await FoundryVersionedAgent.DeleteAIAgentAsync(agent);
