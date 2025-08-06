// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;
using OpenAI;

namespace Specs;

/// <summary>
/// Shows how to use <see cref="AIAgent"/> with Azure AI Persistent Agents.
/// </summary>
/// <remarks>
/// Running "az login" command in terminal is required for authentication with Azure AI service.
/// </remarks>
public sealed class FoundrySDKAlignment(ITestOutputHelper output) : AgentSample(output)
{
    private const string JokerName = "Joker";
    private const string JokerInstructions = "You are good at telling jokes.";

    [Fact]
    public async Task Sample1()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(
            TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a persistent agent.
        var persistentAgent = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName!,
            name: JokerName,
            instructions: JokerInstructions);

        // Get a server side agent.
        AIAgent agent = await persistentAgentsClient.GetAIAgentAsync(persistentAgent.Value.Id);

        // Respond to user input.
        var input = "Tell me a joke about a pirate.";
        Console.WriteLine(input);
        Console.WriteLine(await agent.RunAsync(input));

        // Delete the persistent agent.
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    [Fact]
    public async Task Sample2()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(
            TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a Agent Framework agent.
        AIAgent agent = await persistentAgentsClient.CreateAIAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName!,
            name: JokerName,
            instructions: JokerInstructions);

        // Respond to user input.
        var input = "Tell me a joke about a pirate.";
        Console.WriteLine(input);
        Console.WriteLine(await agent.RunAsync(input));

        // Delete the persistent agent.
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    [Fact]
    public async Task Sample3()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(
            TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());

        // Create a Agent Framework agent.
        AIAgent agent = await persistentAgentsClient.CreateAIAgentAsync(
            model: TestConfiguration.AzureAI.DeploymentName!,
            name: JokerName,
            instructions: JokerInstructions);

        // Start a new thread for the agent conversation.
        AgentThread thread = agent.GetNewThread();

        // Respond to user input.
        await RunAgentAsync("Tell me a joke about a pirate.");
        await RunAgentAsync("Now add some emojis to the joke.");

        // Local function to run agent and display the conversation messages for the thread.
        async Task RunAgentAsync(string input)
        {
            Console.WriteLine(
                $"""
                User: {input}
                Assistant:
                {await agent.RunAsync(input, thread)}

                """);
        }

        // Cleanup
        await persistentAgentsClient.Threads.DeleteThreadAsync(thread.ConversationId);
        await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);
    }

    [Fact]
    public async Task Sample4()
    {
        // Get a client to create server side agents with.
        var persistentAgentsClient = new PersistentAgentsClient(
            TestConfiguration.AzureAI.Endpoint, new AzureCliCredential());
        var model = TestConfiguration.OpenAI.ChatModelId;

        // Define the agents
        AIAgent analystAgent =
            await persistentAgentsClient.CreateAIAgentAsync(
                model,
                name: "Analyst",
                instructions:
                """
                You are a marketing analyst. Given a product description, identify:
                - Key features
                - Target audience
                - Unique selling points
                """,
                description: "A agent that extracts key concepts from a product description.");
        AIAgent writerAgent =
            await persistentAgentsClient.CreateAIAgentAsync(
                model,
                name: "copywriter",
                instructions:
                """
                You are a marketing copywriter. Given a block of text describing features, audience, and USPs,
                compose a compelling marketing copy (like a newsletter section) that highlights these points.
                Output should be short (around 150 words), output just the copy as a single text block.
                """,
                description: "An agent that writes a marketing copy based on the extracted concepts.");
        AIAgent editorAgent =
            await persistentAgentsClient.CreateAIAgentAsync(
                model,
                name: "editor",
                instructions:
                """
                You are an editor. Given the draft copy, correct grammar, improve clarity, ensure consistent tone,
                give format and make it polished. Output the final improved copy as a single text block.
                """,
                description: "An agent that formats and proofreads the marketing copy.");

        // Define the orchestration
        SequentialOrchestration orchestration =
            new(analystAgent, writerAgent, editorAgent)
            {
                LoggerFactory = this.LoggerFactory,
            };

        // Run the orchestration
        string input = "An eco-friendly stainless steel water bottle that keeps drinks cold for 24 hours";
        Console.WriteLine($"\n# INPUT: {input}\n");
        AgentRunResponse result = await orchestration.RunAsync(input);
        Console.WriteLine($"\n# RESULT: {result}");

        // Cleanup
        await persistentAgentsClient.Administration.DeleteAgentAsync(analystAgent.Id);
        await persistentAgentsClient.Administration.DeleteAgentAsync(writerAgent.Id);
        await persistentAgentsClient.Administration.DeleteAgentAsync(editorAgent.Id);
    }
}
