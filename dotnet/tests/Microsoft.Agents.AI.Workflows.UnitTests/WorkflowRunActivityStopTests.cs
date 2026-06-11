// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Regression test for https://github.com/microsoft/agent-framework/issues/4155
/// Verifies that the workflow_invoke Activity is properly stopped/disposed so it gets exported
/// to telemetry backends. The ActivityStopped callback must fire for the workflow_invoke span.
/// </summary>
[Collection("ObservabilityTests")]
public sealed class WorkflowRunActivityStopTests : IDisposable
{
    private readonly ActivityListener _activityListener;
    private readonly ConcurrentBag<Activity> _startedActivities = [];
    private readonly ConcurrentBag<Activity> _stoppedActivities = [];
    private bool _isDisposed;

    public WorkflowRunActivityStopTests()
    {
        this._activityListener = new ActivityListener
        {
            ShouldListenTo = source => source.Name.Contains(typeof(Workflow).Namespace!),
            Sample = (ref ActivityCreationOptions<ActivityContext> options) => ActivitySamplingResult.AllData,
            ActivityStarted = activity => this._startedActivities.Add(activity),
            ActivityStopped = activity => this._stoppedActivities.Add(activity),
        };
        ActivitySource.AddActivityListener(this._activityListener);
    }

    public void Dispose()
    {
        if (!this._isDisposed)
        {
            this._activityListener?.Dispose();
            this._isDisposed = true;
        }
    }

    /// <summary>
    /// Creates a simple sequential workflow with OpenTelemetry enabled.
    /// </summary>
    private static Workflow CreateWorkflow()
    {
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);

