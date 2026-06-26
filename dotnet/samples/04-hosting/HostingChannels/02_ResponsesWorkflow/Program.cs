// Copyright (c) Microsoft. All rights reserved.

// Exposes a Workflow on the OpenAI Responses-shaped channel. A run hook turns the parsed Responses
// input (ChatMessage list) into the workflow's typed string input. Workflow checkpoint storage lives on
// the workflow; the host derives a per-isolation-key checkpoint location from StatePaths.

#pragma warning disable CA1031

using Microsoft.Agents.AI.Hosting.Channels;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Agents.AI.Workflows;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Hosting;
using ResponsesWorkflowSample;

var builder = WebApplication.CreateBuilder(args);

// Application-defined single-executor workflow that echoes its input.
var echo = new EchoExecutor();
var workflow = new WorkflowBuilder(echo).WithOutputFrom(echo).Build();

builder.AddAgentFrameworkHost(workflow, o => o.StatePaths = new HostStatePathOptions { Root = "./.afhost" })
    .AddResponsesChannel(o => o.RunHook = new WorkflowInputRunHook());

var app = builder.Build();
app.MapAgentFrameworkHost();
app.Run();