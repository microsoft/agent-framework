// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to host an AI agent with Azure Functions (DurableAgents).
//
// Prerequisites:
//   - Azure Functions Core Tools
//   - OpenAI API key
//
// Environment variables:
//   OPENAI_API_KEY
//   OPENAI_MODEL (defaults to "gpt-4o-mini")
//
// Run with: func start
// Then call: POST http://localhost:7071/api/agents/HostedAgent/run

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

// Set up an AI agent following the standard Microsoft Agent Framework pattern.
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(
        instructions: "You are a helpful assistant hosted in Azure Functions.",
        name: "HostedAgent");

// Configure the function app to host the AI agent.
// This will automatically generate HTTP API endpoints for the agent.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    .ConfigureDurableAgents(options => options.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)))
    .Build();
app.Run();
