// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Extension methods for <see cref="AIAgent"/>.
/// </summary>
public static class AgentExtensions
{
    /// <summary>
    /// Wraps the agent with OpenTelemetry instrumentation.
    /// </summary>
    /// <param name="agent">The agent to wrap.</param>
    /// <param name="loggerFactory">The <see cref="ILogger"/> to use for emitting events.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    /// <param name="enableSensitiveData">When <see langword="true"/> indicates whether potentially sensitive information should be included in telemetry. Default is <see langword="false"/></param>
    /// <returns>An <see cref="OpenTelemetryAgent"/> that wraps the original agent with telemetry.</returns>
    public static OpenTelemetryAgent WithOpenTelemetry(this AIAgent agent, ILoggerFactory? loggerFactory = null, string? sourceName = null, bool? enableSensitiveData = null)
    {
        return new OpenTelemetryAgent(agent, loggerFactory?.CreateLogger(typeof(OpenTelemetryAgent)), sourceName)
        {
            EnableSensitiveData = enableSensitiveData ?? false
        };
    }
}
