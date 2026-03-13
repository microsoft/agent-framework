// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.InvokeFunctionTool;

/// <summary>
/// Demonstrate a workflow that uses InvokeFunctionTool to call functions directly
/// from the workflow without going through an AI agent first.
/// </summary>
/// <remarks>
/// The InvokeFunctionTool action allows workflows to invoke function tools directly,
/// enabling pre-fetching of data or executing operations before calling an AI agent.
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

        // Create the menu plugin with functions that can be invoked directly by the workflow
        MenuPlugin menuPlugin = new();
        AIFunction[] functions =
            [
                AIFunctionFactory.Create(menuPlugin.GetMenu),
                AIFunctionFactory.Create(menuPlugin.GetSpecials),
                AIFunctionFactory.Create(menuPlugin.GetItemPrice),
            ];

        // Ensure sample agent exists in Foundry
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.
        WorkflowFactory workflowFactory = new("InvokeFunctionTool.yaml", foundryEndpoint);

        // Execute the workflow
        WorkflowRunner runner = new(functions) { UseJsonCheckpoints = true };
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "FunctionMenuAgent",
            agentDefinition: DefineMenuAgent(configuration, []), // Create Agent with no function tool in the definition.
            agentDescription: "Provides information about the restaurant menu");
    }

    private static PromptAgentDefinition DefineMenuAgent(IConfiguration configuration, AIFunction[] functions)
    {
        PromptAgentDefinition agentDefinition =
            new(configuration.GetValue(Application.Settings.FoundryModel))
            {
                Instructions =
                    """
                    Answer the users questions about the menu.
                    Use the information provided in the conversation history to answer questions.
                    If the information is already available in the conversation, use it directly.
                    For questions or input that do not require searching the documentation, inform the
                    user that you can only answer questions about what's on the menu.
                    """
            };

        foreach (AIFunction function in functions)
        {
            agentDefinition.Tools.Add(function.AsOpenAIResponseTool());
        }

        return agentDefinition;
    }
}
