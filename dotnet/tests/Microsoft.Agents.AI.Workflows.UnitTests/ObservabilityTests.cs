// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// </summary>
public sealed class ObservabilityTests : IDisposable
{
    private readonly ActivityListener _activityListener;
    private readonly List<Activity> _capturedActivities = [];
    private readonly List<Activity> _startedActivities = [];
    private readonly List<Activity> _stoppedActivities = [];
    private bool _isDisposed;

    public ObservabilityTests()
    {
        // Set up activity listener to capture activities from workflow
        this._activityListener = new ActivityListener
        {
            ShouldListenTo = source => source.Name.Contains(typeof(Workflow).Namespace!),
            Sample = (ref ActivityCreationOptions<ActivityContext> options) => ActivitySamplingResult.AllData,
            ActivityStarted = activity =>
            {
                this._capturedActivities.Add(activity);
                this._startedActivities.Add(activity);
            },
            ActivityStopped = activity => this._stoppedActivities.Add(activity)
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

    private static List<string> GetExpectedOrderedActivityNames() =>
    [
        ActivityNames.WorkflowBuild,
        ActivityNames.WorkflowRun,
        ActivityNames.EdgeGroupProcess,
        ActivityNames.ExecutorProcess,
        ActivityNames.MessageSend,
        ActivityNames.EdgeGroupProcess,
        ActivityNames.ExecutorProcess,
        ActivityNames.MessageSend
    ];

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

    [Theory]
    [InlineData("Default")]
    [InlineData("OffThread")]
    [InlineData("Concurrent")]
    [InlineData("Lockstep")]
    public async Task CreatesWorkflowEndToEndActivities_WithCorrectNameAsync(string executionEnvironmentName)
    {
        // Arrange
        var workflow = CreateWorkflow();

        // Act - consume the async enumerable to trigger activity creation
        var executionEnvironment = GetExecutionEnvironment(executionEnvironmentName);
        Run run = await executionEnvironment.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert
        this._capturedActivities.Should().HaveCount(8, "Exactly 8 activities should be created.");

        var expectedActivityNames = GetExpectedOrderedActivityNames();
        for (int i = 0; i < expectedActivityNames.Count; i++)
        {
            this._capturedActivities[i].OperationName.Should().Be(expectedActivityNames[i],
                $"Activity at index {i} should have the correct operation name.");
        }

        // Verify WorkflowRun activity events include workflow lifecycle events
        var workflowRunActivity = this._capturedActivities.First(a => a.OperationName == ActivityNames.WorkflowRun);
        var activityEvents = workflowRunActivity.Events.ToList();
        activityEvents.Should().Contain(e => e.Name == EventNames.WorkflowStarted, "activity should have workflow started event");
        activityEvents.Should().Contain(e => e.Name == EventNames.WorkflowCompleted, "activity should have workflow completed event");
    }

    [Fact]
    public void CreatesWorkflowActivities_WithCorrectName()
    {
        // Arrange & Act
        var workflow = CreateWorkflow();

        // Assert
        this._capturedActivities.Should().HaveCount(1, "Exactly 1 activities should be created.");
        this._capturedActivities[0].OperationName.Should().Be(ActivityNames.WorkflowBuild,
            "The activity should have the correct operation name for workflow build.");

        var events = this._capturedActivities[0].Events.ToList();
        events.Should().Contain(e => e.Name == EventNames.BuildStarted, "activity should have build started event");
        events.Should().Contain(e => e.Name == EventNames.BuildValidationCompleted, "activity should have build validation completed event");
        events.Should().Contain(e => e.Name == EventNames.BuildCompleted, "activity should have build completed event");

        var tags = this._capturedActivities[0].Tags.ToDictionary(t => t.Key, t => t.Value);
        tags.Should().ContainKey(Tags.WorkflowId);
        tags.Should().ContainKey(Tags.WorkflowDefinition);
    }
}
