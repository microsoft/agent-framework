// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using the InvokeMcpTool action to call MCP (Model Context Protocol)
// server tools directly from a declarative workflow. MCP servers expose tools that can be
// invoked to perform specific tasks, like searching documentation or executing operations.

using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.Mcp;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
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
/// This sample uses the Microsoft Learn MCP server to search Azure documentation and the Microsoft Foundry MCP server to get AI model details.
/// When you run the sample, provide an AI model (e.g. gpt-5.4-mini) as input,
/// The workflow will use the MCP tools to find relevant information about the model from Microsoft Learn and foundry, then an agent will summarize the results.
/// </para>
/// <para>
/// See the README.md file in the parent folder (../README.md) for detailed
/// information about the configuration required to run this sample.
/// </para>
/// </remarks>
internal sealed class Program
{
    private const string McpHttpClientName = "workflow-mcp";

    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));

        // Ensure sample agent exists in Foundry
        await CreateAgentAsync(foundryEndpoint, configuration);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        DefaultAzureCredential credential = new();

        // Reuse HTTP handlers while each MCP invocation owns its client.
        ServiceCollection services = new();
        services.AddHttpClient(McpHttpClientName)
            .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
            {
                UseCookies = false,
                AllowAutoRedirect = false,
                CheckCertificateRevocationList = true
            })
            .AddHttpMessageHandler(() => new AzureMcpBearerTokenHandler(credential))
            .SetHandlerLifetime(TimeSpan.FromMinutes(2));
        await using ServiceProvider serviceProvider = services.BuildServiceProvider();
        await using DefaultMcpToolHandler mcpToolHandler = new(
            serviceProvider.GetRequiredService<IHttpClientFactory>(), McpHttpClientName);

        // Create the workflow factory with MCP tool provider
        WorkflowFactory workflowFactory = new("InvokeMcpTool.yaml", foundryEndpoint)
        {
            McpToolHandler = mcpToolHandler
        };

        // Execute the workflow
        WorkflowRunner runner = new() { UseJsonCheckpoints = true };
        await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
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

    private static DeclarativeAgentDefinition DefineSearchAgent(IConfiguration configuration)
    {
        return new DeclarativeAgentDefinition(configuration.GetValue(Application.Settings.FoundryModel))
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

    private sealed class AzureMcpBearerTokenHandler(TokenCredential credential) : DelegatingHandler
    {
        private static readonly TokenRequestContext s_tokenContext =
            new(["https://mcp.ai.azure.com/.default"]);

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Uri? requestUri = request.RequestUri;
            if (requestUri is not null
                && string.Equals(requestUri.GetLeftPart(UriPartial.Authority), "https://mcp.ai.azure.com", StringComparison.OrdinalIgnoreCase))
            {
                AccessToken token = await credential.GetTokenAsync(s_tokenContext, cancellationToken);
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
            }

            return await base.SendAsync(request, cancellationToken);
        }
    }
}
