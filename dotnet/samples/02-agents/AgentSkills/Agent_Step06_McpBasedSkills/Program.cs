// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to discover Agent Skills served over MCP.
//
// When launched with "--server", this executable runs a small MCP stdio server
// that advertises the Skills extension and exposes a unit-converter skill:
//   - skills/list - discovery method listing all skills
//   - skill://unit-converter/SKILL.md - the skill instructions
//   - skill://unit-converter/references/conversion-table.md - conversion factors
//
// In default (client) mode the sample launches itself as a child process,
// connects via StdioClientTransport, and uses AgentSkillsProviderBuilder
// to discover and inject the skill into a ChatClientAgent.

using System.ComponentModel;
using System.Text.Json.Nodes;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

if (args.Length > 0 && args[0] == "--server")
{
    await RunMcpServerAsync();
    return;
}

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

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
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "SkillsAgent",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful assistant. Use available skills to answer the user.",
        },
        AIContextProviders = [skillsProvider],
    })
    .AsBuilder()
    .UseToolApproval(new ToolApprovalAgentOptions
    {
        // NOTE: Auto-approving all skill tools is done here for simplicity in
        // this demonstration. In production, you should prompt the user before
        // allowing skill tools to execute. See Agent_Step07_SkillsAutoApproval
        // for a walkthrough of the full approval flow.
        AutoApprovalRules = [AgentSkillsProvider.AllToolsAutoApprovalRule],
    })
    .Build();

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

#pragma warning disable MCPEXP002 // Custom extension methods require raw server request handlers.
    builder.Services.AddMcpServer(o =>
    {
        o.ServerInfo = new() { Name = "SkillsServer", Version = "1.0.0" };
        o.Capabilities = new ServerCapabilities
        {
            Resources = new(),
            Extensions = new Dictionary<string, object>
            {
                ["io.modelcontextprotocol/skills"] = new JsonObject(),
            },
        };
        o.RequestHandlers =
        [
            new()
            {
                Method = "skills/list",
                Handler = (_, _) => ValueTask.FromResult(SkillResources.ListSkills()),
            },
        ];
    })
    .WithStdioServerTransport()
    .WithResources<SkillResources>();
#pragma warning restore MCPEXP002

    await builder.Build().RunAsync();
}

#pragma warning disable CA1812 // Discovered by MCP SDK via [McpServerResourceType] attribute
[McpServerResourceType]
internal sealed class SkillResources
#pragma warning restore CA1812
{
    private const string SkillName = "unit-converter";
    private const string SkillDescription =
        "Convert between common units using a multiplication factor. Use when asked to convert miles, kilometers, pounds, or kilograms.";
    private const string SkillUri = "skill://unit-converter/SKILL.md";
    private const string ConversionTableUri = "skill://unit-converter/references/conversion-table.md";

    private const string SkillMd = $$"""
        ---
        name: {{SkillName}}
        description: {{SkillDescription}}
        ---

        ## Usage

        When the user requests a unit conversion:
        1. First, review `references/conversion-table.md` to find the correct factor
        2. Calculate the result by multiplying the value by the factor
        3. Present the converted value clearly with both units
        """;

    private const string ConversionTable = """
        # Conversion Tables

        Formula: **result = value × factor**

        | From        | To          | Factor   |
        |-------------|-------------|----------|
        | miles       | kilometers  | 1.60934  |
        | kilometers  | miles       | 0.621371 |
        | pounds      | kilograms   | 0.453592 |
        | kilograms   | pounds      | 2.20462  |
        """;

    private const string SkillsListJson = $$"""
        {
            "resultType": "complete",
            "skills": [
                {
                    "uri": "{{SkillUri}}",
                    "frontmatter": {
                        "name": "{{SkillName}}",
                        "description": "{{SkillDescription}}"
                    },
                    "resources": [
                        {
                            "uri": "{{SkillUri}}"
                        },
                        {
                            "uri": "{{ConversionTableUri}}"
                        }
                    ]
                }
            ]
        }
        """;

    /// <summary>
    /// Lists the available skills and their resource metadata.
    /// </summary>
    public static JsonNode? ListSkills() => JsonNode.Parse(SkillsListJson);

    /// <summary>
    /// Returns the unit-converter skill instructions.
    /// </summary>
    [McpServerResource(UriTemplate = SkillUri, Name = "Unit Converter Skill", MimeType = "text/markdown")]
    [Description("Unit converter skill instructions")]
    public static string GetSkillMd() => SkillMd;

    /// <summary>
    /// Returns the conversion factors used by the unit-converter skill.
    /// </summary>
    [McpServerResource(UriTemplate = ConversionTableUri, Name = "Conversion Table", MimeType = "text/markdown")]
    [Description("Unit conversion factors")]
    public static string GetConversionTable() => ConversionTable;
}
