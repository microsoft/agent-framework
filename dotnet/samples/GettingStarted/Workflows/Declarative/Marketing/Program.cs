// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.Marketing;

/// <summary>
/// Demonstrate a declarative workflow with three agents (Analyst, Writer, Editor)
/// sequentially engaging in a task.
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
        await CreateAgentsAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the workflow factory.  This class demonstrates how to initialize a
        // declarative workflow from a YAML file. Once the workflow is created, it
        // can be executed just like any regular workflow.
        WorkflowFactory workflowFactory = new("Marketing.yaml", foundryEndpoint);

        // Execute the workflow:  The WorkflowRunner demonstrates how to execute
        // a workflow, handle the workflow events, and providing external input.
        // This also includes the ability to checkpoint workflow state and how to
        // resume execution.
        WorkflowRunner runner = new();
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
    }

    private static async Task CreateAgentsAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "AnalystAgent",
            agentDefinition: DefineAnalystAgent(configuration),
            agentDescription: "Analyst agent for Marketing workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "WriterAgent",
            agentDefinition: DefineWriterAgent(configuration),
            agentDescription: "Writer agent for Marketing workflow");

        await aiProjectClient.CreateAgentAsync(
            agentName: "EditorAgent",
            agentDefinition: DefineEditorAgent(configuration),
            agentDescription: "Editor agent for Marketing workflow");
    }

    private static PromptAgentDefinition DefineAnalystAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are a marketing analyst. Given a product description, identify:
                - Key features
                - Target audience
                - Unique selling points
                """,
            Tools =
            {
                //AgentTool.CreateBingGroundingTool( // TODO: Use Bing Grounding when available
                //    new BingGroundingSearchToolParameters(
                //        [new BingGroundingSearchConfiguration(configuration[Application.Settings.FoundryGroundingTool])]))
            }
        };

    private static PromptAgentDefinition DefineWriterAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are a marketing copywriter. Given a block of text describing features, audience, and USPs,
                compose a compelling marketing copy (like a newsletter section) that highlights these points.
                Output should be short (around 150 words), output just the copy as a single text block.
                """
        };

    private static PromptAgentDefinition DefineEditorAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are an editor. Given the draft copy, correct grammar, improve clarity, ensure consistent tone,
                give format and make it polished. Output the final improved copy as a single text block.
                """
        };
}
