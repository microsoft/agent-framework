// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using GenerativeAI.Microsoft;
using Microsoft.Agents;
using Microsoft.Agents.CopilotStudio;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.AI.AzureAIAgentsPersistent;
using Microsoft.Shared.Samples;

namespace GettingStarted;

public class AgentTypesDemo(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task FoundryAgentAsync()
    {
        // Get a client for using server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a new server side agent and expose it via the FoundryAgent class.
        FoundryAgent foundryAgent = await FoundryAgent.CreateAsync(persistentAgentsClient, new()
        {
            Name = "Joker",
            Description = "An agent that tells jokes.",
            Instructions = "You are good at telling jokes.",
            Model = TestConfiguration.AzureAI.DeploymentName!,
            // We can configure foundry specific options like grounding tools.
            Tools = [new BingGroundingToolDefinition(new([new(TestConfiguration.BingGrounding.ConnectionId) { Count = 5, Freshness = "Week" }]))],
            Temperature = 0.1f,
        });

        // We can invoke the agent with foundry specific parameters.
        var result = await foundryAgent.RunAsync("Search the web for good jokes and list them to me, then tell me a variation of one of the jokes", options: new ThreadAndRunOptions() { Temperature = 0.9f });
        Console.WriteLine(result.Text);

        // FoundryAgent inherits from the base Agent abstraction, so it can also be used as such.
        Agent agent = foundryAgent;

        // Invoke using the base Agent abstraction.
        result = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(result.Text);

        // We can also retrieve an existing agent using its ID.
        var secondFoundryAgent = await FoundryAgent.GetAsync(persistentAgentsClient, foundryAgent.Id);

        // We can add useful helper methods to the FoundryAgent class like Delete.
        await secondFoundryAgent.EnsureAgentDeletedAsync();
    }

    [Fact]
    public async Task ChatCopilotStudioAgentAsync()
    {
        // Get a CopilotClient for communicating with an Copilot Studio Agent.
        CopilotClient client = this.GetCopilotClient();

        // Expose the CopilotClient as a CopilotStudioAgent.
        Agent agent = new CopilotStudioAgent(client, "FriendlyAssistant", "Friendly Assistant");

        // Invoke using the base Agent abstraction.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);
    }

    [Fact]
    public async Task ChatClientAgentAsync()
    {
        // Get a chat client for Gemini.
        using GenerativeAIChatClient chatClient = new(TestConfiguration.GoogleAI.ApiKey, TestConfiguration.GoogleAI.Gemini.ModelId);

        // Create a ChatClientAgent using the chat client. This supports any IChatClient implementation, including
        // OpenAI Chat Completion, OpenAI Responses, OpenAI Assistants, Ollama, ONNX, AzureAI Inference, Amazon Bedrock, and more.
        Agent agent = new ChatClientAgent(chatClient, new() { Name = "Joker", Instructions = "You are good at telling jokes." });

        // Invoke using the base Agent abstraction.
        var response = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(response.Text);
    }
}
