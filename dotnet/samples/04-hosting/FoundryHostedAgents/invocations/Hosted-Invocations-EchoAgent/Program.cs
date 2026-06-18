// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Invocations;
using DotNetEnv;
using HostedInvocationsEchoAgent;
using Microsoft.Agents.AI;

// Load .env file if present (for local development)
Env.TraversePath().Load();

var builder = WebApplication.CreateBuilder(args);

// Register the echo agent as a singleton (no LLM needed).
builder.Services.AddSingleton<EchoAIAgent>();

// Register the Invocations SDK services and wire the handler.
builder.Services.AddInvocationsServer();
builder.Services.AddScoped<InvocationHandler, EchoInvocationHandler>();

var app = builder.Build();

// Map the Invocations protocol endpoints:
//   POST /invocations              — invoke the agent
//   GET  /invocations/{id}         — get result (not used by this sample)
//   POST /invocations/{id}/cancel  — cancel (not used by this sample)
app.MapInvocationsServer();

app.Run();
