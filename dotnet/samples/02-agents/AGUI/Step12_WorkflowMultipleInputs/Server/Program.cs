// Copyright (c) Microsoft. All rights reserved.

using AGUI.WorkflowMultipleInputs;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.Agents.AI.Workflows;

WebApplicationBuilder builder = WebApplication.CreateBuilder(args);
builder.Services.AddHttpClient().AddLogging();
builder.Services.AddAGUIServer();
builder.Services.AddAIAgent(
        "MultipleInputsWorkflow",
        static (_, _) => MultipleInputsWorkflow.Create().AsAIAgent(name: "MultipleInputsWorkflow"))
    .WithInMemorySessionStore(withIsolation: false);

WebApplication app = builder.Build();
app.MapAGUIServer("MultipleInputsWorkflow", "/");
await app.RunAsync();
