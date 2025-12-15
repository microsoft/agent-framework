// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using LogLevel = Microsoft.Extensions.Logging.LogLevel;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for adding logging support to <see cref="AIAgentBuilder"/> instances.
/// </summary>
public static class LoggingAgentBuilderExtensions
{
    /// <summary>
    /// Adds logging to the agent pipeline, enabling detailed observability of agent operations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which logging support will be added.</param>
    /// <param name="loggerFactory">
    /// An optional <see cref="ILoggerFactory"/> used to create a logger with which logging should be performed.
    /// If not supplied, a required instance will be resolved from the service provider.
    /// </param>
    /// <param name="configure">
    /// An optional callback that provides additional configuration of the <see cref="LoggingAgent"/> instance.
    /// This allows for fine-tuning logging behavior such as customizing JSON serialization options.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> with logging support added, enabling method chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// When the employed <see cref="ILogger"/> enables <see cref="LogLevel.Trace"/>, the contents of
    /// messages, options, and responses are logged. These may contain sensitive application data.
    /// <see cref="LogLevel.Trace"/> is disabled by default and should never be enabled in a production environment.
    /// Messages and options are not logged at other logging levels.
    /// </para>
    /// <para>
    /// If the resolved or provided <see cref="ILoggerFactory"/> is <see cref="NullLoggerFactory"/>, this will be a no-op where
    /// logging will be effectively disabled. In this case, the <see cref="LoggingAgent"/> will not be added.
    /// </para>
    /// </remarks>
    public static AIAgentBuilder UseLogging(
        this AIAgentBuilder builder,
        ILoggerFactory? loggerFactory = null,
        Action<LoggingAgent>? configure = null)
    {
        _ = Throw.IfNull(builder);

        return builder.Use((innerAgent, services) =>
        {
            loggerFactory ??= services.GetRequiredService<ILoggerFactory>();

            // If the factory we resolve is for the null logger, the LoggingAgent will end up
            // being an expensive nop, so skip adding it and just return the inner agent.
            if (loggerFactory == NullLoggerFactory.Instance)
            {
                return innerAgent;
            }

            LoggingAgent agent = new(innerAgent, loggerFactory.CreateLogger(nameof(LoggingAgent)));
            configure?.Invoke(agent);
            return agent;
        });
    }
}
