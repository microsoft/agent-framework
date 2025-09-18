// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace WorkflowFoundryAgentSample;

/// <summary>
/// This sample shows how to use Azure Foundry Agents within a workflow.
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
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
        var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4o-mini";
        var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

        // Create agents
        AIAgent frenchAgent = await GetTranslationAgentAsync("French", persistentAgentsClient, model);
        AIAgent spanishAgent = await GetTranslationAgentAsync("Spanish", persistentAgentsClient, model);
        AIAgent englishAgent = await GetTranslationAgentAsync("English", persistentAgentsClient, model);

        // Build the workflow by adding executors and connecting them
        var workflow = new WorkflowBuilder(frenchAgent)
            .AddEdge(frenchAgent, spanishAgent)
            .AddEdge(spanishAgent, englishAgent)
            .Build<ChatMessage>();

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));
        // Must send the turn token to trigger the agents.
        // The agents are wrapped as executors. When they receive messages,
        // they will cache the messages and only start processing when they receive a TurnToken.
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is AgentRunUpdateEvent executorComplete)
            {
                Console.WriteLine($"{executorComplete.ExecutorId}: {executorComplete.Data}");
            }
        }

        // Cleanup the agents created for the sample.
        await persistentAgentsClient.Administration.DeleteAgentAsync(frenchAgent.Id);
        await persistentAgentsClient.Administration.DeleteAgentAsync(spanishAgent.Id);
        await persistentAgentsClient.Administration.DeleteAgentAsync(englishAgent.Id);
    }

    /// <summary>
    /// Creates a translation agent for the specified target language.
    /// </summary>
    /// <param name="targetLanguage">The target language for translation</param>
    /// <param name="persistentAgentsClient">The PersistentAgentsClient to create the agent</param>
    /// <param name="model">The model to use for the agent</param>
    /// <returns>A ChatClientAgent configured for the specified language</returns>
    private static async Task<ChatClientAgent> GetTranslationAgentAsync(
        string targetLanguage,
        PersistentAgentsClient persistentAgentsClient,
        string model)
    {
        var agentMetadata = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: model,
            name: $"{targetLanguage} Translator",
            instructions: $"You are a translation assistant that translates the provided text to {targetLanguage}.");

        return await persistentAgentsClient.GetAIAgentAsync(agentMetadata.Value.Id);
    }
}
