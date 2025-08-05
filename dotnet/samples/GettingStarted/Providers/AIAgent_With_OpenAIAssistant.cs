// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Providers;

/// <summary>
/// End-to-end sample showing how to use <see cref="AIAgent"/> with OpenAI Assistants.
/// </summary>
public sealed class AIAgent_With_OpenAIAssistant(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithAssistant()
    {
        // Get a client to create server side agents with.
        var openAIClient = new OpenAIClient(TestConfiguration.OpenAI.ApiKey);

        // Get the agent directly from OpenAIClient.
        AIAgent agent = openAIClient
            .GetAssistantClient()
            .CreateAIAgent(
                TestConfiguration.OpenAI.ChatModelId,
                options: new()
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

        // Cleanup
        var assistantClient = openAIClient.GetAssistantClient();
        await assistantClient.DeleteThreadAsync(thread.ConversationId);
        await assistantClient.DeleteAssistantAsync(agent.Id);
    }
}
