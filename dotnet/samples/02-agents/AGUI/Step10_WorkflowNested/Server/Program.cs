// Copyright (c) Microsoft. All rights reserved.

using AGUI.WorkflowNested;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();

AIAgent workflowAgent = NestedWorkflow.Create().AsAIAgent(
    name: "NestedWorkflow",
    includeWorkflowOutputsInResponse: true);

WebApplication app = builder.Build();
app.MapAGUIServer("/", workflowAgent);
await app.RunAsync();
