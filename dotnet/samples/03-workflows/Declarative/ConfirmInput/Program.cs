// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Configuration;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.ConfirmInput;

/// <summary>
/// Demonstrate how to use the question action to request user input
/// and confirm it matches the original input.
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

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("ConfirmInput.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }
}
