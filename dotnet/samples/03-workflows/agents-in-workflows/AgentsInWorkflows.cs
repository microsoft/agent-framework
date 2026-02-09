// Copyright (c) Microsoft. All rights reserved.
// Description: Using AI agents as workflow steps in a translation chain.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowSamples.AgentsInWorkflows;

// <agents_in_workflows>
/// <summary>
/// Demonstrates using AI agents as executors within a workflow.
/// Three translation agents are connected sequentially:
/// French Agent → Spanish Agent → English Agent
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create translation agents
        AIAgent frenchAgent = GetTranslationAgent("French", chatClient);
        AIAgent spanishAgent = GetTranslationAgent("Spanish", chatClient);
        AIAgent englishAgent = GetTranslationAgent("English", chatClient);

        // Build the workflow by chaining agents sequentially
        var workflow = new WorkflowBuilder(frenchAgent)
            .AddEdge(frenchAgent, spanishAgent)
            .AddEdge(spanishAgent, englishAgent)
            .Build();

        // Execute the workflow
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));

        // Send the turn token to trigger the agents
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is AgentResponseUpdateEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }
    }

    private static ChatClientAgent GetTranslationAgent(string targetLanguage, IChatClient chatClient) =>
        new(chatClient, $"You are a translation assistant that translates the provided text to {targetLanguage}.");
}
// </agents_in_workflows>
