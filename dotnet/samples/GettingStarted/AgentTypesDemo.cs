// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents;
using Microsoft.Agents.CopilotStudio;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.AI.AzureAIAgentsPersistent;
using Microsoft.ML.OnnxRuntimeGenAI;
using Microsoft.Shared.Samples;

namespace GettingStarted;

public class AgentTypesDemo(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Fact]
    public async Task FoundryAgentAsync()
    {
        // Get a client for using server side agents.
        PersistentAgentsClient persistentAgentsClient = new(TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a new server side agent and expose it as a FoundryAgent.
        var createPersistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            name: "Joker",
            description: "An agent that tells jokes.",
            instructions: "You are good at telling jokes.",
            model: TestConfiguration.AzureAI.DeploymentName!);
        FoundryAgent foundryAgent = createPersistentAgentResponse.AsRunnableAgent(persistentAgentsClient);

        // We can invoke the agent with foundry specific parameters.
        var result = await foundryAgent.RunAsync(
            "Search the web for good jokes and list them to me, then tell me a variation of one of the jokes",
            options: new ThreadAndRunOptions() { OverrideTools = [new BingGroundingToolDefinition(new([new(TestConfiguration.BingGrounding.ConnectionId) { Count = 5, Freshness = "Week" }]))] });
        Console.WriteLine(result.Text);

        // FoundryAgent inherits from the base Agent abstraction, so it can also be used as such.
        Agent agent = foundryAgent;

        // Invoke using the base Agent abstraction.
        result = await agent.RunAsync("Tell me a joke about a pirate.");
        Console.WriteLine(result.Text);

        // We can also retrieve an existing agent using its ID.
        FoundryAgent existingFoundryAgent = (await persistentAgentsClient.Administration.GetAgentAsync(foundryAgent.Id)).AsRunnableAgent(persistentAgentsClient);

        // We can add useful helper methods to the FoundryAgent class like Delete.
        await existingFoundryAgent.EnsureAgentDeletedAsync();
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
        using OnnxRuntimeGenAIChatClient chatClient = new(@"C:\GR\huggingface\microsoft\Phi-4-mini-instruct-onnx\cpu_and_mobile\cpu-int4-rtn-block-32-acc-level-4");

        // Create a ChatClientAgent using the chat client. This supports any IChatClient implementation, including
        // OpenAI Chat Completion, OpenAI Responses, OpenAI Assistants, Ollama, ONNX, AzureAI Inference, Amazon Bedrock, Google Gemini, and more.
        Agent agent = new ChatClientAgent(chatClient, new() { Name = "FriendlyAssistant", Instructions = "You are a friendly assistant." });

        // Invoke using the base Agent abstraction.
        var response = await agent.RunAsync("What is the capital of France?");
        Console.WriteLine(response.Text);
    }
}
