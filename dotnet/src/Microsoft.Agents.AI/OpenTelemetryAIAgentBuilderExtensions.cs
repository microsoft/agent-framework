// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>Provides extensions for configuring <see cref="OpenTelemetryAgent"/> instances.</summary>
public static class OpenTelemetryAIAgentBuilderExtensions
{
    /// <summary>
    /// Adds OpenTelemetry support to the agent pipeline for agent runs, following the OpenTelemetry Semantic Conventions for Generative AI systems.
    /// </summary>
    /// <remarks>
    /// The draft specification this follows is available at <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/" />.
    /// The specification is still experimental and subject to change; as such, the telemetry output by this agent is also subject to change.
    /// </remarks>
    /// <param name="builder">The <see cref="AIAgentBuilder"/>.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    /// <param name="configure">An optional callback that can be used to configure the <see cref="OpenTelemetryAgent"/> instance.</param>
    /// <returns>The <paramref name="builder"/>.</returns>
    public static AIAgentBuilder UseOpenTelemetry(
        this AIAgentBuilder builder,
        string? sourceName = null,
        Action<OpenTelemetryAgent>? configure = null) =>
        Throw.IfNull(builder).Use((innerAgent, services) =>
        {
            var agent = new OpenTelemetryAgent(innerAgent, sourceName);
            configure?.Invoke(agent);

            return agent;
        });
}
