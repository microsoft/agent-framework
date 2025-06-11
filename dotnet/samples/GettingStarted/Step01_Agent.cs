// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.SampleUtilities;
using OpenAI;
using Xunit.Abstractions;

namespace GettingStarted;

#pragma warning disable  // Identifiers should not contain underscores

/// <summary>TBD</summary>
public sealed class Step01_Agent(ITestOutputHelper output) : BaseTest(output)
#pragma warning restore CA1707 // Identifiers should not contain underscores
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
    public async Task UseChatClientAgentWithNoThread()
    {
        using var chatClient = GetChatClient();
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
    /// Demonstrate the usage of <see cref="ChatCompletionAgent"/> where a conversation history is maintained.
    /// </summary>
    [Fact]
    public async Task UseChatClientAgentWithConversationThread()
    {
        using var chatClient = GetChatClient();

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

    private IChatClient GetChatClient()
    {
        return new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();
    }
}
