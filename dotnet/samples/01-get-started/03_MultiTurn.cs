// Copyright (c) Microsoft. All rights reserved.

// Step 3: Multi-Turn Conversations
// Maintain conversation context across multiple exchanges with the agent.
// The session object preserves conversation state between calls.
//
// For more on conversations, see: ../02-agents/conversations/
// For docs: https://learn.microsoft.com/agent-framework/agents/conversations

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

ChatClientAgent agent = await aiProjectClient.CreateAIAgentAsync(
    name: "JokerAgent",
    options: new AgentVersionCreationOptions(
        new PromptAgentDefinition(model: deploymentName)
        {
            Instructions = "You are good at telling jokes."
        }));

// <multi_turn>
// Create a conversation for tracking in Foundry UI
ProjectConversationsClient conversationsClient = aiProjectClient.GetProjectOpenAIClient().GetProjectConversationsClient();
ProjectConversation conversation = await conversationsClient.CreateProjectConversationAsync();

AgentSession session = await agent.CreateSessionAsync(conversation.Id);

Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));
// </multi_turn>

// Cleanup
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
await conversationsClient.DeleteConversationAsync(conversation.Id);
