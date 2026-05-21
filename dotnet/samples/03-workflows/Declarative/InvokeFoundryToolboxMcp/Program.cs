// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates using InvokeMcpTool to call MCP tools through a Foundry toolbox.
// It creates a sample toolbox that exposes Microsoft Learn MCP tools, lists the toolbox tools
// through the reserved tools/list operation, then calls microsoft_docs_search from the workflow.

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Concurrent;
using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI.Workflows.Declarative.Mcp;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;
using Shared.Workflows;

#pragma warning disable OPENAI001 // Experimental API
#pragma warning disable AAIP001 // AgentToolboxes is experimental

namespace Demo.Workflows.Declarative.InvokeFoundryToolboxMcp;

/// <summary>
/// Demonstrates a workflow that uses InvokeMcpTool to call MCP tools exposed through a Foundry toolbox.
/// </summary>
/// <remarks>
/// This sample provisions a toolbox with Microsoft Learn MCP tools, uses the reserved
/// <c>tools/list</c> tool name to list the toolbox tools, calls one specific toolbox tool,
/// and has a Foundry agent summarize the results.
/// </remarks>
internal sealed class Program
{
    private const string ToolboxNameSetting = "FOUNDRY_TOOLBOX_NAME";
    private const string ToolboxApiVersionSetting = "FOUNDRY_AGENT_TOOLSET_API_VERSION";
    private const string ToolboxMcpServerUrlSetting = "FOUNDRY_TOOLBOX_MCP_SERVER_URL";
    private const string DocsServerLabelSetting = "FOUNDRY_TOOLBOX_DOCS_SERVER_LABEL";
    private const string WebSearchToolNameSetting = "FOUNDRY_TOOLBOX_WEB_SEARCH_TOOL_NAME";
    private const string DefaultToolboxName = "declarative_foundry_toolbox_mcp";
    private const string DefaultToolboxApiVersion = "v1";
    private const string DefaultDocsServerLabel = "microsoft_docs";
    private const string DefaultWebSearchToolName = "web_search";

