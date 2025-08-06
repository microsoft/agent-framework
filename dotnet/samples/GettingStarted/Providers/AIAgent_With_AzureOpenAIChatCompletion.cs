// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;

namespace Providers;

/// <summary>
/// End-to-end sample showing how to use <see cref="ChatClientAgent"/> with Azure OpenAI Chat Completion.
/// </summary>
public sealed class AIAgent_With_AzureOpenAIChatCompletion(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithChatCompletion()
    {
        // Get the OpenAI client to use for the agent.
        var openAIClient = (TestConfiguration.AzureOpenAI.ApiKey is null)
            // Use Azure CLI credentials if API key is not provided.
            ? new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new AzureCliCredential())
            : new AzureOpenAIClient(TestConfiguration.AzureOpenAI.Endpoint, new ApiKeyCredential(TestConfiguration.AzureOpenAI.ApiKey));

        // Create the agent
        AIAgent agent = openAIClient.GetChatClient(TestConfiguration.AzureOpenAI.DeploymentName).CreateAIAgent(JokerInstructions, JokerName);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
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
