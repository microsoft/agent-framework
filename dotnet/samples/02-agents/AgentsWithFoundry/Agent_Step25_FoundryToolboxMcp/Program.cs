// Copyright (c) Microsoft. All rights reserved.

// Foundry Toolbox via MCP (Streamable HTTP).
//
// Point an `McpClient` at a Foundry Toolbox's MCP endpoint. The agent
// discovers the toolbox's tools at runtime and invokes them locally.

using System.ClientModel;
using System.ClientModel.Primitives;
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

// Must match the `<name>` segment of FOUNDRY_TOOLBOX_ENDPOINT.
const string ToolboxName = "research_toolbox";
const string Query = "What tools do you have access to?";

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
string toolboxEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_TOOLBOX_ENDPOINT")
    ?? throw new InvalidOperationException(
        "FOUNDRY_TOOLBOX_ENDPOINT is not set. Example: " +
        "https://<account>.services.ai.azure.com/api/projects/<project>/toolsets/<name>/mcp?api-version=2025-05-01-preview");

TokenCredential credential = new DefaultAzureCredential();

// Comment out if the toolbox already exists in your Foundry project.
await CreateSampleToolboxAsync(ToolboxName, endpoint, credential);

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
// Helper: create (or replace) a sample toolbox so the sample runs end-to-end
// ---------------------------------------------------------------------------
static async Task CreateSampleToolboxAsync(string name, string endpoint, TokenCredential credential)
{
    // Toolboxes are normally configured in the Foundry portal or a deployment
    // script, not the application itself. This helper exists so the sample can
    // be run end-to-end without first setting a toolbox up by hand.

    // The Foundry-Features header is currently required for toolbox CRUD operations.
    var options = new AgentAdministrationClientOptions();
    options.AddPolicy(new FoundryFeaturesPolicy("Toolboxes=V1Preview"), PipelinePosition.PerCall);
    var adminClient = new AgentAdministrationClient(new Uri(endpoint), credential, options);
    var toolboxClient = adminClient.GetAgentToolboxes();

    // Delete existing toolbox if present (ignore 404).
    try
    {
        await toolboxClient.DeleteToolboxAsync(name);
        Console.WriteLine($"Deleted existing toolbox '{name}'");
    }
    catch (ClientResultException ex) when (ex.Status == 404)
    {
        // Toolbox does not exist — nothing to delete.
    }

    // Create a fresh version with a single MCP tool.
    ProjectsAgentTool mcpTool = ProjectsAgentTool.AsProjectTool(ResponseTool.CreateMcpTool(
        serverLabel: "api-specs",
        serverUri: new Uri("https://gitmcp.io/Azure/azure-rest-api-specs"),
        toolCallApprovalPolicy: new McpToolCallApprovalPolicy(GlobalMcpToolCallApprovalPolicy.NeverRequireApproval)));

    var created = (await toolboxClient.CreateToolboxVersionAsync(
        name: name,
        tools: [mcpTool],
        description: "Sample toolbox with an MCP tool — created by Agent_Step25 sample.")).Value;

    Console.WriteLine($"Created toolbox '{created.Name}' v{created.Version} ({created.Tools.Count} tool(s))");
}

// ---------------------------------------------------------------------------
// Pipeline policy: adds the Foundry-Features header for toolbox CRUD calls
// ---------------------------------------------------------------------------
internal sealed class FoundryFeaturesPolicy(string feature) : PipelinePolicy
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
