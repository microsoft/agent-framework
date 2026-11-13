// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates hosting agent-framework agents as Foundry Hosted Agents
// using the Azure AI Responses Server SDK.
//
// Demo:
//   / - Triage workflow routing to specialist agents
//
// Prerequisites:
//   - Foundry project with a deployed model
//
// Environment variables:
//   - FOUNDRY_PROJECT_ENDPOINT - your Foundry project endpoint
//   - FOUNDRY_MODEL            - the model deployment name (default: "gpt-4o")

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var builder = WebApplication.CreateBuilder(args);

// ---------------------------------------------------------------------------
// 1. Create the shared Foundry project chat client
// ---------------------------------------------------------------------------
var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var deployment = FirstNonBlank(
    Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    "gpt-4o");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
IChatClient chatClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .GetProjectOpenAIClient()
    .GetChatClient(deployment)
    .AsIChatClient();

// ---------------------------------------------------------------------------
// 2. Triage Workflow — routes to specialist agents
// ---------------------------------------------------------------------------
ChatClientAgent triageAgent = new(
    chatClient,
    instructions: """
        You are a triage agent that determines which specialist to hand off to.
        Based on the user's question, ALWAYS hand off to one of the available agents.
        Do NOT answer the question yourself - just route it.
        """,
    name: "triage_agent",
    description: "Routes messages to the appropriate specialist agent");

ChatClientAgent codeExpert = new(
    chatClient,
    instructions: """
        You are a coding and technology expert. You help with programming questions,
        explain technical concepts, debug code, and suggest best practices.
        Provide clear, well-structured answers with code examples when appropriate.
        """,
    name: "code_expert",
    description: "Specialist agent for programming and technology questions");

ChatClientAgent creativeWriter = new(
    chatClient,
    instructions: """
        You are a creative writing specialist. You help write stories, poems,
        marketing copy, emails, and other creative content. You have a flair
        for engaging language and vivid descriptions.
        """,
    name: "creative_writer",
    description: "Specialist agent for creative writing and content tasks");

Workflow triageWorkflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(triageAgent)
    .WithHandoffs(triageAgent, [codeExpert, creativeWriter])
    .WithHandoffs([codeExpert, creativeWriter], triageAgent)
    .Build();

AIAgent hostedAgent = triageWorkflow.AsAIAgent(name: "triage-workflow");

// ---------------------------------------------------------------------------
// 3. Wire up the agent-framework handler and Responses Server SDK
// ---------------------------------------------------------------------------
builder.AddFoundryResponses(hostedAgent);

var app = builder.Build();

// ---------------------------------------------------------------------------
// 4. Routes
// ---------------------------------------------------------------------------
app.MapGet("/ready", () => Results.Ok("ready"));
app.MapFoundryResponses();

app.MapGet("/", () => Results.Content(Pages.WorkflowDemo, "text/html"));
app.MapGet("/workflow-demo", () => Results.Content(Pages.WorkflowDemo, "text/html"));
app.MapGet("/js/sse-validator.js", () => Results.Content(Pages.ValidationScript, "application/javascript"));

// Validation endpoint: accepts captured SSE lines and validates them
app.MapPost("/api/validate", (HostedWorkflowHandoff.CapturedSseStream captured) =>
{
    var validator = new HostedWorkflowHandoff.ResponseStreamValidator();
    foreach (var evt in captured.Events)
    {
        validator.ProcessEvent(evt.EventType, evt.Data);
    }

    validator.Complete();
    return Results.Json(validator.GetResult());
});

app.Run();

static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, candidate => !string.IsNullOrWhiteSpace(candidate))!;
