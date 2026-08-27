// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.FileInput;

/// <summary>
/// Demonstrate how to provide file-based input to a declarative workflow.
/// </summary>
/// <remarks>
/// See the README.md file in this folder and the parent folder (../README.md) for
/// detailed information about the configuration required to run this sample.
/// </remarks>
internal sealed class Program
{
    public static async Task Main()
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agents exist in Foundry.
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Create the workflow factory. This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("FileInput.yaml", foundryEndpoint);

        // Execute the workflow with the content from the bundled text file.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, CreateInputMessage());
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "FileInputAgent",
            agentDefinition: DefineFileInputAgent(configuration),
            agentDescription: "Summarizes files provided as declarative workflow input.");
    }

    private static DeclarativeAgentDefinition DefineFileInputAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModel))
        {
            Instructions =
                """
                You summarize product briefs provided as user input to a workflow.

                Provide:
                - A short summary
                - Important facts or entities
                - One suggested follow-up question
                """
        };

    private static ChatMessage CreateInputMessage()
    {
        string productBrief = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "ProductBrief.txt"));
        return new ChatMessage(
            ChatRole.User,
            [
                new TextContent($"Summarize this product brief for a launch announcement:{Environment.NewLine}{Environment.NewLine}{productBrief}"),
            ]);
    }
}
