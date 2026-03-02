// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use a chat history reducer to keep the context within model size limits.
// Any implementation of Microsoft.Extensions.AI.IChatReducer can be used to customize how the chat history is reduced.
// NOTE: this feature is only supported where the chat history is stored locally, such as with OpenAI Chat Completion.
// Where the chat history is stored server side, such as with Azure Foundry Agents, the service must manage the chat history size.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Construct the agent, and provide a factory to create an in-memory chat message store with a reducer that keeps only the last 2 non-system messages.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are good at telling jokes." },
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
