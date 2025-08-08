// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI.Agents.A2A.Internal;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Provides extension methods for configuring A2A (Agent-to-Agent) communication in a host application builder.
/// </summary>
public static class A2AHostingApplicationBuilderExtensions
{
    /// <summary>
    /// Attaches A2A communication via AgentTasks
    /// </summary>
    /// <param name="app"></param>
    /// <param name="path"></param>
    /// <param name="agentName"></param>
    public static void AttachA2ATasks(this WebApplication app, string path, string agentName)
    {
        var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        var logger = app.Services.GetRequiredService<ILogger<A2AAgentTaskProcessor>>();

        var agentA2AConnector = new A2AAgentTaskProcessor(logger, agent);
        var taskStore = new InMemoryTaskStore();

        app.AttachA2A(path, agentA2AConnector, taskStore);
    }

    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities to the specified host application builder.
    /// </summary>
    /// <param name="app"></param>
    /// <param name="path"></param>
    /// <param name="agentName"></param>
    public static void AttachA2AMessaging(this WebApplication app, string path, string agentName)
    {
        var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        var logger = app.Services.GetRequiredService<ILogger<A2AMessageProcessor>>();

        var agentA2AConnector = new A2AMessageProcessor(logger, agent);

        app.AttachA2A(path, agentA2AConnector);
    }

    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities to the specified host application builder.
    /// </summary>
    /// <param name="app"></param>
    /// <param name="path"></param>
    /// <param name="a2aConnector"></param>
    public static void AttachA2A(this WebApplication app, string path, IA2AMessageProcessor a2aConnector)
    {
        var taskManager = new TaskManager();
        AttachMessageProcessor(a2aConnector, taskManager);

        app.AttachA2A(taskManager, path);
    }

    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities to the specified host application builder.
    /// </summary>
    /// <param name="app"></param>
    /// <param name="path"></param>
    /// <param name="a2aConnector"></param>
    /// <param name="taskStore"></param>
    public static void AttachA2A(this WebApplication app, string path, IA2AAgentTaskProcessor a2aConnector, ITaskStore taskStore)
    {
        var taskManager = new TaskManager(taskStore: taskStore);
        AttachAgentTaskProcessor(a2aConnector, taskManager);

        app.AttachA2A(taskManager, path);
    }

    /// <summary>
    /// Maps HTTP A2A communication endpoints to the specified path using the provided TaskManager.
    /// TaskManager should be preconfigured before calling this method.
    /// </summary>
    /// <param name="app"></param>
    /// <param name="taskManager"></param>
    /// <param name="path"></param>
    public static void AttachA2A(this WebApplication app, TaskManager taskManager, string path)
    {
        app.MapA2A(taskManager, path);
        app.MapHttpA2A(taskManager, path);
    }

    private static void AttachAgentTaskProcessor(IA2AAgentTaskProcessor a2aConnector, TaskManager taskManager)
    {
        taskManager.OnAgentCardQuery += a2aConnector.GetAgentCardAsync;

        taskManager.OnTaskCreated += a2aConnector.CreateTaskAsync;
        taskManager.OnTaskUpdated += a2aConnector.UpdateTaskAsync;
        taskManager.OnTaskCancelled += a2aConnector.CancelTaskAsync;
    }

    private static void AttachMessageProcessor(IA2AMessageProcessor a2aConnector, TaskManager taskManager)
    {
        taskManager.OnAgentCardQuery += a2aConnector.GetAgentCardAsync;
        taskManager.OnMessageReceived += a2aConnector.ProcessMessageAsync;
    }
}
