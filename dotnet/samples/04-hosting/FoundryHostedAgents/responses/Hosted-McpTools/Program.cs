// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a hosted agent with two layers of MCP (Model Context Protocol) tools:
//
// 1. CLIENT-SIDE MCP: The agent connects to the Microsoft Learn MCP server directly via
//    McpClient, discovers tools, and handles tool invocations locally within the agent process.
//
// 2. SERVER-SIDE MCP: The agent declares a HostedMcpServerTool for the same MCP server which
//    delegates tool discovery and invocation to the LLM provider (Responses API). The provider
//    calls the MCP server on behalf of the agent — no local connection needed.
//
// Both patterns use the public Microsoft Learn MCP server. It is deployed to Foundry directly from
// source (code / ZIP upload), so the platform builds and runs your code with no container image.

#pragma warning disable MEAI001 // HostedMcpServerTool is experimental

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var projectEndpoint = new Uri(System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));

var deployment = System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    ?? System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL")
    ?? "gpt-4o";

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
var credential = new DefaultAzureCredential();

// ── Client-side MCP: Microsoft Learn (local resolution) ──────────────────────
// Connect directly to the MCP server. The agent discovers and invokes tools locally.
Console.WriteLine("Connecting to Microsoft Learn MCP server (client-side)...");

await using var learnMcp = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("https://learn.microsoft.com/api/mcp"),
    Name = "Microsoft Learn (client)",
}));

var clientTools = await learnMcp.ListToolsAsync();
Console.WriteLine($"Client-side MCP tools: {string.Join(", ", clientTools.Select(t => t.Name))}");

// ── Server-side MCP: Microsoft Learn (provider resolution) ───────────────────
// Declare a HostedMcpServerTool — the LLM provider (Responses API) handles tool
// invocations directly. No local MCP connection needed for this pattern.
AITool serverTool = new HostedMcpServerTool(
    serverName: "microsoft_learn_hosted",
    serverAddress: "https://learn.microsoft.com/api/mcp")
{
    AllowedTools = ["microsoft_docs_search"],
    ApprovalMode = HostedMcpServerToolApprovalMode.NeverRequire
};
Console.WriteLine("Server-side MCP tool: microsoft_docs_search (via HostedMcpServerTool)");

// ── Combine both tool types into a single agent ──────────────────────────────
// The agent has access to tools from both MCP patterns simultaneously.
List<AITool> allTools = [.. clientTools.Cast<AITool>(), serverTool];

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-mcp-tools";

AIAgent agent = new AIProjectClient(projectEndpoint, credential)
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful developer assistant with access to Microsoft Learn documentation.
            Use the available tools to search and retrieve documentation.
            Be concise and provide direct answers with relevant links.
            """,
        name: agentName,
        description: "Developer assistant with dual-layer MCP tools (client-side and server-side)",
        tools: allTools);

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();
