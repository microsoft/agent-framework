// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for adding OpenTelemetry instrumentation to <see cref="AIAgentBuilder"/> instances.
/// </summary>
public static class OpenTelemetryAgentBuilderExtensions
{
    /// <summary>
    /// Adds OpenTelemetry instrumentation to the agent pipeline, enabling comprehensive observability for agent operations.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which OpenTelemetry support will be added.</param>
    /// <param name="sourceName">
    /// An optional source name that will be used to identify telemetry data from this agent.
    /// If not specified, a default source name will be used.
    /// </param>
    /// <param name="configure">
    /// An optional callback that provides additional configuration of the <see cref="OpenTelemetryAgent"/> instance.
    /// This allows for fine-tuning telemetry behavior such as enabling sensitive data collection.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> with OpenTelemetry instrumentation added, enabling method chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// This extension adds comprehensive telemetry capabilities to AI agents, including:
    /// <list type="bullet">
    /// <item><description>Distributed tracing of agent invocations</description></item>
    /// <item><description>Performance metrics and timing information</description></item>
    /// <item><description>Request and response payload logging (when enabled)</description></item>
    /// <item><description>Error tracking and exception details</description></item>
    /// <item><description>Usage statistics and token consumption metrics</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The implementation follows the OpenTelemetry Semantic Conventions for Generative AI systems as defined at
    /// <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/"/>.
    /// </para>
    /// <para>
    /// Note: The OpenTelemetry specification for Generative AI is still experimental and subject to change.
    /// As the specification evolves, the telemetry output from this agent may also change to maintain compliance.
    /// </para>
    /// </remarks>
    public static AIAgentBuilder UseOpenTelemetry(
        this AIAgentBuilder builder,
        string? sourceName = null,
        Action<OpenTelemetryAgent>? configure = null) =>
        builder.UseOpenTelemetry(autoWireChatClient: true, sourceName: sourceName, configure: configure);

    /// <summary>
    /// Adds OpenTelemetry instrumentation to the agent pipeline, with explicit control over whether the underlying
    /// <see cref="IChatClient"/> of a <see cref="ChatClientAgent"/> inner agent is automatically wrapped with
    /// <see cref="Microsoft.Extensions.AI.OpenTelemetryChatClient"/>.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which OpenTelemetry support will be added.</param>
    /// <param name="autoWireChatClient">
    /// When <see langword="true"/>, the underlying <see cref="IChatClient"/> of a <see cref="ChatClientAgent"/> inner agent
    /// is automatically wrapped with <see cref="Microsoft.Extensions.AI.OpenTelemetryChatClient"/> on each invocation so
    /// that chat-level telemetry flows alongside agent-level telemetry. If the underlying chat client is already
    /// instrumented, no additional wrapping is applied. If the inner agent is not a <see cref="ChatClientAgent"/>, no
    /// auto-wiring is performed. Set to <see langword="false"/> to opt out of this behavior.
    /// </param>
    /// <param name="sourceName">
    /// An optional source name that will be used to identify telemetry data from this agent.
    /// If not specified, a default source name will be used.
    /// </param>
    /// <param name="configure">
    /// An optional callback that provides additional configuration of the <see cref="OpenTelemetryAgent"/> instance.
    /// This allows for fine-tuning telemetry behavior such as enabling sensitive data collection.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> with OpenTelemetry instrumentation added, enabling method chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    public static AIAgentBuilder UseOpenTelemetry(
        this AIAgentBuilder builder,
        bool autoWireChatClient,
        string? sourceName = null,
        Action<OpenTelemetryAgent>? configure = null) =>
        Throw.IfNull(builder).Use((innerAgent, services) =>
        {
            var agent = new OpenTelemetryAgent(innerAgent, sourceName, autoWireChatClient);
            configure?.Invoke(agent);

            return agent;
        });
}
