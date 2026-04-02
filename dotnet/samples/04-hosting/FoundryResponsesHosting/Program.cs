// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates hosting agent-framework agents as Foundry Hosted Agents
// using the Azure AI Responses Server SDK.
//
// Demos:
//   /              - Homepage listing all demos
//   /tool-demo     - Agent with local tools + remote MCP tools
//   /workflow-demo - Triage workflow routing to specialist agents
//
// Prerequisites:
//   - Azure OpenAI resource with a deployed model
//
// Environment variables:
//   - AZURE_OPENAI_ENDPOINT   - your Azure OpenAI endpoint
//   - AZURE_OPENAI_DEPLOYMENT - the model deployment name (default: "gpt-4o")

using System.ComponentModel;
using Azure.AI.AgentServer.Responses;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AzureAIResponses;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

var builder = WebApplication.CreateBuilder(args);

// ---------------------------------------------------------------------------
// 1. Register the Azure AI Responses Server SDK
// ---------------------------------------------------------------------------
builder.Services.AddResponsesServer();

// ---------------------------------------------------------------------------
// 2. Create the shared Azure OpenAI chat client
// ---------------------------------------------------------------------------
var endpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set."));
var deployment = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT") ?? "gpt-4o";

var azureClient = new AzureOpenAIClient(endpoint, new DefaultAzureCredential());
IChatClient chatClient = azureClient.GetChatClient(deployment).AsIChatClient();

// ---------------------------------------------------------------------------
// 3. DEMO 1: Tool Agent — local tools + Microsoft Learn MCP
// ---------------------------------------------------------------------------
Console.WriteLine("Connecting to Microsoft Learn MCP server...");
McpClient mcpClient = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("https://learn.microsoft.com/api/mcp"),
    Name = "Microsoft Learn MCP",
}));
var mcpTools = await mcpClient.ListToolsAsync();
Console.WriteLine($"MCP tools available: {string.Join(", ", mcpTools.Select(t => t.Name))}");

builder.AddAIAgent(
    name: "tool-agent",
    instructions: """
        You are a helpful assistant hosted as a Foundry Hosted Agent.
        You have access to several tools - use them proactively:
        - GetCurrentTime: Returns the current date/time in any timezone.
        - GetWeather: Returns weather conditions for any location.
        - Microsoft Learn MCP tools: Search and fetch Microsoft documentation.
        When a user asks a technical question about Microsoft products, use the
        documentation search tools to give accurate, up-to-date answers.
        """,
    chatClient: chatClient)
    .WithAITool(AIFunctionFactory.Create(GetCurrentTime))
    .WithAITool(AIFunctionFactory.Create(GetWeather))
    .WithAITools(mcpTools.Cast<AITool>().ToArray());

// ---------------------------------------------------------------------------
// 4. DEMO 2: Triage Workflow — routes to specialist agents
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

builder.AddAIAgent("triage-workflow", (_, key) =>
    triageWorkflow.AsAIAgent(name: key));

// ---------------------------------------------------------------------------
// 5. Wire up the agent-framework handler as the IResponseHandler
// ---------------------------------------------------------------------------
builder.Services.AddAgentFrameworkHandler();

var app = builder.Build();

// Dispose the MCP client on shutdown
app.Lifetime.ApplicationStopping.Register(() =>
    mcpClient.DisposeAsync().AsTask().GetAwaiter().GetResult());

// ---------------------------------------------------------------------------
// 6. Routes
// ---------------------------------------------------------------------------
app.MapGet("/ready", () => Results.Ok("ready"));
app.MapResponsesServer();

app.MapGet("/", () => Results.Content(Pages.Home, "text/html"));
app.MapGet("/tool-demo", () => Results.Content(Pages.ToolDemo, "text/html"));
app.MapGet("/workflow-demo", () => Results.Content(Pages.WorkflowDemo, "text/html"));
app.MapGet("/js/sse-validator.js", () => Results.Content(Pages.ValidationScript, "application/javascript"));

// Validation endpoint: accepts captured SSE lines and validates them
app.MapPost("/api/validate", (FoundryResponsesHosting.CapturedSseStream captured) =>
{
    var validator = new FoundryResponsesHosting.ResponseStreamValidator();
    foreach (var evt in captured.Events)
    {
        validator.ProcessEvent(evt.EventType, evt.Data);
    }

    validator.Complete();
    return Results.Json(validator.GetResult());
});

app.Run();

// ---------------------------------------------------------------------------
// Local tool definitions
// ---------------------------------------------------------------------------

[Description("Gets the current date and time in the specified timezone.")]
static string GetCurrentTime(
    [Description("IANA timezone (e.g. 'America/New_York', 'Europe/London', 'UTC'). Defaults to UTC.")]
    string timezone = "UTC")
{
    try
    {
        var tz = TimeZoneInfo.FindSystemTimeZoneById(timezone);
        return TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, tz).ToString("F");
    }
    catch
    {
        return DateTime.UtcNow.ToString("F") + " (UTC - unknown timezone: " + timezone + ")";
    }
}

[Description("Gets the current weather for a location. Returns temperature, conditions, and humidity.")]
static string GetWeather(
    [Description("The city or location (e.g. 'Seattle', 'London, UK').")]
    string location)
{
    // Simulated weather - deterministic per location for demo consistency
    var rng = new Random(location.ToUpperInvariant().GetHashCode());
    var temp = rng.Next(-5, 35);
    string[] conditions = ["sunny", "partly cloudy", "overcast", "rainy", "snowy", "windy", "foggy"];
    var condition = conditions[rng.Next(conditions.Length)];
    return $"Weather in {location}: {temp}C, {condition}. Humidity: {rng.Next(30, 90)}%. Wind: {rng.Next(5, 30)} km/h.";
}
