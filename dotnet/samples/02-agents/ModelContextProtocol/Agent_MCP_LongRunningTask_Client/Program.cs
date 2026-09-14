// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the Microsoft Agent Framework's MCP long-running task support.
//
// A small MCP server (hosted in this same executable when launched with "--server") exposes
// a single task-supporting tool "AnalyzeDataset" that simulates ~15 seconds of work. The
// client (default mode) connects to it over stdio via Microsoft.Agents.AI.Mcp's
// McpClientTaskExtensions.ListAgentToolsWithTasksAsync, hands the wrapped tools to a
// ChatClientAgent, and exercises both invocation styles:
//   * RunAsync          — blocks until the agent's final response is ready.
//   * RunStreamingAsync — yields response updates as the model produces them; the model
//                         still waits for the tool's terminal result before it can begin
//                         producing the final answer, so the perceived "pause" reflects
//                         tool execution time, not stream-channel latency.
//
// In both cases the wrapper transparently:
//   1. Calls tools/call with the io.modelcontextprotocol/tasks extension capability
//   2. Accepts either an inline result or a task handle
//   3. Polls tasks/get until the final result is available
//
// No application-level loop or continuation tokens are required in either mode.

using System.ClientModel.Primitives;
using System.ComponentModel;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Mcp;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Extensions.Tasks;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;
using OpenAI;
using OpenAI.Chat;

if (args.Length > 0 && args[0] == "--server")
{
    await RunMcpServerAsync();
    return;
}

Uri endpoint = AzureOpenAIEndpoint.From(
    Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT"))
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// Launch this same assembly as a stdio MCP server in a child process.
var thisAssemblyPath = typeof(Program).Assembly.Location;
await using var mcpClient = await McpClient.CreateAsync(new StdioClientTransport(new()
{
    Name = "DatasetAnalyzer",
    Command = "dotnet",
    Arguments = [thisAssemblyPath, "--server"],
}));

// Wrap each MCP tool with task-aware behavior. Each invocation opts into the Tasks extension;
// a task-capable server may return a task handle, while other servers can return inline.
var mcpTools = await mcpClient.ListAgentToolsWithTasksAsync();

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new OpenAIClient(
    new BearerTokenPolicy(new DefaultAzureCredential(), "https://ai.azure.com/.default"),
    new OpenAIClientOptions { Endpoint = endpoint })
     .GetChatClient(deploymentName)
     .AsAIAgent(
        instructions: "You answer data-analysis questions by invoking the available tools. Always invoke a tool when one matches the request.",
        tools: [.. mcpTools.Cast<AITool>()]);

const string Prompt = "Analyze the dataset named 'sales-2025-q1' and summarize the findings.";

Console.WriteLine("MCP 2026-07-28 Tasks extension enabled.");
Console.WriteLine();
Console.WriteLine("=== Transparent long-running MCP task (RunAsync) ===");
Console.WriteLine("Asking the agent to analyze a dataset; the tool takes ~15s to complete.");
Console.WriteLine("RunAsync blocks while the wrapper polls the task to completion.");
Console.WriteLine();

var stopwatch = System.Diagnostics.Stopwatch.StartNew();
var response = await agent.RunAsync(Prompt);
stopwatch.Stop();

Console.WriteLine($"Agent response (after {stopwatch.Elapsed.TotalSeconds:F1}s):");
Console.WriteLine(response.Text);

Console.WriteLine();
Console.WriteLine("=== Transparent long-running MCP task (RunStreamingAsync) ===");
Console.WriteLine("Same request via the streaming API. Updates only begin to arrive after the");
Console.WriteLine("tool's task reaches the Completed state, since the model needs the tool result");
Console.WriteLine("before it can produce its final answer.");
Console.WriteLine();

stopwatch.Restart();
await foreach (var update in agent.RunStreamingAsync(Prompt))
{
    Console.Write(update.Text);
}
stopwatch.Stop();

Console.WriteLine();
Console.WriteLine($"(Streaming completed after {stopwatch.Elapsed.TotalSeconds:F1}s.)");

// --- Server mode (launched as a child process via --server) ---------------------------------
static async Task RunMcpServerAsync()
{
    var builder = Host.CreateApplicationBuilder();

    // Critical for stdio transport: any provider that writes to stdout will corrupt the
    // JSON-RPC channel. Clear all providers; the MCP SDK routes its own diagnostics
    // appropriately.
    builder.Logging.ClearProviders();
    builder.Logging.AddConsole(o => o.LogToStandardErrorThreshold = LogLevel.Trace);

    builder.Services.AddMcpServer(o =>
        o.ServerInfo = new Implementation { Name = "DatasetAnalyzer", Version = "1.0.0" })
    .WithStdioServerTransport()
    .WithTools<DatasetAnalysisTools>()
    .WithTasks(new InMemoryMcpTaskStore());

    await builder.Build().RunAsync();
}

#pragma warning disable CA1812 // Discovered by MCP SDK via [McpServerToolType] attribute
[McpServerToolType]
internal sealed class DatasetAnalysisTools
#pragma warning restore CA1812
{
    [McpServerTool(Name = "AnalyzeDataset")]
    [Description("Analyze a tabular dataset and return summary statistics. This tool simulates a long-running analytic job (~15 seconds).")]
    public static async Task<string> AnalyzeDatasetAsync(
        [Description("The dataset identifier, e.g. 'sales-2025-q1'.")] string datasetName,
        CancellationToken cancellationToken)
    {
        await Task.Delay(TimeSpan.FromSeconds(15), cancellationToken).ConfigureAwait(false);

        return $"Findings for '{datasetName}': 12,403 rows; avg revenue $48,712; 3 anomalies detected in week 7; outliers concentrated in EMEA region.";
    }
}
