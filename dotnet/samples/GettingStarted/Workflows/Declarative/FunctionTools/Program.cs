// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.FunctionTools;

/// <summary>
/// Demonstrate a workflow that responds to user input using an agent who
/// with function tools assigned.  Exits the loop when the user enters "exit".
/// </summary>
/// <remarks>
/// See the README.md file in the parent folder (../README.md) for detailed
/// information about the configuration required to run this sample.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agents exist in Foundry.
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

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("FunctionTools.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
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
