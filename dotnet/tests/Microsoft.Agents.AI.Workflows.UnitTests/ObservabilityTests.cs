// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Extensions.AI;
using OpenTelemetry;

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
    private static Workflow CreateWorkflow(string? name = null)
    {
        // Create the executors
        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        Func<string, string> reverseFunc = s => new string(s.Reverse().ToArray());
        var reverse = reverseFunc.BindAsExecutor("ReverseTextExecutor");

        // Build the workflow by connecting executors sequentially
        WorkflowBuilder builder = new(uppercase);
        builder.AddEdge(uppercase, reverse).WithOutputFrom(reverse);
        if (name is not null)
        {
            builder.WithName(name);
        }

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
        Assert.Equal(9, capturedActivities.Count);

        // Make sure all expected activities exist and have the correct count
        foreach (var kvp in GetExpectedActivityNameCounts())
        {
            var activityName = kvp.Key;
            var expectedCount = kvp.Value;
            var actualCount = capturedActivities.Count(a => a.OperationName.StartsWith(activityName, StringComparison.Ordinal));
            Assert.Equal(expectedCount, actualCount);
        }

        // Verify WorkflowRun activity events include workflow lifecycle events
        var workflowRunActivity = capturedActivities.First(a => a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
        var activityEvents = workflowRunActivity.Events.ToList();
        Assert.Contains(activityEvents, e => e.Name == EventNames.WorkflowStarted);
        Assert.Contains(activityEvents, e => e.Name == EventNames.WorkflowCompleted);
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

    [Theory]
    [InlineData("Lockstep", false, null)]
    [InlineData("Lockstep", true, null)]
    [InlineData("OffThread", false, null)]
    [InlineData("OffThread", true, null)]
    [InlineData("Concurrent", false, null)]
    [InlineData("Concurrent", true, null)]
    [InlineData("Lockstep", false, "customer_support_pipeline")]
    [InlineData("Lockstep", true, "customer_support_pipeline")]
    [InlineData("OffThread", false, "customer_support_pipeline")]
    [InlineData("OffThread", true, "customer_support_pipeline")]
    [InlineData("Concurrent", false, "customer_support_pipeline")]
    [InlineData("Concurrent", true, "customer_support_pipeline")]
    public async Task WorkflowRunActivity_UsesSemanticConventionNameAsync(string executionEnvironmentName, bool streaming, string? workflowName)
    {
        // Arrange
        using var testActivity = new Activity("WorkflowRunSpanNameTest").Start();
        testActivity.AddBaggage("gen_ai.conversation.id", "application-thread");
        var workflow = CreateWorkflow(workflowName);
        var executionEnvironment = GetExecutionEnvironment(executionEnvironmentName);

        // Act
        if (streaming)
        {
            await using StreamingRun run = await executionEnvironment.RunStreamingAsync(workflow, "Hello, World!");
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                // Drain the stream to complete the workflow invocation.
            }
        }
        else
        {
            await using Run run = await executionEnvironment.RunAsync(workflow, "Hello, World!");
        }

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var workflowRunActivity = Assert.Single(capturedActivities, a =>
            a.Events.Any(e => e.Name == EventNames.WorkflowStarted));
        string expectedSpanName = workflowName is null ? "invoke_workflow" : $"invoke_workflow {workflowName}";
        Assert.Equal(expectedSpanName, workflowRunActivity.OperationName);
        Assert.Equal(expectedSpanName, workflowRunActivity.DisplayName);
        Assert.Equal(workflowName, workflowRunActivity.GetTagItem("gen_ai.workflow.name"));
        Assert.Equal("invoke_workflow", workflowRunActivity.GetTagItem("gen_ai.operation.name"));
        Assert.Equal("application-thread", workflowRunActivity.GetTagItem("gen_ai.conversation.id"));
        Assert.IsType<string>(workflowRunActivity.GetTagItem("session.id"));
        Assert.All(capturedActivities.Where(a => a != workflowRunActivity), a =>
            Assert.DoesNotContain(a.TagObjects, tag => tag.Key is "gen_ai.operation.name" or "gen_ai.conversation.id"));

        var workflowBuildActivity = Assert.Single(capturedActivities, a => a.OperationName == ActivityNames.WorkflowBuild);
        Assert.Equal(workflowName, workflowBuildActivity.GetTagItem("gen_ai.workflow.name"));
        Assert.All(capturedActivities, a => Assert.DoesNotContain(a.TagObjects, tag => tag.Key == "workflow.name"));
    }

    [Theory]
    [InlineData(null, "invoke_workflow")]
    [InlineData("", "invoke_workflow")]
    [InlineData(" ", "invoke_workflow")]
    [InlineData("customer_support_pipeline", "invoke_workflow customer_support_pipeline")]
    public void WorkflowRunActivity_ProvidesSemanticConventionsAtCreation(string? workflowName, string expectedSpanName)
    {
        // Arrange
        using var activitySource = new ActivitySource("WorkflowOperationNameSamplingTest");
        string? spanNameAtCreation = null;
        object? operationNameAtCreation = null;
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source == activitySource,
            Sample = (ref ActivityCreationOptions<ActivityContext> options) =>
            {
                spanNameAtCreation = options.Name;
                operationNameAtCreation = options.Tags?.FirstOrDefault(tag => tag.Key == "gen_ai.operation.name").Value;
                return ActivitySamplingResult.AllData;
            },
        };
        ActivitySource.AddActivityListener(listener);
        var telemetryContext = new WorkflowTelemetryContext(new WorkflowTelemetryOptions(), activitySource);

        // Act
        using Activity? activity = telemetryContext.StartWorkflowRunActivity(workflowName);

        // Assert
        Assert.NotNull(activity);
        Assert.Equal(expectedSpanName, spanNameAtCreation);
        Assert.Equal("invoke_workflow", operationNameAtCreation);
    }

    [Theory]
    [InlineData(null, null, null)]
    [InlineData("", null, null)]
    [InlineData(" ", null, null)]
    [InlineData("otel-thread", null, "otel-thread")]
    [InlineData("otel-thread", "activity-thread", "otel-thread")]
    [InlineData(null, "activity-thread", "activity-thread")]
    [InlineData("", "activity-thread", "activity-thread")]
    [InlineData(" ", "activity-thread", "activity-thread")]
    public void WorkflowRunActivity_UsesConversationContextAtCreation(
        string? otelConversationId, string? activityConversationId, string? expectedConversationId)
    {
        // Arrange
        using var testActivity = new Activity("WorkflowConversationContextTest").Start();
        testActivity.AddBaggage("gen_ai.conversation.id", activityConversationId);
        using var activitySource = new ActivitySource("WorkflowConversationSamplingTest");
        object? conversationIdAtCreation = null;
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source == activitySource,
            Sample = (ref ActivityCreationOptions<ActivityContext> options) =>
            {
                conversationIdAtCreation = options.Tags?.FirstOrDefault(tag => tag.Key == "gen_ai.conversation.id").Value;
                return ActivitySamplingResult.AllData;
            },
        };
        ActivitySource.AddActivityListener(listener);
        var telemetryContext = new WorkflowTelemetryContext(new WorkflowTelemetryOptions(), activitySource);
        Baggage previousBaggage = Baggage.Current;

        try
        {
            Baggage.SetBaggage("gen_ai.conversation.id", otelConversationId);

            // Act
            using Activity? activity = telemetryContext.StartWorkflowRunActivity("customer_support_pipeline");

            // Assert
            Assert.NotNull(activity);
            Assert.Equal(expectedConversationId, conversationIdAtCreation);
            Assert.Equal(expectedConversationId, activity.GetTagItem("gen_ai.conversation.id"));
            if (expectedConversationId is null)
            {
                Assert.DoesNotContain(activity.TagObjects, tag => tag.Key == "gen_ai.conversation.id");
            }
        }
        finally
        {
            Baggage.Current = previousBaggage;
        }
    }

    [Theory]
    [InlineData("Lockstep", null)]
    [InlineData("OffThread", null)]
    [InlineData("Concurrent", null)]
    [InlineData("Lockstep", "execution-only-session")]
    [InlineData("OffThread", "execution-only-session")]
    [InlineData("Concurrent", "execution-only-session")]
    public async Task WorkflowRunActivity_WithoutConversationContext_DoesNotUseSessionIdAsync(string executionEnvironmentName, string? sessionId)
    {
        // Arrange
        using var testActivity = new Activity("WorkflowConversationOmissionTest").Start();
        var workflow = CreateWorkflow("customer_support_pipeline");
        var executionEnvironment = GetExecutionEnvironment(executionEnvironmentName);

        // Act
        Run run = await executionEnvironment.RunAsync(workflow, "Hello, World!", sessionId);
        await run.DisposeAsync();

        // Assert
        var workflowRunActivity = Assert.Single(this._capturedActivities, a =>
            a.RootId == testActivity.RootId &&
            a.Events.Any(e => e.Name == EventNames.WorkflowStarted));
        Assert.DoesNotContain(workflowRunActivity.TagObjects, tag => tag.Key == "gen_ai.conversation.id");
        Assert.IsType<string>(workflowRunActivity.GetTagItem("session.id"));
        if (sessionId is not null)
        {
            Assert.Equal(sessionId, workflowRunActivity.GetTagItem("session.id"));
        }
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    public async Task WorkflowActivities_WithoutMeaningfulName_OmitWorkflowNameAsync(string workflowName)
    {
        // Arrange
        using var testActivity = new Activity("WorkflowNameOmissionTest").Start();
        var workflow = CreateWorkflow(workflowName);

        // Act
        Run run = await InProcessExecution.Default.RunAsync(workflow, "Hello, World!");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        Assert.Contains(capturedActivities, a => a.OperationName == ActivityNames.WorkflowInvoke);
        Assert.All(capturedActivities, a => Assert.DoesNotContain(a.TagObjects,
            tag => tag.Key is "gen_ai.workflow.name" or "workflow.name"));
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
        var capturedActivity = Assert.Single(capturedActivities);
        Assert.Equal(ActivityNames.WorkflowBuild, capturedActivity.OperationName);

        var events = capturedActivity.Events.ToList();
        Assert.Contains(events, e => e.Name == EventNames.BuildStarted);
        Assert.Contains(events, e => e.Name == EventNames.BuildValidationCompleted);
        Assert.Contains(events, e => e.Name == EventNames.BuildCompleted);

        var tags = capturedActivities[0].Tags.ToDictionary(t => t.Key, t => t.Value);
        Assert.Contains(Tags.WorkflowId, tags);
        Assert.Contains(Tags.WorkflowDefinition, tags);
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
        Assert.Empty(capturedActivities ?? []);
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
        Assert.NotEmpty(capturedActivities);
        Assert.All(capturedActivities, a => Assert.True(a.Source.Name == "UserProvidedSource"));
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
        Assert.DoesNotContain(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.WorkflowBuild, StringComparison.Ordinal));
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
        Assert.DoesNotContain(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
        Assert.DoesNotContain(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.WorkflowSession, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.WorkflowBuild, StringComparison.Ordinal));
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
        Assert.DoesNotContain(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.WorkflowInvoke, StringComparison.Ordinal));
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
        Assert.DoesNotContain(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.EdgeGroupProcess, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));
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
        Assert.DoesNotContain(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));
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

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task EnableSensitiveData_DoesNotLogExecutorInputAndOutputAsync(bool enableSensitiveData)
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();

        Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
        var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

        // Act
        WorkflowBuilder builder = new(uppercase);
        builder.WithOutputFrom(uppercase);
