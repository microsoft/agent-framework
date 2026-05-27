// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to discover Agent Skills served over MCP.
//
// When launched with "--server", this executable runs a small MCP stdio server
// that exposes a unit-converter skill via the SEP-2640 convention:
//   - skill://index.json      — discovery document listing all skills
//   - skill://unit-converter/SKILL.md — the skill instructions
//
// In default (client) mode the sample launches itself as a child process,
// connects via StdioClientTransport, and uses AgentSkillsProviderBuilder
// to discover and inject the skill into a ChatClientAgent.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Server;
using OpenAI.Responses;

if (args.Length > 0 && args[0] == "--server")
{
    await RunMcpServerAsync();
    return;
}

// --- Configuration ---
string openAiEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// --- MCP client + skill discovery ---
// Launch this same assembly as a stdio MCP server in a child process.
var thisAssemblyPath = typeof(Program).Assembly.Location;
Console.WriteLine("Discovering MCP-based skills");

await using McpClient client = await McpClient.CreateAsync(
    new StdioClientTransport(new()
    {
        Name = "skills-server",
        Command = "dotnet",
        Arguments = [thisAssemblyPath, "--server"],
    }));

var skillsProvider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(client)
    .Build();

// --- Agent ---
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(new Uri(openAiEndpoint), new DefaultAzureCredential())
    .GetResponsesClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "SkillsAgent",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant. Use available skills to answer the user.",
        },
        AIContextProviders = [skillsProvider],
    },
    model: deploymentName);

// --- Run ---
Console.WriteLine(new string('-', 60));

AgentResponse response = await agent.RunAsync(
    "How many kilometers is a marathon (26.2 miles)? And how many pounds is 75 kilograms?");

Console.WriteLine($"Agent: {response.Text}");

// --- Server mode (launched as a child process via --server) ---------------------------------
static async Task RunMcpServerAsync()
{
    var builder = Host.CreateApplicationBuilder();

    // Critical for stdio transport: any provider that writes to stdout will corrupt the
    // JSON-RPC channel. Clear all providers; the MCP SDK routes its own diagnostics
    // appropriately.
    builder.Logging.ClearProviders();
    builder.Logging.AddConsole(o => o.LogToStandardErrorThreshold = LogLevel.Trace);

    builder.Services.AddMcpServer(o => o.ServerInfo = new() { Name = "SkillsServer", Version = "1.0.0" })
    .WithStdioServerTransport()
    .WithResources<SkillResources>();

    await builder.Build().RunAsync();
}

#pragma warning disable CA1812 // Discovered by MCP SDK via [McpServerResourceType] attribute
[McpServerResourceType]
internal sealed class SkillResources
#pragma warning restore CA1812
{
    private const string IndexJson = """
        {
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "name": "unit-converter",
                    "type": "skill-md",
                    "description": "Convert between common units using a multiplication factor. Use when asked to convert miles, kilometers, pounds, or kilograms.",
                    "url": "skill://unit-converter/SKILL.md"
                }
            ]
        }
        """;

    private const string SkillMd = """
        ---
        name: unit-converter
        description: Convert between common units using a multiplication factor. Use when asked to convert miles, kilometers, pounds, or kilograms.
        ---

        ## Usage

        When the user requests a unit conversion, use these factors:

        | From        | To          | Factor   |
        |-------------|-------------|----------|
        | miles       | kilometers  | 1.60934  |
        | kilometers  | miles       | 0.621371 |
        | pounds      | kilograms   | 0.453592 |
        | kilograms   | pounds      | 2.20462  |

        Formula: result = value × factor
        """;

    [McpServerResource(UriTemplate = "skill://index.json", Name = "Skill Index", MimeType = "application/json")]
    [Description("SEP-2640 skill discovery index")]
    public static string GetIndex() => IndexJson;

    [McpServerResource(UriTemplate = "skill://unit-converter/SKILL.md", Name = "Unit Converter Skill", MimeType = "text/markdown")]
    [Description("Unit converter skill instructions")]
    public static string GetSkillMd() => SkillMd;
}
