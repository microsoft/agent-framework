// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;

// Foundry hosted agent test container for Foundry.Hosting.IntegrationTests.
//
// One image, many scenarios. The IT_SCENARIO environment variable selects which agent
// behavior is wired up at startup. Each scenario corresponds to one test fixture and
// one set of tests in the IT project.
//
// The platform injects FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_NAME, FOUNDRY_AGENT_VERSION,
// PORT, and APPLICATIONINSIGHTS_CONNECTION_STRING. We never set FOUNDRY_* or AGENT_* names
// from the test side because they are reserved by the platform.

var scenario = Environment.GetEnvironmentVariable("IT_SCENARIO") ?? "happy-path";
var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o";

var projectClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());

AIAgent agent = scenario switch
{
    "happy-path" => CreateHappyPathAgent(projectClient, deployment),
    "tool-calling" => CreateToolCallingAgent(projectClient, deployment),
    "tool-calling-approval" => CreateToolCallingApprovalAgent(projectClient, deployment),
    "toolbox" => CreateToolboxAgent(projectClient, deployment),
    "mcp-toolbox" => CreateMcpToolboxAgent(projectClient, deployment),
    "custom-storage" => CreateCustomStorageAgent(projectClient, deployment),
    _ => throw new InvalidOperationException($"Unknown IT_SCENARIO '{scenario}'.")
};

var builder = WebApplication.CreateBuilder(args);

var port = Environment.GetEnvironmentVariable("PORT");
if (!string.IsNullOrEmpty(port))
{
    builder.WebHost.UseUrls($"http://+:{port}");
}

builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();
app.MapGet("/readiness", () => Results.Ok());
app.Run();

static AIAgent CreateHappyPathAgent(AIProjectClient client, string deployment) =>
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful AI assistant. Always reply with exactly the single word ECHO unless the user explicitly asks a question that requires a different answer.",
        name: "happy-path-agent",
        description: "Round trip and conversation test agent.");

static AIAgent CreateToolCallingAgent(AIProjectClient client, string deployment) =>
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful assistant. Use the GetUtcNow and Multiply tools when appropriate.",
        name: "tool-calling-agent",
        description: "Server side tool calling test agent.",
        tools: [
            AIFunctionFactory.Create(GetUtcNow),
            AIFunctionFactory.Create(Multiply)
        ]);

static AIAgent CreateToolCallingApprovalAgent(AIProjectClient client, string deployment) =>
    // TODO: wire approval required AIFunction once the public surface is finalized.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful assistant. Use the SendEmail tool when asked to send a message; it requires user approval before running.",
        name: "tool-calling-approval-agent",
        description: "Approval flow test agent (placeholder).",
        tools: [
            AIFunctionFactory.Create(SendEmail)
        ]);

static AIAgent CreateToolboxAgent(AIProjectClient client, string deployment) =>
    // TODO: wire Foundry toolbox host once API surface is finalized for hosted agents.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a toolbox enabled assistant. Use GetEnvironmentName when asked.",
        name: "toolbox-agent",
        description: "Toolbox test agent (placeholder).",
        tools: [
            AIFunctionFactory.Create(GetEnvironmentName)
        ]);

static AIAgent CreateMcpToolboxAgent(AIProjectClient client, string deployment) =>
    // TODO: wire MCP toolbox client to https://learn.microsoft.com/api/mcp.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are an assistant with access to Microsoft Learn documentation via MCP.",
        name: "mcp-toolbox-agent",
        description: "MCP toolbox test agent (placeholder).");

static AIAgent CreateCustomStorageAgent(AIProjectClient client, string deployment) =>
    // TODO: substitute custom IResponsesStorageProvider in DI.
    client.AsAIAgent(
        model: deployment,
        instructions: "You are a helpful assistant.",
        name: "custom-storage-agent",
        description: "Custom storage test agent (placeholder).");

[Description("Returns the current UTC date and time as an ISO 8601 string.")]
static string GetUtcNow() => DateTime.UtcNow.ToString("o");

[Description("Multiplies two integers and returns the product.")]
static int Multiply([Description("First operand")] int a, [Description("Second operand")] int b) => a * b;

[Description("Sends an email. Requires user approval.")]
static string SendEmail(
    [Description("Recipient address")] string to,
    [Description("Email subject")] string subject) =>
    $"Email sent to {to} with subject '{subject}'.";

[Description("Returns the deployment environment name.")]
static string GetEnvironmentName() => "integration-test";
