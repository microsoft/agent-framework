// Copyright (c) Microsoft. All rights reserved.

using AGUI.WorkflowFailure;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();

Workflow workflow = FailingWorkflow.Create(new FailingAgent());
AIAgent workflowAgent = workflow.AsAIAgent(name: "FailingWorkflow");

WebApplication app = builder.Build();
app.MapAGUIServer("/", workflowAgent);
await app.RunAsync();
