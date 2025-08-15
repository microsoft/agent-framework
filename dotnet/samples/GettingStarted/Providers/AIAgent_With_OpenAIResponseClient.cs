// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;
using OpenAI.Responses;

namespace Providers;

/// <summary>
/// End-to-end sample showing how to use <see cref="ChatClientAgent"/> with OpenAI Chat Completion.
/// </summary>
public sealed class AIAgent_With_OpenAIResponseClient(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    /// <summary>
    /// This will use the conversation id to reference the thread state on the server side.
    /// </summary>
    [Fact]
    public async Task RunWithResponses()
    {
        // Get the agent directly from OpenAIClient.
        AIAgent agent = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetOpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId)
            .CreateAIAgent(JokerInstructions, JokerName);

        // Start a new thread for the agent conversation based on the type.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(
                $"""
                User: {input}
                Assistant:
                {await agent.RunAsync(input, thread)}

                """);
        }
    }

    /// <summary>
    /// This will use in-memory messages to store the thread state.
    /// </summary>
    [Fact]
    public async Task RunWithResponsesAndStoreOutputDisabled()
    {
        // Get the agent directly from OpenAIClient.
        AIAgent agent = new OpenAIClient(TestConfiguration.OpenAI.ApiKey)
            .GetOpenAIResponseClient(TestConfiguration.OpenAI.ChatModelId)
            .CreateAIAgent(options: new()
            {
                Name = JokerName,
                Instructions = JokerInstructions,
                ChatOptions = new ChatOptions
                {
                    // We can use the RawRepresentationFactory to provide Response service specific
                    // options. Here we can indicate that we do not want the service to store the
                    // conversation in a service managed thread.
                    RawRepresentationFactory = (_) => new ResponseCreationOptions() { StoredOutputEnabled = false }
                }
            });

        // Start a new thread for the agent conversation based on the type.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to invoke agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(
                $"""
                User: {input}
                Assistant:
                {await agent.RunAsync(input, thread)}

                """);
        }
    }
}
