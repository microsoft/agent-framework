// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AgentVersion jokerAgentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    "JokerAgent",
    new AgentVersionCreationOptions(
        new PromptAgentDefinition(deploymentName)
        {
            Instructions = "You are good at telling jokes."
        }));
ChatClientAgent jokerAgent = aiProjectClient.AsAIAgent(jokerAgentVersion);

// Create a conversation session — this creates a server-side conversation that appears in the Foundry Project UI.
ProjectConversation conversation = await aiProjectClient
    .GetProjectOpenAIClient()
    .GetProjectConversationsClient()
    .CreateProjectConversationAsync();
ChatClientAgentSession session = (ChatClientAgentSession)await jokerAgent.CreateSessionAsync(conversation.Id);

Console.WriteLine(await jokerAgent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await jokerAgent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming.
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.WriteLine(update);
}

Console.WriteLine();

await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.WriteLine(update);
}

Console.WriteLine();

// Cleanup: deletes the agent and all its versions.
await aiProjectClient.Agents.DeleteAgentAsync(jokerAgent.Name);
