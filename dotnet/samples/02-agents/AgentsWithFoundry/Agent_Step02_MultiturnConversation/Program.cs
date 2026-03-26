// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a multi-turn conversation agent with AIProjectClient.AsAIAgent(...).

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());
AIAgent agent = aiProjectClient.AsAIAgent(
    deploymentName,
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

ProjectConversation conversation = await aiProjectClient
    .GetProjectOpenAIClient()
    .GetProjectConversationsClient()
    .CreateProjectConversationAsync();

AgentSession session = await agent.GetService<ChatClientAgent>()!.CreateSessionAsync(conversation.Id);

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the session object.
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.Write(update);
}

Console.WriteLine();

await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.Write(update);
}

Console.WriteLine();
