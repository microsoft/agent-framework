// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Samples;

namespace Providers;

/// <summary>
/// Shows how to use <see cref="ChatClientAgent"/> with Azure AI Persistent Agents.
/// </summary>
/// <remarks>
/// Running "az login" command in terminal is required for authentication with Azure AI service.
/// </remarks>
public sealed class ChatClientAgent_With_AzureAIAgentsPersistent(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task RunWithAzureAIAgentsPersistent()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a server side agent to work with.
        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName,
            name: JokerName,
            instructions: JokerInstructions);

        var persistentAgent = persistentAgentResponse.Value;

        // Get the chat client to use for the agent.
        using var chatClient = persistentAgentsClient.AsIChatClient(persistentAgent.Id);

        // Define the agent.
        ChatClientAgent agent = new(chatClient);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to run agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            this.WriteUserMessage(input);

            var response = await agent.RunAsync(input, thread);

            this.WriteResponseOutput(response);
        }

        // Cleanup
        await persistentAgentsClient.Threads.DeleteThreadAsync(thread.Id);
        await persistentAgentsClient.Administration.DeleteAgentAsync(persistentAgent.Id);
    }
}
