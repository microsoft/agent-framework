// Copyright (c) Microsoft. All rights reserved.

// Steerable Conversation Agent — a chat agent hosted as a Foundry Hosted Agent that accepts
// steering: a new input sent while a turn is still running is queued behind the current turn
// instead of being rejected, and the agent picks it up at the next safe point.
//
// What "steering" adds here:
//   - The agent is hosted with SteerableConversations = true. A follow-up request for the same
//     conversation that is still in progress is accepted (status "queued") rather than rejected
//     with a conversation-locked error.
//   - Steering is independent of resilience: you can enable either option on its own. This sample
//     turns on only steering to keep the behavior focused; see Hosted-Workflow-Resilient for
//     crash recovery.
//   - Opt-in, off by default. Without SteerableConversations an overlapping turn is rejected, as
//     in the non-steering samples.

using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var projectEndpoint = new Uri(Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));

var agentName = Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-steering";

var deployment = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-4o";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
TokenCredential credential = new ChainedTokenCredential(
    new DevTemporaryTokenCredential(),
    new DefaultAzureCredential());

// Create the agent via the AI project client using the Responses API.
AIAgent agent = new AIProjectClient(projectEndpoint, credential)
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful AI assistant hosted as a Foundry Hosted Agent.
            When you receive an additional message while already working, treat it as a course
            correction and fold it into your ongoing answer. Be concise, clear, and helpful.
            """,
        name: agentName,
        description: "A steerable general-purpose AI assistant");

// Host the agent as a Foundry Hosted Agent using the Responses API.
// SteerableConversations opts this host into mid-turn steering; it is the only difference from
// the non-steering Hosted-ChatClientAgent sample.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent, configure: o => o.SteerableConversations = true);

var app = builder.Build();
app.MapFoundryResponses();

// Contributor-only: in Development, also map the per-agent OpenAI route shape that live Foundry uses
// so a local REPL client can target this server via AIProjectClient.AsAIAgent(Uri agentEndpoint).
// Do not use this in production. Hosted Foundry agents only support the agent-endpoint path.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
