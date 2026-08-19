// Copyright (c) Microsoft. All rights reserved.

// Translation Chain Workflow Agent — demonstrates how to compose multiple AI agents
// into a sequential workflow pipeline. Three translation agents are connected:
// French → Spanish → English, showing how agents can be orchestrated as workflow
// executors in a hosted agent. It is deployed to Foundry directly from source
// (code / ZIP upload), so the platform builds and runs your code with no container image.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
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

var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-workflow-simple";

// WARNING: DefaultAzureCredential is convenient for development but requires careful
// consideration in production. Consider a specific credential (for example
// ManagedIdentityCredential) to avoid latency, unintended credential probing, and
// fallback security risks.
IChatClient chatClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetProjectOpenAIClient()
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Create translation agents
AIAgent frenchAgent = chatClient.AsAIAgent("You are a translation assistant that translates the provided text to French.");
AIAgent spanishAgent = chatClient.AsAIAgent("You are a translation assistant that translates the provided text to Spanish.");
AIAgent englishAgent = chatClient.AsAIAgent("You are a translation assistant that translates the provided text to English.");

// Build the sequential workflow: French → Spanish → English
AIAgent agent = new WorkflowBuilder(frenchAgent)
    .AddEdge(frenchAgent, spanishAgent)
    .AddEdge(spanishAgent, englishAgent)
    .Build()
    .AsAIAgent(name: agentName);

// Host the workflow agent using the Responses protocol.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent);

var app = builder.Build();
app.MapFoundryResponses();

app.Run();

// Returns the first candidate that has an actual value, ignoring null and blank entries.
static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, c => !string.IsNullOrWhiteSpace(c))!;
