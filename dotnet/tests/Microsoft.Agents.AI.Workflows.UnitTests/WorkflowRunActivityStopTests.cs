// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Regression test for https://github.com/microsoft/agent-framework/issues/4155
/// Verifies that the workflow.run Activity is properly stopped/disposed so it gets exported
/// to telemetry backends. The ActivityStopped callback must fire for the workflow.run span.
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
    /// Verifies that the workflow.run Activity is stopped (and thus exportable) when
    /// using the Lockstep execution environment.
    /// Bug: The Activity created by LockstepRunEventStream.TakeEventStreamAsync is never
    /// disposed because yield break in async iterators does not trigger using disposal.
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_Lockstep()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Lockstep").Start();

        // Act
        var workflow = CreateWorkflow();
        Run run = await InProcessExecution.Lockstep.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert - workflow.run should have been started
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowRun, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(1, "workflow.run Activity should be started");

        // Assert - workflow.run should have been stopped (i.e., Dispose/Stop was called)
        // This is the core assertion for issue #4155: the ActivityStopped callback must fire
        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowRun, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(1,
            "workflow.run Activity should be stopped/disposed so it is exported to telemetry backends (issue #4155)");
    }

    /// <summary>
    /// Verifies that the workflow.run Activity is stopped when using the OffThread (Default)
    /// execution environment (StreamingRunEventStream).
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_OffThread()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_OffThread").Start();

        // Act
        var workflow = CreateWorkflow();
        Run run = await InProcessExecution.OffThread.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert - workflow.run should have been started
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowRun, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(1, "workflow.run Activity should be started");

        // Assert - workflow.run should have been stopped
        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowRun, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(1,
            "workflow.run Activity should be stopped/disposed so it is exported to telemetry backends (issue #4155)");
    }

    /// <summary>
    /// Verifies that the workflow.run Activity is stopped when using the streaming API
    /// (StreamingRun.WatchStreamAsync) with the OffThread execution environment.
    /// This matches the exact usage pattern described in the issue.
    /// </summary>
    [Fact]
    public async Task WorkflowRunActivity_IsStopped_Streaming_OffThread()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Streaming_OffThread").Start();

        // Act - use streaming path (WatchStreamAsync), which is the pattern from the issue
        var workflow = CreateWorkflow();
        await using StreamingRun run = await InProcessExecution.OffThread.RunStreamingAsync(workflow, "Hello, World!");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            // Consume all events
        }

        // Assert - workflow.run should have been started
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowRun, StringComparison.Ordinal))
            .ToList();
        startedWorkflowRuns.Should().HaveCount(1, "workflow.run Activity should be started");

        // Assert - workflow.run should have been stopped
        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowRun, StringComparison.Ordinal))
            .ToList();
        stoppedWorkflowRuns.Should().HaveCount(1,
            "workflow.run Activity should be stopped/disposed so it is exported to telemetry backends (issue #4155)");
    }

    /// <summary>
    /// Verifies that all started activities (not just workflow.run) are properly stopped.
    /// This ensures no spans are "leaked" without being exported.
    /// </summary>
    [Fact]
    public async Task AllActivities_AreStopped_AfterWorkflowCompletion()
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
}
