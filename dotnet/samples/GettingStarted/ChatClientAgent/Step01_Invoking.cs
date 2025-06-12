// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;

namespace GettingStarted;

/// <summary>
/// Provides test methods to demonstrate the usage of chat agents with different interaction models.
/// </summary>
/// <remarks>This class contains examples of using <see cref="ChatClientAgent"/> to showcase scenarios with and without conversation history.
/// Each test method demonstrates how to configure and interact with the agents, including handling user input and displaying responses.
/// </remarks>
public sealed class Step01_Invoking(ITestOutputHelper output) : BaseSample(output)
{
    private const string ParrotName = "Parrot";
    private const string ParrotInstructions = "Repeat the user message in the voice of a pirate and then end with a parrot sound.";

    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where each invocation is
    /// a unique interaction with no conversation history between them.
    /// </summary>
    [Fact]
    public async Task UsingAgentWithNoThread()
    {
        using var chatClient = base.GetChatClient(ChatClientType.OpenAI);

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = ParrotName,
                Instructions = ParrotInstructions,
            });

        // Respond to user input
        await InvokeAgentAsync("Fortune favors the bold.");
        await InvokeAgentAsync("I came, I saw, I conquered.");
        await InvokeAgentAsync("Practice makes perfect.");

        chatClient?.Dispose();

        // Local function to invoke agent and display the conversation messages.
        async Task InvokeAgentAsync(string input)
        {
            this.WriteAgentChatMessage(input);

            var response = await agent.RunAsync(input);
            this.WriteAgentChatMessage(response);
        }
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained.
    /// </summary>
    [Fact]
    public async Task UsingAgentWithConversationThread()
    {
        using var chatClient = base.GetChatClient(ChatClientType.OpenAI);

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
        await InvokeAgentAsync("Tell me a joke about a pirate.");
        await InvokeAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task InvokeAgentAsync(string input)
        {
            this.WriteAgentChatMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteAgentChatMessage(response);
        }
    }
}
