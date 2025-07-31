// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Chat;

namespace Providers;

/// <summary>
/// End-to-end sample showing how to use <see cref="AIAgent"/> with OpenAI Chat Completion and Responses.
/// </summary>
public sealed class AIAgent_With_OpenAIClient(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithChatCompletion()
    {
        // Get the agent directly from OpenAIClient.
        AIAgent agent = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .CreateAIAgent(JokerInstructions, JokerName);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(input);

            var response = await agent.RunAsync(input, thread);

            Console.WriteLine(response.Messages.Last().Text);
        }
    }

    [Fact]
    public async Task RunWithChatCompletionReturnChatCompletion()
    {
        // Get the agent directly from OpenAIClient.
        var agent = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .CreateAIAgent(JokerInstructions, JokerName);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(input);

            var response = await agent.RunAsync(input, thread);
            var chatCompletion = response.AsChatCompletion();

            Console.WriteLine(chatCompletion.Content.Last().Text);
        }
    }

    [Fact]
    public async Task RunWithChatCompletionWithOpenAIChatMessage()
    {
        // Get the agent directly from OpenAIClient.
        var agent = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetChatClient(TestConfiguration.OpenAI.ChatModelId)
            .CreateAIAgent(JokerInstructions, JokerName);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(input);

            // Use the OpenAI.Chat message types directly
            var chatMessage = new UserChatMessage(input);
            var chatCompletion = await agent.RunAsync(chatMessage, thread);

            Console.WriteLine(chatCompletion.Content.Last().Text);
        }
    }
}
