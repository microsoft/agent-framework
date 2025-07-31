// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI.Agents;

namespace Steps;

/// <summary>
/// Demonstrates how to suspend and resume a thread with the <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class Step08_ChatClientAgent_SuspendResumeThread(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a thread is suspended.
    /// The thread is serialized and can be stored to a database, file, or any other storage mechanism,
    /// and then deserialized later to resume the conversation with the agent.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIResponses_InMemoryMessageThread)]
    [InlineData(ChatClientProviders.OpenAIResponses_ConversationIdThread)]
    public async Task SuspendResumeThread(ChatClientProviders provider)
    {
        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = JokerName,
            Instructions = JokerInstructions,

            // Get chat options based on the store type, if needed.
            ChatOptions = base.GetChatOptions(provider),
        };

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider, agentOptions);

        // Define the agent
        var agent = new ChatClientAgent(chatClient, agentOptions);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", thread));

        // Serialize the thread state, so it can be stored for later use.
        JsonElement serializedThread = await thread.SerializeAsync();

        // The thread can now be saved to a database, file, or any other storage mechanism
        // and loaded again later.

        // Deserialize the thread state after loading from storage.
        AgentThread resumedThread = await agent.DeserializeThreadAsync(serializedThread);

        Console.WriteLine(await agent.RunAsync("Now tell the same joke in the voice of a pirate, and add some emojis to the joke.", resumedThread));

        // Clean up the server-side agent and thread after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }
}