        return builder.WithOpenTelemetry().Build();
    }

    /// <summary>
    /// Verifies that the workflow_invoke Activity is stopped (and thus exportable) when
    /// using the Lockstep execution environment.
    /// Bug: The Activity created by LockstepRunEventStream.TakeEventStreamAsync is never
    /// disposed because yield break in async iterators does not trigger using disposal.
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_LockstepAsync()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Lockstep").Start();

        // Act
        var workflow = CreateWorkflow();
        Run run = await InProcessExecution.Lockstep.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert - workflow.session should have been started and stopped
        var startedSessions = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        startedSessions.Should().HaveCount(1, "workflow.session Activity should be started");

        var stoppedSessions = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        stoppedSessions.Should().HaveCount(1,
            "workflow.session Activity should be stopped/disposed so it is exported to telemetry backends");

        // Assert - workflow_invoke should have been started and stopped
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(1, "workflow_invoke Activity should be started");

        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(1,
            "workflow_invoke Activity should be stopped/disposed so it is exported to telemetry backends (issue #4155)");
    }

    /// <summary>
    /// Verifies that the workflow_invoke Activity is stopped when using the OffThread (Default)
    /// execution environment (StreamingRunEventStream).
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_OffThreadAsync()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_OffThread").Start();

        // Act
        var workflow = CreateWorkflow();
        Run run = await InProcessExecution.OffThread.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert - workflow.session should have been started and stopped
        var startedSessions = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        startedSessions.Should().HaveCount(1, "workflow.session Activity should be started");

        var stoppedSessions = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        stoppedSessions.Should().HaveCount(1,
            "workflow.session Activity should be stopped/disposed so it is exported to telemetry backends");

        // Assert - workflow_invoke should have been started and stopped
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(1, "workflow_invoke Activity should be started");

        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(1,
            "workflow_invoke Activity should be stopped/disposed so it is exported to telemetry backends (issue #4155)");
    }

    /// <summary>
    /// Verifies that the workflow_invoke Activity is stopped when using the streaming API
    /// (StreamingRun.WatchStreamAsync) with the OffThread execution environment.
    /// This matches the exact usage pattern described in the issue.
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_Streaming_OffThreadAsync()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Streaming_OffThread").Start();

        // Act - use streaming path (WatchStreamAsync), which is the pattern from the issue
        var workflow = CreateWorkflow();
        StreamingRun run = await InProcessExecution.OffThread.RunStreamingAsync(workflow, "Hello, World!");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            // Consume all events
        }

        // Dispose the run before asserting — the run Activity is disposed when the
        // run loop exits, which happens during DisposeAsync. Without this, assertions
        // can race against the background run loop's finally block.
        await run.DisposeAsync();

        // Assert - workflow.session should have been started
        var startedSessions = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        startedSessions.Should().HaveCount(1, "workflow.session Activity should be started");

        // Assert - workflow_invoke should have been started
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(1, "workflow_invoke Activity should be started");

        // Assert - workflow_invoke should have been stopped
        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(1,
            "workflow_invoke Activity should be stopped/disposed so it is exported to telemetry backends (issue #4155)");
    }

    /// <summary>
    /// Verifies that a new workflow_invoke activity is started and stopped for each
    /// streaming invocation, even when using the same workflow in a multi-turn pattern,
    /// and that each session gets its own session activity.
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_Streaming_OffThread_MultiTurnAsync()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Streaming_OffThread_MultiTurn").Start();

        var workflow = CreateWorkflow();

        // Act - first streaming run
        await using (StreamingRun run1 = await InProcessExecution.OffThread.RunStreamingAsync(workflow, "Hello, World!"))
        {
            await foreach (WorkflowEvent evt in run1.WatchStreamAsync())
            {
                // Consume all events from first turn
            }
        }

        // Act - second streaming run (multi-turn scenario with same workflow)
        await using (StreamingRun run2 = await InProcessExecution.OffThread.RunStreamingAsync(workflow, "Second turn!"))
        {
            await foreach (WorkflowEvent evt in run2.WatchStreamAsync())
            {
                // Consume all events from second turn
            }
        }

        // Assert - two workflow.session activities should have been started and stopped
        var startedSessions = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        startedSessions.Should().HaveCount(2,
            "each streaming invocation should start its own workflow.session Activity");

        var stoppedSessions = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        stoppedSessions.Should().HaveCount(2,
            "each workflow.session Activity should be stopped/disposed so it is exported to telemetry backends");

        // Assert - two workflow_invoke activities should have been started and stopped
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(2,
            "each streaming invocation should start its own workflow_invoke Activity");

        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(2,
            "each workflow_invoke Activity should be stopped/disposed so it is exported to telemetry backends in multi-turn scenarios");
    }

    /// <summary>
    /// Verifies that all started activities (not just workflow_invoke) are properly stopped.
    /// This ensures no spans are "leaked" without being exported.
    /// </summary>
    [Fact]
    public async Task AllActivities_AreStopped_AfterWorkflowCompletionAsync()
    {
        // Arrange
        using var testActivity = new Activity("AllActivitiesStopTest").Start();

        // Act
        var workflow = CreateWorkflow();
        Run run = await InProcessExecution.Lockstep.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert - every started activity should also be stopped
        var started = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId)
            .Select(a => a.Id)
            .ToHashSet();

        var stopped = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId)
            .Select(a => a.Id)
            .ToHashSet();

        var neverStopped = started.Except(stopped).ToList();
        if (neverStopped.Count > 0)
        {
            var neverStoppedNames = this._startedActivities
                .Where(a => neverStopped.Contains(a.Id))
                .Select(a => a.OperationName)
                .ToList();
            neverStoppedNames.Should().BeEmpty(
                "all started activities should be stopped so they are exported. " +
                $"Activities started but never stopped: [{string.Join(", ", neverStoppedNames)}]");
        }
    }

    /// <summary>
    /// Verifies that Activity.Current is not leaked after lockstep RunAsync.
    /// Application code creating activities after RunAsync returns should not
    /// be parented under the workflow session span. The run activity should
    /// still nest correctly under the session.
    /// </summary>
    [Fact]
    public async Task Lockstep_SessionActivity_DoesNotLeak_IntoCaller_ActivityCurrentAsync()
    {
        // Arrange
        using var testActivity = new Activity("SessionLeakTest").Start();
        var workflow = CreateWorkflow();

        // Act — run the workflow via lockstep (Start + drain happen inside RunAsync)
        Run run = await InProcessExecution.Lockstep.RunAsync(workflow, "Hello, World!");

        // Create an application activity after RunAsync returns.
        // If the session leaked into Activity.Current, this would be parented under it.
        using var appActivity = new Activity("AppWork").Start();
        appActivity.Stop();

        await run.DisposeAsync();

        // Assert — the app activity should be parented under the test root, not the session
        var sessionActivities = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        sessionActivities.Should().HaveCount(1, "one session activity should exist");

        appActivity.ParentId.Should().Be(testActivity.Id,
            "application activity should be parented under the test root, not the workflow session");

        // Assert — the run activity should still be parented under the session
        var invokeActivities = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        invokeActivities.Should().HaveCount(1, "one workflow_invoke activity should exist");
        invokeActivities[0].ParentId.Should().Be(sessionActivities[0].Id,
            "workflow_invoke activity should be nested under the session activity");
    }
}
