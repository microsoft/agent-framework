// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Regression test for https://github.com/microsoft/agent-framework/issues/4155
/// Verifies that the invoke_workflow Activity is properly stopped/disposed so it gets exported
/// to telemetry backends. The ActivityStopped callback must fire for the invoke_workflow span.
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

        return builder.WithName("activity_stop_workflow").WithOpenTelemetry().Build();
    }

    /// <summary>
    /// Verifies that the invoke_workflow Activity is stopped (and thus exportable) when
    /// using the Lockstep execution environment.
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
        Assert.Single(startedSessions ?? []);

        var stoppedSessions = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        Assert.Single(stoppedSessions ?? []);

        // Assert - invoke_workflow should have been started and stopped
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Single(startedWorkflowRuns ?? []);

        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Single(stoppedWorkflowRuns ?? []);
    }

    [Theory]
    [InlineData("EarlyDisposal")]
    [InlineData("Cancellation")]
    [InlineData("ConsumerFailure")]
    public async Task WorkflowRunActivity_IsStopped_Lockstep_InterruptedEnumerationAsync(string exitReason)
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Lockstep_Interrupted").Start();
        var workflow = CreateWorkflow();
        var expectedException = new InvalidOperationException("Consumer failed.");
        await using StreamingRun run = await InProcessExecution.Lockstep.RunStreamingAsync(workflow, "Hello, World!");
        int eventCount = 0;

        async Task ConsumeAsync()
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                eventCount++;
                Assert.DoesNotContain(this._stoppedActivities, a =>
                    a.RootId == testActivity.RootId &&
                    a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));

                switch (exitReason)
                {
                    case "EarlyDisposal":
                        return;
                    case "Cancellation":
                        await run.CancelRunAsync();
                        break;
                    case "ConsumerFailure":
                        throw expectedException;
                    default:
                        throw new ArgumentOutOfRangeException(nameof(exitReason));
                }
            }
        }

        // Act
        if (string.Equals(exitReason, "ConsumerFailure", StringComparison.Ordinal))
        {
            var actualException = await Assert.ThrowsAsync<InvalidOperationException>(ConsumeAsync);
            Assert.Same(expectedException, actualException);
        }
        else
        {
            await ConsumeAsync();
        }

        // Assert
        Assert.Equal(1, eventCount);
        var startedRun = Assert.Single(this._startedActivities, a =>
            a.RootId == testActivity.RootId &&
            a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
        var stoppedRun = Assert.Single(this._stoppedActivities, a =>
            a.RootId == testActivity.RootId &&
            a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
        Assert.Same(startedRun, stoppedRun);
        Assert.Equal(RunStatus.Idle, await run.GetStatusAsync());
        Assert.Same(testActivity, Activity.Current);
    }

    [Fact]
    public async Task WorkflowRunActivity_IsStopped_Lockstep_ExecutorFailureAsync()
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunStopTest_Lockstep_ExecutorFailure").Start();
        var expectedException = new InvalidOperationException("Executor failed.");
        Func<string, string> failingFunc = _ => throw expectedException;
        var executor = failingFunc.BindAsExecutor("FailingExecutor");
        var workflow = new WorkflowBuilder(executor)
            .WithOutputFrom(executor)
            .WithName("failing_workflow")
            .WithOpenTelemetry()
            .Build();
        await using StreamingRun run = await InProcessExecution.Lockstep.RunStreamingAsync(workflow, "Hello, World!");
        ExecutorFailedEvent? failureEvent = null;

        // Act
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is ExecutorFailedEvent failure)
            {
                failureEvent = failure;
            }
        }

        // Assert
        Assert.NotNull(failureEvent);
        Assert.Same(expectedException, failureEvent.Data);
        var startedRun = Assert.Single(this._startedActivities, a =>
            a.RootId == testActivity.RootId &&
            a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
        var stoppedRun = Assert.Single(this._stoppedActivities, a =>
            a.RootId == testActivity.RootId &&
            a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
        Assert.Same(startedRun, stoppedRun);
        Assert.Equal(RunStatus.Idle, await run.GetStatusAsync());
        Assert.Same(testActivity, Activity.Current);
    }

    /// <summary>
    /// Verifies that the invoke_workflow Activity is stopped when using the OffThread (Default)
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
        Assert.Single(startedSessions ?? []);

        var stoppedSessions = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        Assert.Single(stoppedSessions ?? []);

        // Assert - invoke_workflow should have been started and stopped
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Single(startedWorkflowRuns ?? []);

        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Single(stoppedWorkflowRuns ?? []);
    }

    /// <summary>
    /// Verifies that the invoke_workflow Activity is stopped when using the streaming API
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
        Assert.Single(startedSessions ?? []);

        // Assert - invoke_workflow should have been started
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Single(startedWorkflowRuns ?? []);

        // Assert - invoke_workflow should have been stopped
        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Single(stoppedWorkflowRuns ?? []);
    }

    /// <summary>
    /// Verifies that a new invoke_workflow activity is started and stopped for each
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
        Assert.Equal(2, startedSessions.Count);

        var stoppedSessions = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal))
            .ToList();
        Assert.Equal(2, stoppedSessions.Count);

        // Assert - two invoke_workflow activities should have been started and stopped
        var startedWorkflowRuns = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Equal(2, startedWorkflowRuns.Count);

        var stoppedWorkflowRuns = this._stoppedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        Assert.Equal(2, stoppedWorkflowRuns.Count);
    }

    /// <summary>
    /// Verifies that all started activities (not just invoke_workflow) are properly stopped.
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
            Assert.Empty(neverStoppedNames ?? []);
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
        Assert.Single(sessionActivities);

        Assert.Equal(testActivity.Id, appActivity.ParentId);

        // Assert — the run activity should still be parented under the session
        var invokeActivities = this._startedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                        a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal))
            .ToList();
        var invokeActivity = Assert.Single(invokeActivities);
        Assert.Equal(Assert.Single(sessionActivities).Id, invokeActivity.ParentId);
    }
}
