// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Observability;

/// <summary>
/// Internal context for workflow telemetry, holding the enabled state and configuration options.
/// </summary>
internal sealed class WorkflowTelemetryContext
{
    /// <summary>
    /// Gets a shared instance representing disabled telemetry.
    /// </summary>
    public static WorkflowTelemetryContext Disabled { get; } = new();

    /// <summary>
    /// Gets a value indicating whether telemetry is enabled.
    /// </summary>
    public bool IsEnabled { get; }

    /// <summary>
    /// Gets the telemetry options.
    /// </summary>
    public WorkflowTelemetryOptions Options { get; }

    /// <summary>
    /// Gets the activity source used for creating telemetry spans.
    /// </summary>
    public ActivitySource? ActivitySource { get; }

    private WorkflowTelemetryContext()
    {
        this.IsEnabled = false;
        this.Options = new WorkflowTelemetryOptions();
        this.ActivitySource = null;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowTelemetryContext"/> class with telemetry enabled.
    /// </summary>
    /// <param name="sourceName">The source name for the activity source. Used only when <paramref name="activitySource"/> is <see langword="null"/>.</param>
    /// <param name="options">The telemetry options.</param>
    /// <param name="activitySource">
    /// An optional activity source to use. If provided, this activity source will be used directly
    /// and the caller retains ownership (responsible for disposal). If <see langword="null"/>, a new
    /// activity source will be created using <paramref name="sourceName"/>.
    /// </param>
    public WorkflowTelemetryContext(string sourceName, WorkflowTelemetryOptions options, ActivitySource? activitySource = null)
    {
        this.IsEnabled = true;
        this.Options = options;
        this.ActivitySource = activitySource ?? new ActivitySource(sourceName);
    }

    /// <summary>
    /// Starts an activity if telemetry is enabled, otherwise returns null.
    /// </summary>
    /// <param name="name">The activity name.</param>
    /// <param name="kind">The activity kind.</param>
    /// <returns>An activity if telemetry is enabled and the activity is sampled, otherwise null.</returns>
    public Activity? StartActivity(string name, ActivityKind kind = ActivityKind.Internal)
    {
        return this.ActivitySource?.StartActivity(name, kind);
    }

    /// <summary>
    /// Starts a workflow build activity if enabled.
    /// </summary>
    /// <returns>An activity if workflow build telemetry is enabled, otherwise null.</returns>
    public Activity? StartWorkflowBuildActivity()
    {
        if (this.Options.DisableWorkflowBuild)
        {
            return null;
        }

        return this.ActivitySource?.StartActivity(ActivityNames.WorkflowBuild);
    }

    /// <summary>
    /// Starts a workflow run activity if enabled.
    /// </summary>
    /// <returns>An activity if workflow run telemetry is enabled, otherwise null.</returns>
    public Activity? StartWorkflowRunActivity()
    {
        if (this.Options.DisableWorkflowRun)
        {
            return null;
        }

        return this.ActivitySource?.StartActivity(ActivityNames.WorkflowRun);
    }

    /// <summary>
    /// Starts an executor process activity if enabled.
    /// </summary>
    /// <param name="executorId">The executor identifier to include in the activity name.</param>
    /// <returns>An activity if executor process telemetry is enabled, otherwise null.</returns>
    public Activity? StartExecutorProcessActivity(string executorId)
    {
        if (this.Options.DisableExecutorProcess)
        {
            return null;
        }

        return this.ActivitySource?.StartActivity(ActivityNames.ExecutorProcess + " " + executorId);
    }

    /// <summary>
    /// Starts an edge group process activity if enabled.
    /// </summary>
    /// <returns>An activity if edge group process telemetry is enabled, otherwise null.</returns>
    public Activity? StartEdgeGroupProcessActivity()
    {
        if (this.Options.DisableEdgeGroupProcess)
        {
            return null;
        }

        return this.ActivitySource?.StartActivity(ActivityNames.EdgeGroupProcess);
    }

    /// <summary>
    /// Starts a message send activity if enabled.
    /// </summary>
    /// <returns>An activity if message send telemetry is enabled, otherwise null.</returns>
    public Activity? StartMessageSendActivity()
    {
        if (this.Options.DisableMessageSend)
        {
            return null;
        }

        return this.ActivitySource?.StartActivity(ActivityNames.MessageSend, ActivityKind.Producer);
    }
}
