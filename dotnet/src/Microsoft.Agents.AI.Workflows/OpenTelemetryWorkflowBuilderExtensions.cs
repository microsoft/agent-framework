// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides extension methods for adding OpenTelemetry instrumentation to <see cref="WorkflowBuilder"/> instances.
/// </summary>
public static class OpenTelemetryWorkflowBuilderExtensions
{
    private const string DefaultSourceName = "Microsoft.Agents.AI.Workflows";

    /// <summary>
    /// Enables OpenTelemetry instrumentation for the workflow, providing comprehensive observability for workflow operations.
    /// </summary>
    /// <param name="builder">The <see cref="WorkflowBuilder"/> to which OpenTelemetry support will be added.</param>
    /// <param name="sourceName">
    /// An optional source name that will be used to identify telemetry data from this workflow.
    /// If not specified, a default source name will be used.
    /// </param>
    /// <param name="configure">
    /// An optional callback that provides additional configuration of the <see cref="WorkflowTelemetryOptions"/> instance.
    /// This allows for fine-tuning telemetry behavior such as enabling sensitive data collection.
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
    ///     .WithOpenTelemetry("MyApp.Workflows", cfg => cfg.EnableSensitiveData = true)
    ///     .Build();
    /// </code>
    /// </example>
    public static WorkflowBuilder WithOpenTelemetry(
        this WorkflowBuilder builder,
        string? sourceName = null,
        Action<WorkflowTelemetryOptions>? configure = null)
    {
        Throw.IfNull(builder);

        WorkflowTelemetryOptions options = new();
        configure?.Invoke(options);

        string effectiveSourceName = string.IsNullOrEmpty(sourceName) ? DefaultSourceName : sourceName!;
        WorkflowTelemetryContext context = new(effectiveSourceName, options);

        builder.SetTelemetryContext(context);

        return builder;
    }
}
