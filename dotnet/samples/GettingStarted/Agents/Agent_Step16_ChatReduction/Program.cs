// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use a chat history reducer to keep the context within model size limits.
// Any implementation of Microsoft.Extensions.AI.IChatReducer can be used to customize how the chat history is reduced.
// NOTE: this feature is only supported where the chat history is stored locally, such as with OpenAI Chat Completion.
// Where the chat history is stored server side, such as with Azure Foundry Agents, the service must manage the chat history size.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Construct the agent, and provide a factory to create an in-memory chat message store with a reducer that keeps only the last 2 non-system messages.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(new ChatClientAgentOptions
    {
        ChatOptions = new() { Instructions = "You are good at telling jokes." },
        Name = "Joker",
        ChatMessageStoreFactory = ctx => new InMemoryChatMessageStore(new MessageCountingChatReducer(2), ctx.SerializedState, ctx.JsonSerializerOptions)
    });

AgentThread thread = agent.GetNewThread();

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

// Get the chat history to see how many messages are stored.
IList<ChatMessage>? chatHistory = thread.GetService<IList<ChatMessage>>();
Console.WriteLine($"\nChat history has {chatHistory?.Count} messages.\n");

// Invoke the agent a few more times.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a robot.", thread));
Console.WriteLine($"\nChat history has {chatHistory?.Count} messages.\n");
Console.WriteLine(await agent.RunAsync("Tell me a joke about a lemur.", thread));
Console.WriteLine($"\nChat history has {chatHistory?.Count} messages.\n");

// At this point, the chat history has exceeded the limit and the original message will not exist anymore,
// so asking a follow up question about it will not work as expected.
Console.WriteLine(await agent.RunAsync("Tell me the joke about the pirate again, but add emojis and use the voice of a parrot.", thread));

Console.WriteLine($"\nChat history has {chatHistory?.Count} messages.\n");
