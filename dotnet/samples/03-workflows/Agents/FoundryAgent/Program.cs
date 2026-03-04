// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowFoundryAgentSample;

/// <summary>
/// This sample shows how to use code-first agents within a workflow.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - An Azure Foundry project endpoint and model id.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Foundry project client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

        // Create agents using code-first pattern (no server-side agent registration)
        IChatClient chatClient = new ProjectResponsesClient(
            projectEndpoint: new Uri(endpoint),
            tokenProvider: new DefaultAzureCredential())
            .AsIChatClient();

        AIAgent frenchAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "French Translator",
            ChatOptions = new() { ModelId = deploymentName, Instructions = "You are a translation assistant that translates the provided text to French." },
        });
        AIAgent spanishAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "Spanish Translator",
            ChatOptions = new() { ModelId = deploymentName, Instructions = "You are a translation assistant that translates the provided text to Spanish." },
        });
        AIAgent englishAgent = chatClient.AsAIAgent(new ChatClientAgentOptions
        {
            Name = "English Translator",
            ChatOptions = new() { ModelId = deploymentName, Instructions = "You are a translation assistant that translates the provided text to English." },
        });

        // Build the workflow by adding executors and connecting them
        var workflow = new WorkflowBuilder(frenchAgent)
            .AddEdge(frenchAgent, spanishAgent)
            .AddEdge(spanishAgent, englishAgent)
            .Build();

        // Execute the workflow
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));
        // Must send the turn token to trigger the agents.
        // The agents are wrapped as executors. When they receive messages,
        // they will cache the messages and only start processing when they receive a TurnToken.
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is AgentResponseUpdateEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }
}
