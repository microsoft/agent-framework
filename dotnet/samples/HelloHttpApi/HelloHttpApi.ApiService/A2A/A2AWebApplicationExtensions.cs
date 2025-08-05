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
        var taskManager = new TaskManager();
        var agentKey = $"agent:{agentName}";

        var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentKey);
        var logger = app.Services.GetRequiredService<ILogger<A2AConnector>>();
        var a2aConnector = new A2AConnector(logger, agent);

        a2aConnector.Attach(taskManager);

        app.MapA2A(taskManager, path);
        app.MapHttpA2A(taskManager, path);
    }
}
