// Copyright (c) Microsoft. All rights reserved.
// Description: Define workflows declaratively using YAML configuration files.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace WorkflowSamples.Declarative;

// <declarative_workflow>
/// <summary>
/// Demonstrates a declarative workflow defined in YAML.
/// Uses a menu agent with function tools assigned, initialized from
/// a YAML workflow definition file.
/// </summary>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Create function tools for the menu agent
        MenuPlugin menuPlugin = new();
        AIFunction[] functions =
            [
                AIFunctionFactory.Create(menuPlugin.GetMenu),
                AIFunctionFactory.Create(menuPlugin.GetSpecials),
                AIFunctionFactory.Create(menuPlugin.GetItemPrice),
            ];

        await CreateAgentAsync(foundryEndpoint, configuration, functions);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow from a YAML definition file
        WorkflowFactory workflowFactory = new("FunctionTools.yaml", foundryEndpoint);

        // Execute the workflow with checkpointing support
        WorkflowRunner runner = new(functions) { UseJsonCheckpoints = true };
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration, AIFunction[] functions)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "MenuAgent",
            agentDefinition: DefineMenuAgent(configuration, functions),
            agentDescription: "Provides information about the restaurant menu");
    }

    private static PromptAgentDefinition DefineMenuAgent(IConfiguration configuration, AIFunction[] functions)
    {
        PromptAgentDefinition agentDefinition =
            new(configuration.GetValue(Application.Settings.FoundryModelMini))
            {
                Instructions =
                    """
                    Answer the users questions on the menu.
                    For questions or input that do not require searching the documentation, inform the
                    user that you can only answer questions what's on the menu.
                    """
            };

        foreach (AIFunction function in functions)
        {
            agentDefinition.Tools.Add(function.AsOpenAIResponseTool());
        }

        return agentDefinition;
    }
}
// </declarative_workflow>
