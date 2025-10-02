// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for configuring and customizing <see cref="AIAgentBuilder"/> instances.
/// </summary>
public static class AIAgentBuilderExtensions
{
    /// <summary>
    /// Adds function invocation callbacks to the <see cref="AIAgent"/> pipeline that intercepts and processes <see cref="AIFunction"/> calls.
    /// </summary>
    /// <param name="builder">The <see cref="AIAgentBuilder"/> to which the function invocation callback is added.</param>
    /// <param name="callback">
    /// A delegate that processes function invocations. The delegate receives the <see cref="AIAgent"/> instance,
    /// the function invocation context, and a continuation delegate representing the next callback in the pipeline.
    /// It returns a task representing the result of the function invocation.
    /// </param>
    /// <returns>The <see cref="AIAgentBuilder"/> instance with the function invocation callback added, enabling method chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> or <paramref name="callback"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// The callback must call the provided continuation delegate to proceed with the function invocation,
    /// unless it intends to completely replace the function's behavior.
    /// </para>
    /// <para>
    /// The inner agent or the pipeline wrapping it must include a <see cref="FunctionInvokingChatClient"/>. If one does not exist,
    /// the <see cref="AIAgent"/> added to the pipline by this method will throw an exception when it is invoked.
    /// </para>
    /// </remarks>
    public static AIAgentBuilder Use(this AIAgentBuilder builder, Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> callback)
    {
        _ = Throw.IfNull(builder);
        _ = Throw.IfNull(callback);
        return builder.Use((innerAgent, _) =>
        {
            // Function calling requires a ChatClientAgent inner agent.
            if (innerAgent.GetService<FunctionInvokingChatClient>() is null)
            {
                throw new InvalidOperationException($"The function invocation middleware can only be used with decorations of a {nameof(AIAgent)} that support usage of FunctionInvokingChatClient decorated chat clients.");
            }

            return new FunctionInvocationDelegatingAgent(innerAgent, callback);
        });
    }

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
        Throw.IfNull(builder).Use((innerAgent, services) =>
        {
            var agent = new OpenTelemetryAgent(innerAgent, sourceName);
            configure?.Invoke(agent);

            return agent;
        });
}
