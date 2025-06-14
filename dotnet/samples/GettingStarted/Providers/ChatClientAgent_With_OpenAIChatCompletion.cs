// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;

namespace Providers;

/// <summary>
/// Shows how to use <see cref="ChatClientAgent"/> with Open AI Chat Completion.
/// </summary>
public sealed class ChatClientAgent_With_OpenAIChatCompletion(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithOpenAIAssistant()
    {
        // Get the chat client to use for the agent.
        using var chatClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();

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
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteResponseOutput(response);
        }
    }
}
