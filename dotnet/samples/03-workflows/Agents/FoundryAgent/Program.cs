// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

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
        // Set up the Azure AI Project client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var aiProjectClient = new AIProjectClient(new Uri(endpoint), new AzureCliCredential());

        // Create agents
        AIAgent frenchAgent = await CreateTranslationAgentAsync("French", aiProjectClient, deploymentName);
        AIAgent spanishAgent = await CreateTranslationAgentAsync("Spanish", aiProjectClient, deploymentName);
        AIAgent englishAgent = await CreateTranslationAgentAsync("English", aiProjectClient, deploymentName);

        try
        {
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
        finally
        {
            // Cleanup the agents created for the sample.
            await aiProjectClient.Agents.DeleteAgentAsync(frenchAgent.Name);
            await aiProjectClient.Agents.DeleteAgentAsync(spanishAgent.Name);
            await aiProjectClient.Agents.DeleteAgentAsync(englishAgent.Name);
        }
    }

    /// <summary>
    /// Creates a translation agent for the specified target language.
    /// </summary>
    /// <param name="targetLanguage">The target language for translation</param>
    /// <param name="aiProjectClient">The <see cref="AIProjectClient"/> to create the agent with.</param>
    /// <param name="model">The model to use for the agent</param>
    /// <returns>A FoundryAgent configured for the specified language</returns>
    private static async Task<FoundryAgent> CreateTranslationAgentAsync(
        string targetLanguage,
        AIProjectClient aiProjectClient,
        string model)
    {
        AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
            $"{targetLanguage} Translator",
            new AgentVersionCreationOptions(
                new PromptAgentDefinition(model: model)
                {
                    Instructions = $"You are a translation assistant that translates the provided text to {targetLanguage}.",
                }));
        return aiProjectClient.AsAIAgent(agentVersion);
    }
}
