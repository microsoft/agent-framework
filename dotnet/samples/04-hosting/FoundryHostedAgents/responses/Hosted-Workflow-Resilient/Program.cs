// Copyright (c) Microsoft. All rights reserved.

// Resilient Translation Chain Workflow Agent — the same sequential translation workflow as
// Hosted-Workflow-Simple, hosted as a durable long-running (resilient) Foundry Hosted Agent.
//
// What "resilient" adds here:
//   - The workflow is hosted with ResilientBackground = true. For a background response
//     (store=true, background=true), the platform keeps the agent running with no client
//     connected and re-invokes the handler after a container crash or graceful shutdown.
//   - A workflow hosted as an agent checkpoints its progress between executor steps and resumes
//     from its last checkpoint. The hosting handler persists the session at each completed output
//     item, so a crash mid-run loses at most the step that was in flight.
//   - Everything is opt-in: without ResilientBackground the agent behaves exactly like the
//     non-resilient sample.
//
// See the README for the local crash-and-recover walkthrough.

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

string endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// Create a chat client from the Foundry project
IChatClient chatClient = new AIProjectClient(new Uri(endpoint), credential)
    .GetProjectOpenAIClient()
    .GetChatClient(deploymentName)
    .AsIChatClient();

// Create translation agents. Each becomes a workflow step, so each completed translation is a
// natural checkpoint boundary the platform can resume from.
//
// IMPORTANT for resilient workflows: give every agent a STABLE Id. A workflow checkpoint records
// each step by its executor id, and an agent-backed step derives that id from the agent's Id (and
// Name). By default an agent gets a fresh random Id per process, so after a crash the restarted
// process would rebuild the workflow with different ids and the saved checkpoint would no longer
// match, failing the resume. Fixed ids keep the rebuilt workflow identical across restarts.
AIAgent frenchAgent = chatClient.AsAIAgent(options: new()
{
    Id = "french-translator",
    Name = "french-translator",
    ChatOptions = new() { Instructions = "You are a translation assistant that translates the provided text to French." },
});
AIAgent spanishAgent = chatClient.AsAIAgent(options: new()
{
    Id = "spanish-translator",
    Name = "spanish-translator",
    ChatOptions = new() { Instructions = "You are a translation assistant that translates the provided text to Spanish." },
});
AIAgent englishAgent = chatClient.AsAIAgent(options: new()
{
    Id = "english-translator",
    Name = "english-translator",
    ChatOptions = new() { Instructions = "You are a translation assistant that translates the provided text to English." },
});

// Build the sequential workflow: French → Spanish → English
AIAgent agent = new WorkflowBuilder(frenchAgent)
    .AddEdge(frenchAgent, spanishAgent)
    .AddEdge(spanishAgent, englishAgent)
    .Build()
    .AsAIAgent(
        name: Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-workflow-resilient");

// Host the workflow agent as a durable Foundry Hosted Agent using the Responses API.
// ResilientBackground opts this host into crash-recoverable background responses; it is the only
// difference from the non-resilient Hosted-Workflow-Simple sample.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent, configure: o => o.ResilientBackground = true);

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
