// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for adding OpenTelemetry instrumentation to <see cref="WorkflowBuilder"/> instances.
/// </summary>
public static class OpenTelemetryWorkflowBuilderExtensions
{
    /// <summary>
    /// Enables OpenTelemetry instrumentation for the workflow, providing comprehensive observability for workflow operations.
    /// </summary>
    /// <param name="builder">The <see cref="WorkflowBuilder"/> to which OpenTelemetry support will be added.</param>
    /// <param name="configure">
    /// An optional callback that provides additional configuration of the <see cref="WorkflowTelemetryOptions"/> instance.
    /// This allows for fine-tuning telemetry behavior such as enabling sensitive data collection.
    /// </param>
    /// <param name="activitySource">
    /// An optional <see cref="ActivitySource"/> to use for telemetry. If provided, this activity source will be used
    /// directly and the caller retains ownership (responsible for disposal). If <see langword="null"/>, a shared
    /// default activity source named "Microsoft.Agents.AI.Workflows" will be used.
    /// </param>
    /// <returns>The <see cref="WorkflowBuilder"/> with OpenTelemetry instrumentation enabled, enabling method chaining.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="builder"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// This extension adds comprehensive telemetry capabilities to workflows, including:
    /// <list type="bullet">
    /// <item><description>Distributed tracing of workflow execution</description></item>
    /// <item><description>Executor invocation and processing spans</description></item>
    /// <item><description>Edge routing and message delivery spans</description></item>
    /// <item><description>Workflow build and validation spans</description></item>
    /// <item><description>Error tracking and exception details</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// By default, workflow telemetry is disabled. Call this method to enable telemetry collection.
    /// </para>
    /// </remarks>
    /// <example>
    /// <code>
    /// var workflow = new WorkflowBuilder(startExecutor)
    ///     .AddEdge(executor1, executor2)
    ///     .WithOpenTelemetry(cfg => cfg.EnableSensitiveData = true)
    ///     .Build();
    /// </code>
    /// </example>
    public static WorkflowBuilder WithOpenTelemetry(
        this WorkflowBuilder builder,
        Action<WorkflowTelemetryOptions>? configure = null,
        ActivitySource? activitySource = null)
    {
        Throw.IfNull(builder);

        WorkflowTelemetryOptions options = new();
        configure?.Invoke(options);

        WorkflowTelemetryContext context = new(options, activitySource);

        builder.SetTelemetryContext(context);

        return builder;
    }
}
