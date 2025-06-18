// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;

namespace Steps;

/// <summary>
/// Provides test methods to demonstrate the usage of chat agents with different interaction models.
/// </summary>
/// <remarks>This class contains examples of using <see cref="ChatClientAgent"/> to showcase scenarios with and without conversation history.
/// Each test method demonstrates how to configure and interact with the agents, including handling user input and displaying responses.
/// </remarks>
public sealed class Step01_Running(ITestOutputHelper output) : AgentSample(output)
{
    private const string ParrotName = "Parrot";
    private const string ParrotInstructions = "Repeat the user message in the voice of a pirate and then end with a parrot sound.";

    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where each invocation is
    /// a unique interaction with no conversation history between them.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.OpenAI)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    public async Task RunWithoutThread(ChatClientProviders provider)
    {
        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider);

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = ParrotName,
                Instructions = ParrotInstructions,
            });

        // Respond to user input
        await RunAgentAsync("Fortune favors the bold.");
        await RunAgentAsync("I came, I saw, I conquered.");
        await RunAgentAsync("Practice makes perfect.");

        // Local function to invoke agent and display the conversation messages.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input);
            this.WriteResponseOutput(response);
        }
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.OpenAI)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    public async Task RunWithConversationThread(ChatClientProviders provider)
    {
        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider);

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = JokerName,
                Instructions = JokerInstructions,
            });

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteResponseOutput(response);
        }
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> in streaming mode,
    /// where a conversation is maintained by the <see cref="AgentThread"/>.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.OpenAI)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    public async Task StreamingRunWithConversationThread(ChatClientProviders provider)
    {
        // Get the chat client to use for the agent.
        using var chatClient = base.GetChatClient(provider);

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = ParrotName,
                Instructions = ParrotInstructions,
            });

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            await foreach (var update in agent.RunStreamingAsync(input, thread))
            {
                this.WriteAgentOutput(update);
            }
        }
    }
}
