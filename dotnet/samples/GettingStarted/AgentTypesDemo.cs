// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using GenerativeAI.Microsoft;
using Microsoft.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.AzureAIAgentsPersistent;
using Microsoft.Shared.Samples;

namespace GettingStarted;

public class AgentTypesDemo(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task FoundryAgentAsync()
    {
        // Get a client for creating server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a server side agent and expose it as a FoundryAgent.
        FoundryAgent foundryAgent = await persistentAgentsClient.CreateFoundryAgentAsync(
            new()
            {
                Name = "Joker",
                Description = "An agent that tells jokes.",
                Instructions = "You are good at telling jokes.",
                Model = TestConfiguration.AzureAI.DeploymentName!,
                Temperature = 0.1f,
            });

        // We can invoke the agent with foundry specific parameters.
        var result = await foundryAgent.RunAsync("Tell me a joke about a pirate.", options: new ThreadAndRunOptions() { Temperature = 0.9f });
        Console.WriteLine(result.Text);

        // FoundryAgent inherits from the base Agent abstraction, so it can also be used as such.
        Agent agent = foundryAgent;

        // Invoke using the base Agent abstraction.
        result = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(result.Text);

        // We can also retrieve an existing agent using its ID.
        var secondFoundryAgent = await persistentAgentsClient.GetFoundryAgentAsync(foundryAgent.Id);

        // And we can delete the agent via a helper on the FoundryAgent class.
        await secondFoundryAgent.EnsureAgentDeletedAsync();
    }

    [Fact]
    public async Task ChatClientAgentAsync()
    {
        // Get a chat client for Gemini.
        using GenerativeAIChatClient chatClient = new(TestConfiguration.GoogleAI.ApiKey, TestConfiguration.GoogleAI.Gemini.ModelId);

        // Create the agent.
        Agent agent = new ChatClientAgent(chatClient, new() { Name = "Joker", Instructions = "You are good at telling jokes." });

        // Invoke the agent.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);
    }
}
