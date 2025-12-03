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
/// These tests ensure that OpenTelemetry Activity traces are properly created for workflow monitoring.
/// Tests are run in a collection to avoid parallel execution since ActivityListener is global.
/// Each test creates a new instance of ObservabilityTests and runs in serial within the collection.
/// This prevents interference between tests due to the global nature of ActivityListener.
/// </summary>
[Collection("ObservabilityTests")]
public sealed class ObservabilityTests : IDisposable
{
    private readonly ActivityListener _activityListener;
    private readonly ConcurrentBag<Activity> _capturedActivities = [];

    private bool _isDisposed;

    public ObservabilityTests()
    {
        // Set up activity listener to capture activities from workflow
        // This is global and captures ALL workflow activities from ANY test in the same process!
        this._activityListener = new ActivityListener
        {
            ShouldListenTo = source => source.Name.Contains(typeof(Workflow).Namespace!),
            Sample = (ref options) => ActivitySamplingResult.AllData,
            ActivityStarted = activity => this._capturedActivities.Add(activity),
        };
        ActivitySource.AddActivityListener(this._activityListener);
    }

    /// <summary>
    /// Create a sample workflow for testing.
    /// </summary>
    /// <remarks>
    /// This workflow is expected to create 8 activities that will be captured by the tests
    /// - ActivityNames.WorkflowBuild
    /// - ActivityNames.WorkflowRun
    /// -- ActivityNames.EdgeGroupProcess
    /// -- ActivityNames.ExecutorProcess (UppercaseExecutor)
    /// --- ActivityNames.MessageSend
    /// ---- ActivityNames.EdgeGroupProcess
    /// -- ActivityNames.ExecutorProcess (ReverseTextExecutor)
    /// --- ActivityNames.MessageSend
    /// </remarks>
    /// <returns>The created workflow.</returns>
    private static Workflow CreateWorkflow()
    {
        // Create the executors
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        // Build the workflow by connecting executors sequentially
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);

        return builder.Build();
    }

    private static Dictionary<string, int> GetExpectedActivityNameCounts() =>
        new()
        {
            { ActivityNames.WorkflowBuild, 1 },
            { ActivityNames.WorkflowRun, 1 },
            { ActivityNames.EdgeGroupProcess, 2 },
            { ActivityNames.ExecutorProcess, 2 },
            { ActivityNames.MessageSend, 2 }
        };

    private static InProcessExecutionEnvironment GetExecutionEnvironment(string name) =>
        name switch
        {
            "Default" => InProcessExecution.Default,
            "Lockstep" => InProcessExecution.Lockstep,
            "OffThread" => InProcessExecution.OffThread,
            "Concurrent" => InProcessExecution.Concurrent,
            _ => throw new ArgumentException($"Unknown execution environment name: {name}")
        };

    public void Dispose()
    {
        if (!this._isDisposed)
        {
            this._activityListener?.Dispose();
            this._isDisposed = true;
        }
    }

    private async Task TestWorkflowEndToEndActivitiesAsync(string executionEnvironmentName)
    {
        // Arrange
        // Create a test activity to correlate captured activities
        using var testActivity = new Activity("ObservabilityTest").Start();

        // Act
        var workflow = CreateWorkflow();
        var executionEnvironment = GetExecutionEnvironment(executionEnvironmentName);
        Run run = await executionEnvironment.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        await Task.Delay(100); // Allow time for activities to be captured

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().HaveCount(8, "Exactly 8 activities should be created.");

        // Make sure all expected activities exist and have the correct count
        foreach (var kvp in GetExpectedActivityNameCounts())
        {
            var activityName = kvp.Key;
            var expectedCount = kvp.Value;
            var actualCount = capturedActivities.Count(a => a.OperationName == activityName);
            actualCount.Should().Be(expectedCount, $"Activity '{activityName}' should occur {expectedCount} times.");
        }

        // Verify WorkflowRun activity events include workflow lifecycle events
        var workflowRunActivity = capturedActivities.First(a => a.OperationName == ActivityNames.WorkflowRun);
        var activityEvents = workflowRunActivity.Events.ToList();
        activityEvents.Should().Contain(e => e.Name == EventNames.WorkflowStarted, "activity should have workflow started event");
        activityEvents.Should().Contain(e => e.Name == EventNames.WorkflowCompleted, "activity should have workflow completed event");
    }

    [Fact]
    public async Task CreatesWorkflowEndToEndActivities_WithCorrectName_DefaultAsync()
    {
        await this.TestWorkflowEndToEndActivitiesAsync("Default");
    }

    [Fact]
    public async Task CreatesWorkflowEndToEndActivities_WithCorrectName_OffThreadAsync()
    {
        await this.TestWorkflowEndToEndActivitiesAsync("OffThread");
    }

    [Fact]
    public async Task CreatesWorkflowEndToEndActivities_WithCorrectName_ConcurrentAsync()
    {
        await this.TestWorkflowEndToEndActivitiesAsync("Concurrent");
    }

    [Fact]
    public async Task CreatesWorkflowEndToEndActivities_WithCorrectName_LockstepAsync()
    {
        await this.TestWorkflowEndToEndActivitiesAsync("Lockstep");
    }

    [Fact]
    public async Task CreatesWorkflowActivities_WithCorrectNameAsync()
    {
        // Arrange
        // Create a test activity to correlate captured activities
        using var testActivity = new Activity("ObservabilityTest").Start();

        // Act
        CreateWorkflow();
        await Task.Delay(100); // Allow time for activities to be captured

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().HaveCount(1, "Exactly 1 activity should be created.");
        capturedActivities[0].OperationName.Should().Be(ActivityNames.WorkflowBuild,
            "The activity should have the correct operation name for workflow build.");

        var events = capturedActivities[0].Events.ToList();
        events.Should().Contain(e => e.Name == EventNames.BuildStarted, "activity should have build started event");
        events.Should().Contain(e => e.Name == EventNames.BuildValidationCompleted, "activity should have build validation completed event");
        events.Should().Contain(e => e.Name == EventNames.BuildCompleted, "activity should have build completed event");

        var tags = capturedActivities[0].Tags.ToDictionary(t => t.Key, t => t.Value);
        tags.Should().ContainKey(Tags.WorkflowId);
        tags.Should().ContainKey(Tags.WorkflowDefinition);
    }
}
