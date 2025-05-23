// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Xunit;
using Xunit.Abstractions;

namespace GettingStarted;

/// <summary>
/// Demonstrate creation of <see cref="ChatClientAgent"/> and
/// eliciting its response to three explicit user messages.
/// </summary>
public class Step01_Agent(ITestOutputHelper output) : BaseAgentsTest(output)
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
    public async Task UseSingleChatClientAgent()
    {
        var chatClient = this.CreateChatClient();

        // Define the agent
        ChatClientAgent agent =
            new(chatClient)
            {
                Name = ParrotName,
                Instructions = ParrotInstructions,
            };

        // Respond to user input
        await InvokeAgentAsync("Fortune favors the bold.");
        await InvokeAgentAsync("I came, I saw, I conquered.");
        await InvokeAgentAsync("Practice makes perfect.");

        chatClient?.Dispose();

        // Local function to invoke agent and display the conversation messages.
        async Task InvokeAgentAsync(string input)
        {
            ChatMessage message = new(ChatRole.User, input);
            this.WriteAgentChatMessage(message);

            await foreach (AgentResponseItem<ChatMessage> response in agent.InvokeAsync(message))
            {
                this.WriteAgentChatMessage(response);
            }
        }
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained.
    /// </summary>
    [Fact]
    public async Task UseSingleChatClientAgentWithConversation()
    {
        var chatClient = this.CreateChatClient();

        // Define the agent
        ChatClientAgent agent =
            new(chatClient)
            {
                Name = JokerName,
                Instructions = JokerInstructions,
            };

        // Define a thread variable to maintain the conversation context.
        // Since we are passing a null thread to InvokeAsync on the first invocation,
        // the agent will create a new thread for the conversation.
        AgentThread? thread = null;

        // Respond to user input
        await InvokeAgentAsync("Tell me a joke about a pirate.");
        await InvokeAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages.
        async Task InvokeAgentAsync(string input)
        {
            ChatMessage message = new(ChatRole.User, input);
            this.WriteAgentChatMessage(message);

            await foreach (AgentResponseItem<ChatMessage> response in agent.InvokeAsync(message, thread))
            {
                this.WriteAgentChatMessage(response);
                thread = response.Thread;
            }
        }
    }

    /// <summary>
    /// Demonstrate the usage of <see cref="ChatClientAgent"/> where a conversation history is maintained
    /// and where the thread containing the conversation is created manually.
    /// </summary>
    [Fact]
    public async Task UseSingleChatClientAgentWithManuallyCreatedThread()
    {
        var chatClient = this.CreateChatClient();

        // Define the agent
        ChatClientAgent agent =
            new(chatClient)
            {
                Name = JokerName,
                Instructions = JokerInstructions,
            };

        // Define a thread variable to maintain the conversation context.
        // Since we are creating the thread, we can pass some initial messages to it.
        AgentThread? thread = new ChatMessageAgentThread(
            [
                new ChatMessage(ChatRole.User, "Tell me a joke about a pirate."),
                new ChatMessage(ChatRole.Assistant, "Why did the pirate go to school? Because he wanted to improve his \"arrrrrrrrrticulation\""),
            ]);

        // Respond to user input
        await InvokeAgentAsync("Now add some emojis to the joke.");
        await InvokeAgentAsync("Now make the joke sillier.");

        // Local function to invoke agent and display the conversation messages.
        async Task InvokeAgentAsync(string input)
        {
            ChatMessage message = new(ChatRole.User, input);
            this.WriteAgentChatMessage(message);

            // Use the thread we created earlier to continue the conversation.
            await foreach (AgentResponseItem<ChatMessage> response in agent.InvokeAsync(message, thread))
            {
                this.WriteAgentChatMessage(response);
            }
        }
    }
}
