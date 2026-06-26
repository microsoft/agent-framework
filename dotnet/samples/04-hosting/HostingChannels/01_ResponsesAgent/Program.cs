// Copyright (c) Microsoft. All rights reserved.

// Exposes an AIAgent on the OpenAI Responses-shaped channel.
//   POST /responses  { "input": "Hi" }                 -> Responses JSON
//   POST /responses  { "input": "Hi", "stream": true } -> SSE stream
// Session continuity is keyed by ChannelSession.IsolationKey; identical keys resolve to the same
// cached AgentSession. This sample lets the channel derive the session from previous_response_id.

#pragma warning disable CA1031

using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-5.4-mini";

// The hosting channel only needs an OpenAI-compatible chat client, so it depends on the OpenAI SDK
// directly rather than Azure.AI.OpenAI. No Azure-specific features are required here.
AIAgent agent = new OpenAIClient(new ApiKeyCredential(apiKey))
    .GetChatClient(model)
    .AsAIAgent(name: "Concierge", instructions: "You are a helpful concierge.");

var builder = WebApplication.CreateBuilder(args);

builder.AddAgentFrameworkHost(agent)
    .AddResponsesChannel();

var app = builder.Build();
app.MapAgentFrameworkHost();
app.Run();