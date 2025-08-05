// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Microsoft.Extensions.AI.Agents;

namespace HelloHttpApi.ApiService.A2A;

public static class A2AWebApplicationExtensions
{
    public static void AttachA2A(
        this WebApplication app,
        string agentName,
        string path)
    {
        var agentKey = $"agent:{agentName}";
        var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentKey);
        var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();

        var a2aConnector = new A2AConnector(loggerFactory.CreateLogger<A2AConnector>(), agent);
        var taskStore = new A2ATaskStore(loggerFactory.CreateLogger<A2ATaskStore>(), agent);

        var taskManager = new TaskManager(taskStore: taskStore);
        a2aConnector.Attach(taskManager);

        app.MapA2A(taskManager, path);
        app.MapHttpA2A(taskManager, path);
    }
}
