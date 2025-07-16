// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;

namespace Providers;

/// <summary>
/// End-to-end sample showing how to use <see cref="ChatClientAgent"/> with OpenAI Chat Completion.
/// </summary>
public sealed class ChatClientAgent_With_OpenAIChatCompletion(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithChatCompletion()
    {
        // Get the chat client to use for the agent.
        using var chatClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();

        // Define the agent
        ChatClientAgent agent = new(chatClient, JokerInstructions, JokerName);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
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
}
