// Copyright (c) Microsoft. All rights reserved.

// Chat Reduction — Keep conversation context within model limits
//
// This sample shows how to use a chat history reducer to keep the context
// within model size limits. Any IChatReducer implementation can customize
// how the chat history is reduced.
// NOTE: This feature is only supported where chat history is stored locally
// (e.g. OpenAI Chat Completion). For server-side history (e.g. Foundry Agents),
// the service manages chat history size.

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// Construct the agent, and provide a factory to create an in-memory chat message store with a reducer that keeps only the last 2 non-system messages.
// You must dissable client side conversation storage for clients that support it.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AIProjectClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetProjectOpenAIClient()
    .GetProjectResponsesClient()
    .AsIChatClientWithStoredOutputDisabled(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { ModelId = deploymentName, Instructions = "You are good at telling jokes." },
        Name = "Joker",
        ChatHistoryProvider = new InMemoryChatHistoryProvider(new() { ChatReducer = new MessageCountingChatReducer(2) })
    });

AgentSession session = await agent.CreateSessionAsync();

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));

// Get the chat history to see how many messages are stored.
// We can use the ChatHistoryProvider, that is also used by the agent, to read the
// chat history from the session state, and see how the reducer is affecting the stored messages.
// Here we expect to see 2 messages, the original user message and the agent response message.
if (session.TryGetInMemoryChatHistory(out var chatHistory))
{
    Console.WriteLine($"\nChat history has {chatHistory.Count} messages.\n");
}

// Invoke the agent a few more times.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a robot.", session));

// Now we expect to see 4 messages in the chat history, 2 input and 2 output.
// While the target number of messages is 2, the default time for the InMemoryChatHistoryProvider
// to trigger the reducer is just before messages are contributed to a new agent run.
// So at this time, we have not yet triggered the reducer for the most recently added messages,
// and they are still in the chat history.
if (session.TryGetInMemoryChatHistory(out chatHistory))
{
    Console.WriteLine($"\nChat history has {chatHistory.Count} messages.\n");
}

Console.WriteLine(await agent.RunAsync("Tell me a joke about a lemur.", session));
if (session.TryGetInMemoryChatHistory(out chatHistory))
{
    Console.WriteLine($"\nChat history has {chatHistory.Count} messages.\n");
}

// At this point, the chat history has exceeded the limit and the original message will not exist anymore,
// so asking a follow up question about it may not work as expected.
Console.WriteLine(await agent.RunAsync("What was the first joke I asked you to tell again?", session));

if (session.TryGetInMemoryChatHistory(out chatHistory))
{
    Console.WriteLine($"\nChat history has {chatHistory.Count} messages.\n");
}