#pragma warning disable CS0618 // Verify compatibility with the deprecated option.
        var workflow = builder.WithOpenTelemetry(configure: opts => opts.EnableSensitiveData = enableSensitiveData).Build();
#pragma warning restore CS0618

        Run run = await InProcessExecution.Default.RunAsync(workflow, "hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var executorActivity = capturedActivities.FirstOrDefault(
            a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));

        Assert.NotNull(executorActivity);

        Assert.Equal("UppercaseExecutor", executorActivity.GetTagItem(Tags.ExecutorId));
        Assert.NotNull(executorActivity.GetTagItem(Tags.ExecutorType));
        Assert.NotNull(executorActivity.GetTagItem(Tags.MessageType));
        Assert.All(capturedActivities, activity =>
            Assert.DoesNotContain(activity.TagObjects, tag => tag.Key is "executor.input" or "executor.output"));
        Assert.Equal("HELLO", Assert.Single(run.OutgoingEvents.OfType<WorkflowOutputEvent>()).Data);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task EnableSensitiveData_DoesNotLogMessageContentAsync(bool enableSensitiveData)
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
#pragma warning disable CS0618 // Verify compatibility with the deprecated option.
        var workflow = builder.WithOpenTelemetry(configure: opts => opts.EnableSensitiveData = enableSensitiveData).Build();
