// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to load a Foundry toolbox and pass its tools as server-side
// tools when creating an agent. The Foundry platform handles tool execution — the agent
// process does not invoke tools locally.

using System.ClientModel;
using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Experimental API
#pragma warning disable AAIP001  // AgentToolboxes is experimental
#pragma warning disable CS8321   // Local functions may be commented-out alternatives

// Replace with your own Foundry toolbox name.
const string ToolboxName = "research_toolbox";
// Used only by CombineToolboxes — swap in a second toolbox you own.
const string SecondToolboxName = "analysis_toolbox";
// Replace with any question that exercises the tools configured in your toolbox.
const string Query = "Introduce yourself and briefly describe the tools you can use to help me.";

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("Set FOUNDRY_PROJECT_ENDPOINT to your Foundry project endpoint.");
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
var projectClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());

await Main(projectClient, model, endpoint);
// await CombineToolboxes(projectClient, model, endpoint);

// ---------------------------------------------------------------------------
// Main: single toolbox
// ---------------------------------------------------------------------------
static async Task Main(AIProjectClient projectClient, string model, string endpoint)
{
    Console.WriteLine("=== Foundry Toolbox Server-Side Tools Example ===");

    // Comment out if the toolbox already exists in your Foundry project.
    await CreateSampleToolboxAsync(ToolboxName, endpoint);

    // Omit the version to resolve the toolbox's current default version at runtime.
    var tools = await projectClient.GetToolboxToolsAsync(ToolboxName);

    AIAgent agent = projectClient
        .AsAIAgent(
            model: model,
            instructions: "You are a research assistant. Use the available tools to answer questions.",
            tools: tools.ToList());

    Console.WriteLine($"User: {Query}");
    Console.WriteLine($"Result: {await agent.RunAsync(Query)}\n");
}

// ---------------------------------------------------------------------------
// Alternative: combine tools from multiple toolboxes
// ---------------------------------------------------------------------------
static async Task CombineToolboxes(AIProjectClient projectClient, string model, string endpoint)
{
    Console.WriteLine("=== Combine Toolboxes Example ===");

    // Comment out if the toolboxes already exist in your Foundry project.
    await CreateSampleToolboxAsync(ToolboxName, endpoint);
    await CreateSampleToolboxAsync(SecondToolboxName, endpoint);

    var toolboxA = await projectClient.GetToolboxToolsAsync(ToolboxName);
    var toolboxB = await projectClient.GetToolboxToolsAsync(SecondToolboxName);

    var allTools = toolboxA.Concat(toolboxB).ToList();

    AIAgent agent = projectClient
        .AsAIAgent(
            model: model,
            instructions: "You are a research assistant. Use all available tools to answer questions.",
            tools: allTools);

    Console.WriteLine($"User: {Query}");
    Console.WriteLine($"Combined-toolbox result: {await agent.RunAsync(Query)}\n");
}

// ---------------------------------------------------------------------------
// Helper: create (or replace) a sample toolbox so the sample works out-of-the-box
// ---------------------------------------------------------------------------
static async Task CreateSampleToolboxAsync(string name, string endpoint)
{
    // Toolboxes are normally configured in the Foundry portal or a deployment
    // script, not the application itself. This helper exists so the sample can
    // be run end-to-end without first setting a toolbox up by hand.

    // The Foundry-Features header is currently required for toolbox CRUD operations.
    var options = new AgentAdministrationClientOptions();
    options.AddPolicy(new FoundryFeaturesPolicy("Toolboxes=V1Preview"), PipelinePosition.PerCall);
    var adminClient = new AgentAdministrationClient(
        new Uri(endpoint),
        new DefaultAzureCredential(),
        options);
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
// Pipeline policy that adds the Foundry-Features header for toolbox CRUD
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
