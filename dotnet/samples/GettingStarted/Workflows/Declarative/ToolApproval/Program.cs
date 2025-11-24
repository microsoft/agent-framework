// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.ToolApproval;

/// <summary>
/// Demonstrate a workflow that responds to user input using an agent who
/// has an MCP tool that requires approval.  Exits the loop when the user enters "exit".
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
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("ToolApproval.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new() { UseJsonCheckpoints = true };
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "DocumentSearchAgent",
            agentDefinition: DefineSearchAgent(configuration),
            agentDescription: "Searches documents on Microsoft Learn");
    }

    private static PromptAgentDefinition DefineSearchAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Answer the users questions by searching the Microsoft Learn documentation.
                For questions or input that do not require searching the documentation, inform the
                user that you can only answer questions related to Microsoft Learn documentation.
                """,
            Tools =
                {
                    ResponseTool.CreateMcpTool(
                        serverLabel: "microsoft_docs",
                        serverUri: new Uri("https://learn.microsoft.com/api/mcp"),
                        toolCallApprovalPolicy: new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.AlwaysRequireApproval))
                }
        };
}
