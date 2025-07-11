// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable CS8524 // The switch expression does not handle some values of its input type (it is not exhaustive) involving an unnamed enum value.

namespace Providers;

/// <summary>
/// End-to-end sample showing how to use <see cref="ChatClientAgent"/> with OpenAI Chat Completion.
/// </summary>
public sealed class ChatClientAgent_With_OpenAIResponsesChatCompletion(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Theory]
    [InlineData(false)] // This will use in-memory messages to store the thread state.
    [InlineData(true)] // This will use the conversation id to reference the thread state on the server side.
    public async Task RunWithChatCompletion(bool useConversationIdThread)
    {
        // Get the chat client to use for the agent.
#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        using var chatClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetOpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId)
            .AsIChatClient();

        // Define the agent
        ChatClientAgent agent =
            new(chatClient, new()
            {
                Name = JokerName,
                Instructions = JokerInstructions,
                ChatOptions = new ChatOptions
                {
                    RawRepresentationFactory = (_) => new ResponseCreationOptions() { StoredOutputEnabled = useConversationIdThread }
                }
            });
#pragma warning restore OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

        // Start a new thread for the agent conversation based on the type.
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