#pragma warning restore CS0618

        Run run = await InProcessExecution.Default.RunAsync(workflow, "hello");
        await run.DisposeAsync();

        // Assert
        var capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        var messageSendActivities = capturedActivities.Where(
            a => a.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal)).ToList();
        Assert.NotEmpty(messageSendActivities);
        Assert.All(messageSendActivities, activity => Assert.NotNull(activity.GetTagItem(Tags.MessageSourceId)));
        Assert.All(capturedActivities, activity =>
            Assert.DoesNotContain(activity.TagObjects, tag => tag.Key == "message.content"));
        Assert.Equal("OLLEH", Assert.Single(run.OutgoingEvents.OfType<WorkflowOutputEvent>()).Data);
    }

    [Fact]
    public async Task EnableSensitiveData_UnserializableMessage_DoesNotFailWorkflowAsync()
    {
        // Arrange
        const string SenderId = "UnserializableMessageSender";
        const string ReceiverId = "UnserializableMessageReceiver";
        const string ExpectedOutput = "done";
        using var testActivity = new Activity("ObservabilityTest").Start();

        var sender = new UnserializableMessageSender(SenderId, ReceiverId);
        List<ChatMessage> received = [];
        Func<ChatMessage, string> consume = message =>
        {
            received.Add(message);
            return ExpectedOutput;
        };
        var receiver = consume.BindAsExecutor(ReceiverId);

        WorkflowBuilder builder = new(sender);
        builder.AddEdge(sender, receiver).WithOutputFrom(receiver);
#pragma warning disable CS0618 // Verify compatibility with the deprecated option.
        Workflow workflow = builder.WithOpenTelemetry(configure: opts => opts.EnableSensitiveData = true).Build();
#pragma warning restore CS0618

        // Act
        Run run = await InProcessExecution.Default.RunAsync(workflow, "start");
        await run.DisposeAsync();

        // Assert
        Assert.Empty(run.OutgoingEvents.OfType<WorkflowErrorEvent>() ?? []);
        WorkflowOutputEvent output = Assert.Single(run.OutgoingEvents.OfType<WorkflowOutputEvent>());
        Assert.Equal(ExpectedOutput, output.Data);

        ChatMessage delivered = Assert.Single(received);
        Assert.IsType<UnregisteredAIContent>(Assert.Single(delivered.Contents));

        List<Activity> capturedActivities = this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        Assert.Contains(capturedActivities, activity => activity.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, activity => activity.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal));
        Assert.All(capturedActivities, activity =>
            Assert.DoesNotContain(activity.TagObjects, tag => tag.Key is "executor.input" or "executor.output" or "message.content"));
    }

    private static ChatMessage CreateUnserializableMessage() =>
        new(ChatRole.Assistant, [new UnregisteredAIContent()]);

    private sealed class UnserializableMessageSender(string id, string targetId) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            protocolBuilder.RouteBuilder.AddHandler<string>(
                (_, context) => context.SendMessageAsync(CreateUnserializableMessage(), targetId));

            return protocolBuilder.SendsMessage<ChatMessage>();
        }
    }

    private sealed class UnregisteredAIContent : AIContent;

}
