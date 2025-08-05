// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;

namespace Providers;

/// <summary>
/// Shows how to use <see cref="AIAgent"/> with Azure AI Persistent Agents.
/// </summary>
/// <remarks>
/// Running "az login" command in terminal is required for authentication with Azure AI service.
/// </remarks>
public sealed class AIAgent_With_AzureAIAgentsPersistent(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task GetWithAzureAIAgentsPersistent()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a service side persistent agent.
        var persistentAgent = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName!,
            name: JokerName,
            instructions: JokerInstructions);

        // Get a server side agent.
        AIAgent agent = await persistentAgentsClient.GetAIAgentAsync(persistentAgent.Value.Id);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to run agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(input);

            var response = await agent.RunAsync(input, thread);

            Console.WriteLine(response);
        }

        // Cleanup
        await persistentAgentsClient.Threads.DeleteThreadAsync(thread.ConversationId);
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    [Fact]
    public async Task CreateWithAzureAIAgentsPersistent()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a server side persistent agent.
        AIAgent agent = await persistentAgentsClient.CreateAIAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName!,
            name: JokerName,
            instructions: JokerInstructions);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to run agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(input);

            var response = await agent.RunAsync(input, thread);

            Console.WriteLine(response);
        }

        // Cleanup
        await persistentAgentsClient.Threads.DeleteThreadAsync(thread.ConversationId);
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }
}
