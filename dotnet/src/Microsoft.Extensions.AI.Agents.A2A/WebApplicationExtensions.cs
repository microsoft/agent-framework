// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI.Agents.A2A.Internal.Connectors;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Provides extension methods for configuring A2A (Agent-to-Agent) communication in a host application builder.
/// </summary>
public static class WebApplicationExtensions
{
    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities via Agent-Task processing to the specified web application.
    /// </summary>
    /// <param name="app">The web application used to configure the pipeline and routes.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    public static void AttachA2ATasks(this WebApplication app, string path, string agentName)
    {
        // user provided taskStore
        var taskStore = app.Services.GetKeyedService<ITaskStore>(agentName) ?? new InMemoryTaskStore();
        var taskManager = new TaskManager(taskStore: taskStore);

        // user provided a2aConnector
        var a2aConnector = app.Services.GetKeyedService<IA2AAgentTaskProcessor>(agentName);
        if (a2aConnector is null)
        {
            var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
            var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
            a2aConnector = new A2AAgentTaskProcessor(agent, taskManager, loggerFactory);
        }

        // attach A2A.SDK calls of TaskManager to the A2A connector
        AttachAgentTaskProcessor(a2aConnector, taskManager);

        app.AttachA2A(taskManager, path);
    }

    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="app">The web application used to configure the pipeline and routes.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    public static void AttachA2AMessaging(this WebApplication app, string path, string agentName)
    {
        var taskManager = new TaskManager();

        var a2aConnector = app.Services.GetKeyedService<IA2AMessageProcessor>(agentName);
        if (a2aConnector is null)
        {
            var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
            var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
            a2aConnector = new A2AMessageProcessor(agent, taskManager, loggerFactory);
        }

        // attach A2A.SDK calls of TaskManager to the A2A connector
        AttachMessageProcessor(a2aConnector, taskManager);

        app.AttachA2A(taskManager, path);
    }

    /// <summary>
    /// Maps HTTP A2A communication endpoints to the specified path using the provided TaskManager.
    /// TaskManager should be preconfigured before calling this method.
    /// </summary>
    /// <param name="app">The web application used to configure the pipeline and routes.</param>
    /// <param name="taskManager">Pre-configured A2A TaskManager to use for A2A endpoints handling.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
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
