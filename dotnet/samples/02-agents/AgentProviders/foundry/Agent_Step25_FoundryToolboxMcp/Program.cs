// Copyright (c) Microsoft. All rights reserved.

// Foundry Toolbox via MCP (Streamable HTTP).
//
// Point an `McpClient` at a Foundry Toolbox's MCP endpoint. The agent
// discovers the toolbox's tools at runtime and invokes them locally.

using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental API
#pragma warning disable AAIP001  // AgentToolboxes is experimental

// Name of the toolbox to create and connect to.
const string ToolboxName = "research_toolbox";
const string Query = "Find the REST API documentation for Azure Container Apps session pools.";

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

TokenCredential credential = new DefaultAzureCredential();

// Connect to the new version so the tool-search configuration is unambiguous.
var toolboxEndpoint = await CreateSampleToolboxAsync(ToolboxName, endpoint, credential);

// Inject a fresh Azure AI bearer token on every MCP request.
using var httpClient = new HttpClient(new BearerTokenHandler(credential, "https://ai.azure.com/.default")
{
    InnerHandler = new HttpClientHandler(),
});

Console.WriteLine($"Connecting to toolbox MCP endpoint: {toolboxEndpoint}");

await using McpClient mcpClient = await McpClient.CreateAsync(
    new HttpClientTransport(
        new HttpClientTransportOptions
        {
            Endpoint = new Uri(toolboxEndpoint),
            Name = "foundry_toolbox",
            TransportMode = HttpTransportMode.StreamableHttp,
            AdditionalHeaders = new Dictionary<string, string>
            {
                ["Foundry-Features"] = "Toolboxes=V1Preview",
            },
        },
        httpClient));

IList<McpClientTool> mcpTools = await mcpClient.ListToolsAsync();
Console.WriteLine($"Toolbox MCP tools available: {string.Join(", ", mcpTools.Select(t => t.Name))}");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

AIAgent agent = aiProjectClient.AsAIAgent(
    model: deploymentName,
    instructions: "You are a helpful assistant. Use the available toolbox tools to answer the user.",
    name: "ToolboxMcpAgent",
    tools: [.. mcpTools.Cast<AITool>()]);

Console.WriteLine($"\nUser: {Query}\n");
Console.WriteLine($"Assistant: {await agent.RunAsync(Query)}");

// ---------------------------------------------------------------------------
// Helper: create a sample toolbox version so the sample runs end-to-end
// ---------------------------------------------------------------------------
static async Task<string> CreateSampleToolboxAsync(string name, string endpoint, TokenCredential credential)
{
    // Toolboxes are normally configured in the Foundry portal or a deployment
    // script, not the application itself. This helper exists so the sample can
    // be run end-to-end without first setting a toolbox up by hand.

    var adminClient = new AgentAdministrationClient(new Uri(endpoint), credential);
    var toolboxClient = adminClient.GetAgentToolboxes();

    // Enable discovery through tool_search and invocation through call_tool.
    // The underlying MCP tools are not all placed in the model's initial context.
    MCPToolboxTool mcpTool = new("api-specs")
    {
        ServerUri = new Uri("https://gitmcp.io/Azure/azure-rest-api-specs"),
        ToolCallApprovalPolicy = new McpToolCallApprovalPolicy(DefaultMcpToolCallApprovalPolicy.NeverRequireApproval),
    };

    ToolboxVersion created = (await toolboxClient.CreateVersionAsync(
        name: name,
        tools: [mcpTool, new ToolSearchToolboxTool()],
        description: "Sample toolbox with tool search — created by Agent_Step25 sample.")).Value;

    Console.WriteLine($"Created toolbox '{created.Name}' v{created.Version} ({created.Tools.Count} tool(s))");
    return $"{endpoint.TrimEnd('/')}/toolboxes/{created.Name}/versions/{created.Version}/mcp?api-version=v1";
}

// ---------------------------------------------------------------------------
// DelegatingHandler: attaches a fresh Azure AI bearer token to every request
// ---------------------------------------------------------------------------
internal sealed class BearerTokenHandler(TokenCredential credential, string scope) : DelegatingHandler
{
    private readonly TokenRequestContext _tokenContext = new([scope]);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        AccessToken token = await credential.GetTokenAsync(this._tokenContext, cancellationToken).ConfigureAwait(false);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        return await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
    }
}
