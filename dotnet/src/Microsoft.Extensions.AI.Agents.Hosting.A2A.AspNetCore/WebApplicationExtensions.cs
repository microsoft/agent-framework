// Copyright (c) Microsoft. All rights reserved.

using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.Hosting.A2A.AspNetCore;

/// <summary>
/// Provides extension methods for configuring A2A (Agent-to-Agent) communication in a host application builder.
/// </summary>
public static class WebApplicationExtensions
{
    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="app">The web application used to configure the pipeline and routes.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    public static void AttachA2A(this WebApplication app, string agentName, string path)
    {
        var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
        var actorClient = app.Services.GetRequiredService<IActorClient>();

        var taskManager = agent.AttachA2A(actorClient, loggerFactory: loggerFactory);
        app.AttachA2A(taskManager, path);
    }

    /// <summary>
    /// Attaches A2A (Agent-to-Agent) communication capabilities via Message processing to the specified web application.
    /// </summary>
    /// <param name="app">The web application used to configure the pipeline and routes.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route group to use for A2A endpoints.</param>
    /// <param name="agentCard">Agent card info to return on query.</param>
    public static void AttachA2A(
        this WebApplication app,
        string agentName,
        string path,
        AgentCard agentCard)
    {
        var agent = app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        var loggerFactory = app.Services.GetRequiredService<ILoggerFactory>();
        var actorClient = app.Services.GetRequiredService<IActorClient>();

        var taskManager = agent.AttachA2A(actorClient, agentCard: agentCard, loggerFactory: loggerFactory);
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
        // note: current SDK version registers multiple `.well-known/agent.json` handlers here.
        // it makes app return HTTP 500, but will be fixed once new A2A SDK is released.
        // see https://github.com/microsoft/agent-framework/issues/476 for details
        app.MapA2A(taskManager, path);

        app.MapHttpA2A(taskManager, path);
    }
}
