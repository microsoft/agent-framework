// Copyright (c) Microsoft. All rights reserved.

// Hosted Local CodeAct sample. Wires Microsoft.Agents.AI.LocalCodeAct into a
// Foundry hosted agent. The model only sees a single `execute_code` tool;
// `compute` and `fetch_data` are registered as sandbox-only host tools that
// generated Python reaches via `await call_tool(...)`. It is deployed to Foundry
// directly from source (code / ZIP upload), so the platform builds and runs your
// code with no container image.
//
// SECURITY: LocalCodeAct executes LLM-generated Python in the agent process.
// Only deploy this sample to an externally sandboxed environment such as a
// Foundry hosted-agent container.
//
// RUNTIME: this sample runs generated Python with a Python interpreter. The
// hosted dotnet_10 source-deployment runtime provides python3. Local runs use
// python.exe on Windows and python3 elsewhere; LOCAL_CODEACT_PYTHON overrides
// that selection when a different executable is required.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.LocalCodeAct;
using Microsoft.Extensions.AI;

// Load a local .env file when present (local development only). In Foundry the
// platform injects the required environment variables at runtime.
Env.TraversePath().Load();

var endpoint = System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");

// Environment variables can arrive set but blank: azd substitutes an empty string when the azd
// environment does not define the variable referenced from azure.yaml. An empty string is not
// null, so a plain ?? chain would pass the blank straight through and fail deep inside the SDK.
var deploymentName = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-local-codeact";

var pythonExecutable = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("LOCAL_CODEACT_PYTHON"),
    OperatingSystem.IsWindows() ? "python.exe" : "python3");

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

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
AIAgent agent = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = agentName,
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

// Host the agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;
