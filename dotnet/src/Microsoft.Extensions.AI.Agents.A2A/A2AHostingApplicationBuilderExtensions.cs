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
    /// <param name="a2aConnector"></param>
    /// <param name="taskStore"></param>
    /// <param name="path"></param>
    public static void AttachHttpA2A(
        this WebApplication app,
        IA2AConnector a2aConnector,
        ITaskStore? taskStore,
        string path)
    {
        var taskManager = new TaskManager(taskStore: taskStore);
        Attach(a2aConnector, taskManager);

        app.AttachHttpA2A(taskManager, path);
    }

    /// <summary>
    /// Maps HTTP A2A communication endpoints to the specified path using the provided TaskManager.
    /// TaskManager should be preconfigured before calling this method.
    /// </summary>
    /// <param name="app"></param>
    /// <param name="taskManager"></param>
    /// <param name="path"></param>
    public static void AttachHttpA2A(
        this WebApplication app,
        TaskManager taskManager,
        string path)
    {
        app.MapHttpA2A(taskManager, path);
    }

    private static void Attach(IA2AConnector a2aConnector, TaskManager taskManager)
    {
        taskManager.OnAgentCardQuery += a2aConnector.GetAgentCardAsync;
        taskManager.OnMessageReceived += a2aConnector.ProcessMessageAsync;
    }
}
