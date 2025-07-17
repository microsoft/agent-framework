// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Extension methods for <see cref="Agent"/>.
/// </summary>
public static class AgentExtensions
{
    /// <summary>
    /// Wraps the agent with OpenTelemetry instrumentation.
    /// </summary>
    /// <param name="agent">The agent to wrap.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    /// <returns>An <see cref="OpenTelemetryAgent"/> that wraps the original agent with telemetry.</returns>
    public static OpenTelemetryAgent WithOpenTelemetry(this Agent agent, string? sourceName = null)
    {
        return new OpenTelemetryAgent(agent, sourceName);
    }
}
