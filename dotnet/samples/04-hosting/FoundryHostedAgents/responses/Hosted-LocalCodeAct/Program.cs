// Copyright (c) Microsoft. All rights reserved.

// Hosted Local CodeAct sample. Wires Microsoft.Agents.AI.LocalCodeAct into a
// Foundry hosted agent. The model only sees a single `execute_code` tool;
// `compute` and `fetch_data` are registered as sandbox-only host tools that
// generated Python reaches via `await call_tool(...)`. This mirrors the Python
// `foundry_hosted_agent.py` sample for the local-codeact package.
//
// SECURITY: LocalCodeAct executes LLM-generated Python in the agent process.
// Only deploy this sample to an externally sandboxed environment such as a
// Foundry hosted-agent container.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.LocalCodeAct;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o";
string pythonExecutable = Environment.GetEnvironmentVariable("LOCAL_CODEACT_PYTHON")
    ?? (OperatingSystem.IsWindows() ? "python.exe" : "python3");

TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// ── Sandbox-only tools (model never sees these directly) ─────────────────────

[Description("Perform a math operation: add, subtract, multiply, or divide.")]
static double Compute(
    [Description("Operation: add, subtract, multiply, or divide.")] string operation,
    [Description("First numeric operand.")] double a,
    [Description("Second numeric operand.")] double b) => operation switch
    {
        "add" => a + b,
        "subtract" => a - b,
        "multiply" => a * b,
        "divide" => b == 0 ? double.PositiveInfinity : a / b,
        _ => throw new ArgumentException($"Unknown operation '{operation}'.", nameof(operation)),
    };

[Description("Fetch records from a named simulated table (users or products).")]
static IReadOnlyList<IReadOnlyDictionary<string, object>> FetchData(
    [Description("Name of the simulated table to query.")] string table)
{
    Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object>>> data = new()
    {
        ["users"] =
        [
            new Dictionary<string, object> { ["id"] = 1, ["name"] = "Alice", ["role"] = "admin" },
            new Dictionary<string, object> { ["id"] = 2, ["name"] = "Bob", ["role"] = "user" },
            new Dictionary<string, object> { ["id"] = 3, ["name"] = "Charlie", ["role"] = "admin" },
        ],
        ["products"] =
        [
            new Dictionary<string, object> { ["id"] = 101, ["name"] = "Widget", ["price"] = 9.99 },
            new Dictionary<string, object> { ["id"] = 102, ["name"] = "Gadget", ["price"] = 19.99 },
        ],
    };

    return data.TryGetValue(table, out var rows) ? rows : [];
}

// ── LocalCodeAct provider with sandbox-only host tools ───────────────────────

var codeActOptions = new LocalCodeActProviderOptions
{
    Tools =
    [
        AIFunctionFactory.Create(Compute, name: "compute"),
        AIFunctionFactory.Create(FetchData, name: "fetch_data"),
    ],
    ExecutionLimits = new ProcessExecutionLimits { TimeoutSeconds = 5 },
};

var codeAct = new LocalCodeActProvider(pythonExecutable, codeActOptions);

// ── Build the hosted agent ───────────────────────────────────────────────────

AIAgent agent = new AIProjectClient(new Uri(endpoint), credential)
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-local-codeact",
        Description = "Hosted CodeAct agent with sandbox-only compute and fetch_data tools.",
        ChatOptions = new ChatOptions
        {
            ModelId = deploymentName,
            Instructions =
                """
                You are a helpful assistant. Keep your answers brief. Prefer orchestrating your work
                in a single `execute_code` block using `await call_tool(...)` over issuing many
                direct tool calls. The sandbox exposes `compute` and `fetch_data` via `call_tool`.
                """,
        },
        AIContextProviders = [codeAct],
    });

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
