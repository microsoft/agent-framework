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
    /// This workflow is expected to create 9 activities that will be captured by the tests
    /// - ActivityNames.WorkflowBuild
    /// - ActivityNames.WorkflowSession
    /// -- ActivityNames.WorkflowInvoke
    /// --- ActivityNames.EdgeGroupProcess
    /// --- ActivityNames.ExecutorProcess (UppercaseExecutor)
    /// ---- ActivityNames.MessageSend
    /// ----- ActivityNames.EdgeGroupProcess
    /// --- ActivityNames.ExecutorProcess (ReverseTextExecutor)
    /// ---- ActivityNames.MessageSend
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

        return builder.WithOpenTelemetry().Build();
    }

    private static Dictionary<string, int> GetExpectedActivityNameCounts() =>
        new()
        {
            { ActivityNames.WorkflowBuild, 1 },
            { ActivityNames.WorkflowSession, 1 },
            { ActivityNames.WorkflowInvoke, 1 },
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

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().HaveCount(9, "Exactly 9 activities should be created.");

        // Make sure all expected activities exist and have the correct count
        foreach (var kvp in GetExpectedActivityNameCounts())
        {
            var activityName = kvp.Key;
            var expectedCount = kvp.Value;
            var actualCount = capturedActivities.Count(a => a.OperationName.StartsWith(activityName, StringComparison.Ordinal));
            actualCount.Should().Be(expectedCount, $"Activity '{activityName}' should occur {expectedCount} times.");
        }

        // Verify WorkflowRun activity events include workflow lifecycle events
        var workflowRunActivity = capturedActivities.First(a => a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
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

    [Fact]
    public async Task TelemetryDisabledByDefault_CreatesNoActivitiesAsync()
    {
        // Arrange
        // Create a test activity to correlate captured activities
        using var testActivity = new Activity("ObservabilityTest").Start();

        // Act - Build workflow WITHOUT calling WithOpenTelemetry()
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        WorkflowBuilder builder = new(uppercase);
        builder.Build(); // No WithOpenTelemetry() call
        // Assert - No activities should be created
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().BeEmpty("No activities should be created when telemetry is disabled (default).");
    }

    [Fact]
    public async Task WithOpenTelemetry_UsesProvidedActivitySourceAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        using var userActivitySource = new ActivitySource("UserProvidedSource");

        // Set up a separate listener for the user-provided source
        ConcurrentBag<Activity> userActivities = [];
        using var userListener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == "UserProvidedSource",
            Sample = (ref ActivityCreationOptions<ActivityContext> options) => ActivitySamplingResult.AllData,
            ActivityStarted = activity => userActivities.Add(activity),
        };
        ActivitySource.AddActivityListener(userListener);

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        var workflow = builder.WithOpenTelemetry(activitySource: userActivitySource).Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "Hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = userActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().NotBeEmpty("Activities should be created with user-provided ActivitySource.");
        capturedActivities.Should().OnlyContain(
            a => a.Source.Name == "UserProvidedSource",
            "All activities should come from the user-provided ActivitySource.");
    }

    [Fact]
    public async Task DisableWorkflowBuild_PreventsWorkflowBuildActivityAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        builder.WithOpenTelemetry(configure: opts => opts.DisableWorkflowBuild = true).Build();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().NotContain(
            a => a.OperationName.StartsWith(ActivityNames.WorkflowBuild, StringComparison.Ordinal),
            "WorkflowBuild activity should be disabled.");
    }

    [Fact]
    public async Task DisableWorkflowRun_PreventsWorkflowRunActivityAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        builder.WithOutputFrom(uppercase);
        var workflow = builder.WithOpenTelemetry(configure: opts => opts.DisableWorkflowRun = true).Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "Hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().NotContain(
            a => a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal),
            "WorkflowRun activity should be disabled.");
        capturedActivities.Should().NotContain(
            a => a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal),
            "WorkflowSession activity should also be disabled when DisableWorkflowRun is true.");
        capturedActivities.Should().Contain(
            a => a.OperationName.StartsWith(ActivityNames.WorkflowBuild, StringComparison.Ordinal),
            "Other activities should still be created.");
    }

    [Fact]
    public async Task DisableExecutorProcess_PreventsExecutorProcessActivityAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        builder.WithOutputFrom(uppercase);
        var workflow = builder.WithOpenTelemetry(configure: opts => opts.DisableExecutorProcess = true).Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "Hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().NotContain(
            a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal),
            "ExecutorProcess activity should be disabled.");
        capturedActivities.Should().Contain(
            a => a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal),
            "Other activities should still be created.");
    }

    [Fact]
    public async Task DisableEdgeGroupProcess_PreventsEdgeGroupProcessActivityAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        var workflow = CreateWorkflowWithDisabledEdges();

        // Act
        Run run = await InProcessExecution.Default.RunAsync(workflow, "Hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().NotContain(
            a => a.OperationName.StartsWith(ActivityNames.EdgeGroupProcess, StringComparison.Ordinal),
            "EdgeGroupProcess activity should be disabled.");
        capturedActivities.Should().Contain(
            a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal),
            "Other activities should still be created.");
    }

    [Fact]
    public async Task DisableMessageSend_PreventsMessageSendActivityAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        var workflow = CreateWorkflowWithDisabledMessages();

        // Act
        Run run = await InProcessExecution.Default.RunAsync(workflow, "Hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        capturedActivities.Should().NotContain(
            a => a.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal),
            "MessageSend activity should be disabled.");
        capturedActivities.Should().Contain(
            a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal),
            "Other activities should still be created.");
    }

    private static Workflow CreateWorkflowWithDisabledEdges()
    {
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);

        return builder.WithOpenTelemetry(configure: opts => opts.DisableEdgeGroupProcess = true).Build();
    }

    private static Workflow CreateWorkflowWithDisabledMessages()
    {
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);

        return builder.WithOpenTelemetry(configure: opts => opts.DisableMessageSend = true).Build();
    }

    [Fact]
    public async Task EnableSensitiveData_LogsExecutorInputAndOutputAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        builder.WithOutputFrom(uppercase);
        var workflow = builder.WithOpenTelemetry(configure: opts => opts.EnableSensitiveData = true).Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var executorActivity = capturedActivities.FirstOrDefault(
            a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));

        executorActivity.Should().NotBeNull("ExecutorProcess activity should be created.");

        var tags = executorActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        tags.Should().ContainKey(Tags.ExecutorInput, "Input should be logged when EnableSensitiveData is true.");
        tags.Should().ContainKey(Tags.ExecutorOutput, "Output should be logged when EnableSensitiveData is true.");
        tags[Tags.ExecutorInput].Should().Contain("hello", "Input should contain the input value.");
        tags[Tags.ExecutorOutput].Should().Contain("HELLO", "Output should contain the transformed value.");
    }

    [Fact]
    public async Task EnableSensitiveData_Disabled_DoesNotLogInputOutputAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act - EnableSensitiveData is false by default
        WorkflowBuilder builder = new(uppercase);
        builder.WithOutputFrom(uppercase);
        var workflow = builder.WithOpenTelemetry().Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var executorActivity = capturedActivities.FirstOrDefault(
            a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));

        executorActivity.Should().NotBeNull("ExecutorProcess activity should be created.");

        var tags = executorActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        tags.Should().NotContainKey(Tags.ExecutorInput, "Input should NOT be logged when EnableSensitiveData is false.");
        tags.Should().NotContainKey(Tags.ExecutorOutput, "Output should NOT be logged when EnableSensitiveData is false.");
    }

    [Fact]
    public async Task EnableSensitiveData_LogsMessageSendContentAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        var workflow = builder.WithOpenTelemetry(configure: opts => opts.EnableSensitiveData = true).Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var messageSendActivity = capturedActivities.FirstOrDefault(
            a => a.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal));

        messageSendActivity.Should().NotBeNull("MessageSend activity should be created.");

        var tags = messageSendActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        tags.Should().ContainKey(Tags.MessageContent, "Message content should be logged when EnableSensitiveData is true.");
        tags.Should().ContainKey(Tags.MessageSourceId, "Source ID should be logged.");
    }

    [Fact]
    public async Task EnableSensitiveData_Disabled_DoesNotLogMessageContentAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        // Act - EnableSensitiveData is false by default
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        var workflow = builder.WithOpenTelemetry().Build();

        Run run = await InProcessExecution.Default.RunAsync(workflow, "hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var messageSendActivity = capturedActivities.FirstOrDefault(
            a => a.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal));

        messageSendActivity.Should().NotBeNull("MessageSend activity should be created.");

        var tags = messageSendActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        tags.Should().NotContainKey(Tags.MessageContent, "Message content should NOT be logged when EnableSensitiveData is false.");
        tags.Should().ContainKey(Tags.MessageSourceId, "Source ID should still be logged.");
    }
}
