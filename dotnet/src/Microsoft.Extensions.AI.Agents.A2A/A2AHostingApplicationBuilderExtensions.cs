// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Microsoft.AspNetCore.Builder;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Provides extension methods for configuring A2A (Agent-to-Agent) communication in a host application builder.
/// </summary>
public static class A2AHostingApplicationBuilderExtensions
{
    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities to the specified host application builder.
    /// </summary>
    /// <param name="app"></param>
    /// <param name="agentName"></param>
    /// <param name="path"></param>
    public static void AttachA2A(
        this WebApplication app,
        string agentName,
        string path)
    {
        var agentKey = $"agent:{agentName}";
        // var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentKey);
        // var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();

        //var a2aConnector = new A2AConnector(loggerFactory.CreateLogger<A2AConnector>(), agent);
        //var taskStore = new A2ATaskStore(loggerFactory.CreateLogger<A2ATaskStore>(), agent);

        //var taskManager = new TaskManager(taskStore: taskStore);
        //a2aConnector.Attach(taskManager);

        var taskManager = new TaskManager();
        app.MapHttpA2A(taskManager, path);
    }
}
