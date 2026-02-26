// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with a multi-turn conversation.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Define the agent you want to create. (Prompt Agent in this case)
AgentVersionCreationOptions options = new(new PromptAgentDefinition(model: deploymentName) { Instructions = JokerInstructions });

// Retrieve an AIAgent for the created server side agent version.
ChatClientAgent jokerAgent = await aiProjectClient.CreateAIAgentAsync(name: JokerName, options);

// Invoke the agent with a multi-turn conversation, where the context is preserved in the session object.
// Create a conversation in the server
ProjectConversationsClient conversationsClient = aiProjectClient.GetProjectOpenAIClient().GetProjectConversationsClient();
ProjectConversation conversation = await conversationsClient.CreateProjectConversationAsync();

// Providing the conversation Id is not strictly necessary, but by not providing it no information will show up in the Foundry Project UI as conversations.
// Sessions that don't have a conversation Id will work based on the `PreviousResponseId`.
AgentSession session = await jokerAgent.CreateSessionAsync(conversation.Id);

Console.WriteLine(await jokerAgent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await jokerAgent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Invoke the agent with a multi-turn conversation and streaming, where the context is preserved in the session object.
session = await jokerAgent.CreateSessionAsync(conversation.Id);
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.WriteLine(update);
}
await foreach (AgentResponseUpdate update in jokerAgent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.WriteLine(update);
}

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(jokerAgent.Name);

// Cleanup the conversation created.
await conversationsClient.DeleteConversationAsync(conversation.Id);
