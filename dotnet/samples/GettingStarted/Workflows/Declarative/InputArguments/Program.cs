// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.FunctionTools;

/// <summary>
/// Demonstrate a workflow that responds to user input using an agent who
/// with function tools assigned.  Exits the loop when the user enters "exit".
/// </summary>
/// <remarks>
/// See the README.md file in the parent folder (../Declarative/README.md) for detailed
/// information the configuration required to run this sample.
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agents exist in Foundry.

        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("InputArguments.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        AgentClient agentsClient = new(foundryEndpoint, new AzureCliCredential());

        await agentsClient.CreateAgentAsync(
            agentName: "LocationAgent",
            agentDefinition: DefineLocationAgent(configuration),
            agentDescription: "Chats with the user with location awareness.");
    }

    private static PromptAgentDefinition DefineLocationAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
        {
            Instructions =
                """
                Talk to the user.
                Their location is {{location}}.
                """,
            StructuredInputs =
            {
                ["location"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""unknown"""),
                        Description = "The user's location",
                    }
            }
        };
}
