// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using OpenTelemetry;

namespace Microsoft.Agents.AI.Workflows.Observability;

/// <summary>
/// Internal context for workflow telemetry, holding the enabled state and configuration options.
/// </summary>
internal sealed class WorkflowTelemetryContext
{
    private const string DefaultSourceName = "Microsoft.Agents.AI.Workflows";
    private static readonly ActivitySource s_defaultActivitySource = new(DefaultSourceName);

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
    public ActivitySource ActivitySource { get; }

    private WorkflowTelemetryContext()
    {
        this.IsEnabled = false;
        this.Options = new WorkflowTelemetryOptions();
        this.ActivitySource = s_defaultActivitySource;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowTelemetryContext"/> class with telemetry enabled.
    /// </summary>
    /// <param name="options">The telemetry options.</param>
    /// <param name="activitySource">
    /// An optional activity source to use. If provided, this activity source will be used directly
    /// and the caller retains ownership (responsible for disposal). If <see langword="null"/>, the
    /// shared default activity source will be used.
    /// </param>
    public WorkflowTelemetryContext(WorkflowTelemetryOptions options, ActivitySource? activitySource = null)
    {
        this.IsEnabled = true;
        this.Options = options;
        this.ActivitySource = activitySource ?? s_defaultActivitySource;
    }

    /// <summary>
    /// Starts an activity if telemetry is enabled, otherwise returns null.
    /// </summary>
    /// <param name="name">The activity name.</param>
    /// <param name="kind">The activity kind.</param>
    /// <returns>An activity if telemetry is enabled and the activity is sampled, otherwise null.</returns>
    public Activity? StartActivity(string name, ActivityKind kind = ActivityKind.Internal)
    {
        if (!this.IsEnabled)
        {
            return null;
        }

        return this.ActivitySource.StartActivity(name, kind);
    }

    /// <summary>
    /// Starts a workflow build activity if enabled.
    /// </summary>
    /// <returns>An activity if workflow build telemetry is enabled, otherwise null.</returns>
    public Activity? StartWorkflowBuildActivity()
    {
        if (!this.IsEnabled || this.Options.DisableWorkflowBuild)
        {
            return null;
        }

        return this.ActivitySource.StartActivity(ActivityNames.WorkflowBuild);
    }

    /// <summary>
    /// Starts a workflow session activity if enabled. This is the outer/parent span
    /// that represents the entire lifetime of a workflow execution (from start
    /// until stop, cancellation, or error) within the current trace.
    /// Individual run stages are typically nested within it.
    /// </summary>
    /// <returns>An activity if workflow run telemetry is enabled, otherwise null.</returns>
    public Activity? StartWorkflowSessionActivity()
    {
        if (!this.IsEnabled || this.Options.DisableWorkflowRun)
        {
            return null;
        }

        return this.ActivitySource.StartActivity(ActivityNames.WorkflowSession);
    }

    /// <summary>
    /// Starts a workflow run activity if enabled. This represents a single
    /// input-to-halt cycle within a workflow session.
    /// </summary>
    /// <param name="workflowName">The optional application-defined workflow name.</param>
    /// <returns>An activity if workflow run telemetry is enabled, otherwise null.</returns>
    public Activity? StartWorkflowRunActivity(string? workflowName)
    {
        if (!this.IsEnabled || this.Options.DisableWorkflowRun)
        {
            return null;
        }

        ActivityTagsCollection tags = new() { { Tags.OperationName, ActivityNames.WorkflowInvoke } };
        string activityName = ActivityNames.WorkflowInvoke;
        if (!string.IsNullOrWhiteSpace(workflowName))
        {
            tags.Add(Tags.WorkflowName, workflowName);
            activityName += " " + workflowName;
        }

        string? conversationId = Baggage.GetBaggage(Tags.ConversationId);
        if (string.IsNullOrWhiteSpace(conversationId))
        {
            conversationId = Activity.Current?.GetBaggageItem(Tags.ConversationId);
        }
        if (!string.IsNullOrWhiteSpace(conversationId))
        {
            tags.Add(Tags.ConversationId, conversationId);
        }

        return this.ActivitySource.StartActivity(activityName, ActivityKind.Internal, parentContext: default, tags: tags);
    }

    /// <summary>
    /// Starts an executor process activity if enabled, with all standard tags set.
    /// </summary>
    /// <param name="executorId">The executor identifier.</param>
    /// <param name="executorType">The executor type name.</param>
    /// <param name="messageType">The message type name.</param>
    /// <returns>An activity if executor process telemetry is enabled, otherwise null.</returns>
    public Activity? StartExecutorProcessActivity(string executorId, string? executorType, string messageType)
    {
        if (!this.IsEnabled || this.Options.DisableExecutorProcess)
        {
            return null;
        }

        Activity? activity = this.ActivitySource.StartActivity(ActivityNames.ExecutorProcess + " " + executorId);
        if (activity is null)
        {
            return null;
        }

        activity.SetTag(Tags.ExecutorId, executorId)
            .SetTag(Tags.ExecutorType, executorType)
            .SetTag(Tags.MessageType, messageType);

        return activity;
    }

    /// <summary>
    /// Starts an edge group process activity if enabled.
    /// </summary>
    /// <returns>An activity if edge group process telemetry is enabled, otherwise null.</returns>
    public Activity? StartEdgeGroupProcessActivity()
    {
        if (!this.IsEnabled || this.Options.DisableEdgeGroupProcess)
        {
            return null;
        }

        return this.ActivitySource.StartActivity(ActivityNames.EdgeGroupProcess);
    }

    /// <summary>
    /// Starts a message send activity if enabled, with all standard tags set.
    /// </summary>
    /// <param name="sourceId">The source executor identifier.</param>
    /// <param name="targetId">The target executor identifier, if any.</param>
    /// <returns>An activity if message send telemetry is enabled, otherwise null.</returns>
    public Activity? StartMessageSendActivity(string sourceId, string? targetId)
    {
        if (!this.IsEnabled || this.Options.DisableMessageSend)
        {
            return null;
        }

        Activity? activity = this.ActivitySource.StartActivity(ActivityNames.MessageSend, ActivityKind.Producer);
        if (activity is null)
        {
            return null;
        }

        activity.SetTag(Tags.MessageSourceId, sourceId);
        if (targetId is not null)
        {
            activity.SetTag(Tags.MessageTargetId, targetId);
        }

        return activity;
    }
}
