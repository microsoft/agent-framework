// Copyright (c) Microsoft. All rights reserved.

// Sample: a Foundry Hosted Agent that accepts steering input while a response is still running.
// It deploys directly from source, so Foundry builds and runs the uploaded project.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry.Hosting;

Env.TraversePath().Load();

var projectEndpoint = new Uri(System.Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set."));
var deployment = FirstNonBlank(
    System.Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
    System.Environment.GetEnvironmentVariable("FOUNDRY_MODEL"),
    "gpt-4o");
var agentName = System.Environment.GetEnvironmentVariable("AGENT_NAME") ?? "hosted-steering";

AIAgent agent = new AIProjectClient(projectEndpoint, new DefaultAzureCredential())
    .AsAIAgent(
        model: deployment,
        instructions: """
            You are a helpful AI assistant. When another message arrives while you are working,
            treat it as a course correction and incorporate it into the answer.
            """,
        name: agentName,
        description: "A steerable general-purpose AI assistant");

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddFoundryResponses(agent, configure: options => options.SteerableConversations = true);

var app = builder.Build();
app.MapFoundryResponses();
app.Run();

static string FirstNonBlank(params string?[] candidates) =>
    Array.Find(candidates, candidate => !string.IsNullOrWhiteSpace(candidate))!;