    public static async Task Main(string[] args)
    {
        // Initialize configuration
        IConfiguration configuration = Application.InitializeConfig();
        Uri foundryEndpoint = new(configuration.GetValue(Application.Settings.FoundryEndpoint));
        string toolboxName = configuration[ToolboxNameSetting] ?? DefaultToolboxName;
        string toolboxApiVersion = configuration[ToolboxApiVersionSetting] ?? DefaultToolboxApiVersion;
        string docsServerLabel = configuration[DocsServerLabelSetting] ?? DefaultDocsServerLabel;
        string webSearchToolName = configuration[WebSearchToolNameSetting] ?? DefaultWebSearchToolName;

        // WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
        // In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
        // latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
        DefaultAzureCredential credential = new();

        // Ensure sample toolbox and agent exist in Foundry
        string toolboxEndpoint = await CreateSampleToolboxAsync(toolboxName, docsServerLabel, foundryEndpoint, credential);
        string toolboxMcpServerUrl = BuildToolboxMcpServerUrl(toolboxEndpoint, toolboxName, toolboxApiVersion);
        IConfiguration workflowConfiguration = new ConfigurationBuilder()
            .AddConfiguration(configuration)
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                [ToolboxMcpServerUrlSetting] = toolboxMcpServerUrl,
                [DocsServerLabelSetting] = docsServerLabel,
                [WebSearchToolNameSetting] = webSearchToolName,
            })
            .Build();

        await CreateAgentAsync(foundryEndpoint, configuration, credential);

        // Get input from command line or console
        string workflowInput = Application.GetInput(args);

        // Create the MCP tool handler for invoking the Foundry toolbox MCP proxy.
        ConcurrentBag<HttpClient> createdHttpClients = [];
        DefaultMcpToolHandler mcpToolHandler = new(
            httpClientProvider: async (serverUrl, _) =>
            {
                await Task.CompletedTask.ConfigureAwait(false);

                if (!string.Equals(serverUrl, toolboxMcpServerUrl, StringComparison.OrdinalIgnoreCase))
                {
                    return null;
                }

                FoundryToolboxBearerTokenHandler handler = new(credential)
                {
                    InnerHandler = new HttpClientHandler()
                };
                HttpClient httpClient = new(handler);
                createdHttpClients.Add(httpClient);
                return httpClient;
            });

        try
        {
            // Create the workflow factory with MCP tool provider
            WorkflowFactory workflowFactory = new("InvokeFoundryToolboxMcp.yaml", foundryEndpoint)
            {
                Configuration = workflowConfiguration,
                McpToolHandler = mcpToolHandler
            };

            // Execute the workflow
            WorkflowRunner runner = new() { UseJsonCheckpoints = true };
            await runner.ExecuteAsync(workflowFactory.CreateWorkflow, workflowInput);
        }
        finally
        {
            // Clean up connections and dispose created HttpClients
            await mcpToolHandler.DisposeAsync();

            foreach (HttpClient httpClient in createdHttpClients)
            {
                httpClient.Dispose();
            }
        }
    }

    private static async Task CreateAgentAsync(Uri foundryEndpoint, IConfiguration configuration, TokenCredential credential)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, credential);

        await aiProjectClient.CreateAgentAsync(
            agentName: "FoundryToolboxMcpAgent",
            agentDefinition: DefineToolboxAgent(configuration),
            agentDescription: "Summarizes Foundry toolbox MCP tool results");
    }

    private static DeclarativeAgentDefinition DefineToolboxAgent(IConfiguration configuration)
    {
        return new DeclarativeAgentDefinition(configuration.GetValue(Application.Settings.FoundryModel))
        {
            Instructions =
                """
                You are a helpful assistant that explains results produced by tools exposed through a Foundry toolbox.
                The conversation history contains output from BOTH a Microsoft Learn documentation search (MCP) and a Foundry web search.
                Synthesize an answer that draws on both sources, calls out where they agree or differ, and notes which toolbox tool produced each fact when it is relevant.
                Be concise.
                """
        };
    }

    private static async Task<string> CreateSampleToolboxAsync(string name, string serverLabel, Uri foundryEndpoint, TokenCredential credential)
    {
        AgentAdministrationClientOptions options = new();
        options.AddPolicy(new FoundryFeaturesPolicy("Toolboxes=V1Preview"), PipelinePosition.PerCall);
        AgentAdministrationClient adminClient = new(foundryEndpoint, credential, options);
        AgentToolboxes toolboxClient = adminClient.GetAgentToolboxes();

        try
        {
            await toolboxClient.DeleteToolboxAsync(name);
            Console.WriteLine($"Deleted existing toolbox '{name}'");
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            // Toolbox does not exist.
        }

        ProjectsAgentTool webTool = ProjectsAgentTool.AsProjectTool(ResponseTool.CreateWebSearchTool());

        ProjectsAgentTool mcpTool = ProjectsAgentTool.AsProjectTool(ResponseTool.CreateMcpTool(
            serverLabel: serverLabel,
            serverUri: new Uri("https://learn.microsoft.com/api/mcp"),
            toolCallApprovalPolicy: new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.NeverRequireApproval)));

        ToolboxVersion created = (await toolboxClient.CreateToolboxVersionAsync(
            name: name,
            tools: [webTool, mcpTool],
            description: "Sample toolbox combining Foundry web search with the Microsoft Learn MCP tools for the declarative InvokeFoundryToolboxMcp sample.")).Value;

        Console.WriteLine($"Created toolbox '{created.Name}' v{created.Version} ({created.Tools.Count} tool(s))");

        return $"{foundryEndpoint.ToString().TrimEnd('/')}/toolboxes";
    }

    private static string BuildToolboxMcpServerUrl(string toolboxEndpoint, string toolboxName, string apiVersion) =>
        $"{toolboxEndpoint.TrimEnd('/')}/{toolboxName}/mcp?api-version={Uri.EscapeDataString(apiVersion)}";

    private sealed class FoundryToolboxBearerTokenHandler(TokenCredential credential) : DelegatingHandler
    {
        private static readonly TokenRequestContext s_tokenContext =
            new(["https://ai.azure.com/.default"]);

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            AccessToken token = await credential.GetTokenAsync(s_tokenContext, cancellationToken);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

            return await base.SendAsync(request, cancellationToken);
        }
    }

    private sealed class FoundryFeaturesPolicy(string feature) : PipelinePolicy
    {
        private const string FeatureHeader = "Foundry-Features";

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Add(FeatureHeader, feature);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Add(FeatureHeader, feature);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }
}
