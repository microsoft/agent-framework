// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use server-side conversations with a FoundryAgent.
// Server-side conversations persist on the Foundry service and are visible in the Foundry Project UI.
// Use this when you need conversation history to be stored and accessible server-side.

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

ChatClientAgent agent = aiProjectClient
    .AsAIAgent(deploymentName, instructions: "You are good at telling jokes.", name: "JokerAgent");

ProjectConversationsClient conversationsClient = aiProjectClient
            .GetProjectOpenAIClient()
            .GetProjectConversationsClient();

ProjectConversation conversation = (await conversationsClient.CreateProjectConversationAsync().ConfigureAwait(false)).Value;

// CreateConversationSessionAsync creates a server-side ProjectConversation
// that persists on the Foundry service and is visible in the Foundry Project UI.
AgentSession session = await agent.CreateSessionAsync(conversation.Id);

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Streaming with server-side conversation context.
await foreach (AgentResponseUpdate update in agent.RunStreamingAsync("Tell me another joke, but about a ninja this time.", session))
{
    Console.Write(update);
}

Console.WriteLine();
