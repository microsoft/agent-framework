// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;
using OpenAI;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Providers;

/// <summary>
/// Shows how to use <see cref="ChatClientAgent"/> with Open AI Assistants.
/// </summary>
public sealed class ChatClientAgent_With_OpenAIAssistant(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithOpenAIAssistant()
    {
        // Get a client to create server side agents with.
        var openAIClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey);
        var assistantClient = openAIClient.GetAssistantClient();

        // Create a server side agent to work with.
        var assistantCreateResult = await assistantClient.CreateAssistantAsync(
            TestConfiguration.OpenAI.ChatModelId,
            new()
            {
                Name = JokerName,
                Instructions = JokerInstructions
            });

        var assistantId = assistantCreateResult.Value.Id;

        // Get the chat client to use for the agent.
        using var chatClient = assistantClient.AsIChatClient(assistantId);

        // Define the agent
        ChatClientAgent agent = new(chatClient);

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

        // Cleanup
        await assistantClient.DeleteThreadAsync(thread.Id);
        await assistantClient.DeleteAssistantAsync(assistantId);
    }
}
