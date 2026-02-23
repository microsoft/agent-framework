// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using the InvokeMcpTool action to call MCP (Model Context Protocol)
// server tools directly from a declarative workflow. MCP servers expose tools that can be
// invoked to perform specific tasks, like searching documentation or executing operations.

using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Workflows.Declarative.InvokeMcpTool;

/// <summary>
/// Demonstrates a workflow that uses InvokeMcpTool to call MCP server tools
/// directly from the workflow.
/// </summary>
/// <remarks>
/// <para>
/// The InvokeMcpTool action allows workflows to invoke tools on MCP (Model Context Protocol)
/// servers. This enables:
/// </para>
/// <list type="bullet">
/// <item>Searching external data sources like documentation</item>
/// <item>Executing operations on remote servers</item>
/// <item>Integrating with MCP-compatible services</item>
/// </list>
/// <para>
/// This sample uses the Microsoft Learn MCP server to search Azure documentation.
/// </para>
/// <para>
/// See the README.md file in the parent folder (../README.md) for detailed
/// information about the configuration required to run this sample.
/// </para>
/// </remarks>
internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agent exists in Foundry
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the MCP tool provider for invoking MCP server tools
        DefaultMcpToolHandler mcpToolProvider = new(tokenCredential: new DefaultAzureCredential(), tokenScopes: ["https://mcp.ai.azure.com"]);

        // Create the workflow factory with MCP tool provider
        WorkflowFactory workflowFactory = new("InvokeMcpTool.yaml", foundryEndpoint)
        {
            McpToolHandler = mcpToolProvider
        };

        // Execute the workflow
        WorkflowRunner runner = new() { UseJsonCheckpoints = true };
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);

        // Clean up MCP connections
        await mcpToolProvider.DisposeAsync();
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration)
    {
        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        AIProjectClient aiProjectClient = new(foundryEndpoint, new DefaultAzureCredential());

        await aiProjectClient.CreateAgentAsync(
            agentName: "McpSearchAgent",
            agentDefinition: DefineSearchAgent(configuration),
            agentDescription: "Provides information based on search results");
    }

    private static PromptAgentDefinition DefineSearchAgent(IConfiguration configuration)
    {
        return new PromptAgentDefinition(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                You are a helpful assistant that answers questions based on search results.
                Use the information provided in the conversation history to answer questions.
                If the information is already available in the conversation, use it directly.
                Be concise and helpful in your responses.
                """
        };
    }
}
