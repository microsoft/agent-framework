// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;

namespace GettingStarted.Steps;

/// <summary>
/// Demonstrates how to suspend and resume a thread with the <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class Step06_ChatClientAgent_SuspendResumeThread(ITestOutputHelper output) : AgentSample(output)
{
    private const string ParrotName = "Parrot";
    private const string ParrotInstructions = "Repeat the user message in the voice of a pirate and then end with a parrot sound.";

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
    [InlineData(ChatClientProviders.OpenAIResponses_InMemoryMessageThread)]
    [InlineData(ChatClientProviders.OpenAIResponses_ConversationIdThread)]
    public async Task RunWithThread(ChatClientProviders provider)
    {
        // Define the options for the chat client agent.
        var agentOptions = new ChatClientAgentOptions
        {
            Name = ParrotName,
            Instructions = ParrotInstructions,

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
        var serializedThread = thread.Serialize();

        // The thread can now be saved to a database, file, or any other storage mechanism
        // and loaded again later.

        // Deserialize the thread state after loading from storage.
        var resumedThread = agent.DeserializeThread(serializedThread);

        Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke.", resumedThread));

        // Clean up the server-side agent and thread after use when applicable (depending on the provider).
        await base.AgentCleanUpAsync(provider, agent, thread);
    }
}
