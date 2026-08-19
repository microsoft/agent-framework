// Copyright (c) Microsoft. All rights reserved.

using AGUI.WorkflowApproval;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();
builder.Services.AddAIAgent(
        "ApprovalWorkflow",
        static (_, _) => ApprovalWorkflow.Create().AsAIAgent(
            name: "ApprovalWorkflow",
            includeWorkflowOutputsInResponse: true))
    .WithInMemorySessionStore(withIsolation: false);

WebApplication app = builder.Build();
app.MapAGUIServer("ApprovalWorkflow", "/");
await app.RunAsync();
