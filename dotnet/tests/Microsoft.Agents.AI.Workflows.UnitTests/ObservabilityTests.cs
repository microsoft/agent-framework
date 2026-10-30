// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Extensions.AI;

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

        Assert.NotNull(executorActivity);

        var tags = executorActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        Assert.Contains(Tags.ExecutorInput, tags);
        Assert.Contains(Tags.ExecutorOutput, tags);
        Assert.Contains("hello", tags[Tags.ExecutorInput]);
        Assert.Contains("HELLO", tags[Tags.ExecutorOutput]);
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

        Assert.NotNull(executorActivity);

        var tags = executorActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        Assert.DoesNotContain(Tags.ExecutorInput, tags);
        Assert.DoesNotContain(Tags.ExecutorOutput, tags);
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

        Assert.NotNull(messageSendActivity);

        var tags = messageSendActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        Assert.Contains(Tags.MessageContent, tags);
        Assert.Contains(Tags.MessageSourceId, tags);
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

        Assert.NotNull(messageSendActivity);

        var tags = messageSendActivity!.Tags.ToDictionary(t => t.Key, t => t.Value);
        Assert.DoesNotContain(Tags.MessageContent, tags);
        Assert.Contains(Tags.MessageSourceId, tags);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task EnableSensitiveData_HostedAsAgent_ControlsGenericPayloadTagsAsync(
        bool includeSensitiveDataWhenHostedAsAgent,
        bool streaming)
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        AIAgent echoAgent = new TestEchoAgent(id: "echo-agent", name: "echo-agent");
        ExecutorBinding executor = echoAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });

        Workflow workflow = new WorkflowBuilder(executor)
            .WithOutputFrom(executor)
            .WithOpenTelemetry(configure: options =>
            {
                options.EnableSensitiveData = true;
                options.IncludeSensitiveDataWhenHostedAsAgent =
                    includeSensitiveDataWhenHostedAsAgent;
            })
            .Build();
        AIAgent hostedAgent = workflow.AsAIAgent(
            includeWorkflowOutputsInResponse: true);

        // Act
        ChatMessage input = new(ChatRole.User, "sensitive workflow input");
        AgentResponse response = streaming
            ? await hostedAgent.RunStreamingAsync(input).ToAgentResponseAsync()
            : await hostedAgent.RunAsync(input);

        // Assert
        Assert.Contains("sensitive workflow input", response.Text);

        List<Activity> capturedActivities =
            this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        List<Activity> executorActivities = capturedActivities
            .Where(a => a.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal))
            .ToList();
        List<Activity> messageSendActivities = capturedActivities
            .Where(a => a.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal))
            .ToList();

        Assert.NotEmpty(executorActivities);
        Assert.NotEmpty(messageSendActivities);

        if (includeSensitiveDataWhenHostedAsAgent)
        {
            Assert.Contains(
                executorActivities,
                activity => activity.Tags.Any(tag =>
                    string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                    string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal)));
            Assert.Contains(
                messageSendActivities,
                activity => activity.Tags.Any(tag =>
                    string.Equals(tag.Key, Tags.MessageContent, StringComparison.Ordinal)));
        }
        else
        {
            Assert.All(executorActivities, activity =>
            {
                Assert.DoesNotContain(
                    activity.Tags,
                    tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal));
                Assert.DoesNotContain(
                    activity.Tags,
                    tag => string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal));
            });
            Assert.All(messageSendActivities, activity =>
                Assert.DoesNotContain(
                    activity.Tags,
                    tag => string.Equals(tag.Key, Tags.MessageContent, StringComparison.Ordinal)));
        }
    }

    [Fact]
    public async Task EnableSensitiveData_HostedAsAgent_StreamingLockstepSuppressesPayloadTagsAcrossSuperstepsAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        AIAgent firstAgent = new TestEchoAgent(id: "first-agent", name: "FirstAgent");
        AIAgent secondAgent = new TestEchoAgent(id: "second-agent", name: "SecondAgent");
        ExecutorBinding first = firstAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });
        ExecutorBinding second = secondAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });

        Workflow workflow = new WorkflowBuilder(first)
            .AddEdge(first, second)
            .WithOutputFrom(second)
            .WithOpenTelemetry(configure: options => options.EnableSensitiveData = true)
            .Build();
        AIAgent hostedAgent = workflow.AsAIAgent(
            executionEnvironment: InProcessExecution.Lockstep,
            includeWorkflowOutputsInResponse: true);

        // Act
        AgentResponse response = await hostedAgent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "sensitive workflow input"))
            .ToAgentResponseAsync();

        // Assert
        Assert.Contains("sensitive workflow input", response.Text);

        List<Activity> capturedActivities =
            this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        Assert.Contains(
            capturedActivities,
            activity => activity.OperationName.Contains("SecondAgent", StringComparison.Ordinal));
        Assert.DoesNotContain(
            capturedActivities.SelectMany(activity => activity.Tags),
            tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                   string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal) ||
                   string.Equals(tag.Key, Tags.MessageContent, StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task EnableSensitiveData_HostedAsAgent_ControlsNestedWorkflowPayloadTagsAsync(
        bool includeSensitiveDataWhenHostedAsAgent)
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        AIAgent childFirstAgent = new TestEchoAgent(id: "child-first-agent", name: "ChildFirstAgent");
        AIAgent childSecondAgent = new TestEchoAgent(id: "child-second-agent", name: "ChildSecondAgent");
        ExecutorBinding childFirst = childFirstAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });
        ExecutorBinding childSecond = childSecondAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });

        Workflow childWorkflow = new WorkflowBuilder(childFirst)
            .AddEdge(childFirst, childSecond)
            .WithOutputFrom(childSecond)
            .WithOpenTelemetry(configure: options => options.EnableSensitiveData = true)
            .Build();
        ExecutorBinding child = childWorkflow.BindAsExecutor("ChildWorkflow");

        Workflow parentWorkflow = new WorkflowBuilder(child)
            .WithOutputFrom(child)
            .WithOpenTelemetry(configure: options =>
            {
                options.EnableSensitiveData = true;
                options.IncludeSensitiveDataWhenHostedAsAgent =
                    includeSensitiveDataWhenHostedAsAgent;
            })
            .Build();
        AIAgent hostedAgent = parentWorkflow.AsAIAgent(includeWorkflowOutputsInResponse: true);

        // Act
        AgentResponse response = await hostedAgent.RunAsync(
            new ChatMessage(ChatRole.User, "sensitive workflow input"));

        // Assert
        Assert.Contains("sensitive workflow input", response.Text);

        List<Activity> capturedActivities =
            this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        List<Activity> childExecutorActivities = capturedActivities
            .Where(activity =>
                activity.OperationName.Contains("ChildFirstAgent", StringComparison.Ordinal) ||
                activity.OperationName.Contains("ChildSecondAgent", StringComparison.Ordinal))
            .ToList();
        List<Activity> childMessageSendActivities = capturedActivities
            .Where(activity => activity.Tags.Any(tag =>
                string.Equals(tag.Key, Tags.MessageSourceId, StringComparison.Ordinal) &&
                tag.Value?.Contains("Child", StringComparison.Ordinal) == true))
            .ToList();

        Assert.NotEmpty(childExecutorActivities);
        Assert.NotEmpty(childMessageSendActivities);
        if (includeSensitiveDataWhenHostedAsAgent)
        {
            Assert.Contains(
                childExecutorActivities.SelectMany(activity => activity.Tags),
                tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                       string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal));
            Assert.Contains(
                childMessageSendActivities.SelectMany(activity => activity.Tags),
                tag => string.Equals(tag.Key, Tags.MessageContent, StringComparison.Ordinal));
        }
        else
        {
            Assert.DoesNotContain(
                capturedActivities.SelectMany(activity => activity.Tags),
                tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                       string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal) ||
                       string.Equals(tag.Key, Tags.MessageContent, StringComparison.Ordinal));
        }
    }

    [Fact]
    public async Task IncludeSensitiveDataWhenHostedAsAgent_AllowsNestedPayloadsWithoutParentSensitiveDataAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        AIAgent childFirstAgent = new TestEchoAgent(id: "child-first-agent", name: "ChildFirstAgent");
        AIAgent childSecondAgent = new TestEchoAgent(id: "child-second-agent", name: "ChildSecondAgent");
        ExecutorBinding childFirst = childFirstAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });
        ExecutorBinding childSecond = childSecondAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });

        Workflow childWorkflow = new WorkflowBuilder(childFirst)
            .AddEdge(childFirst, childSecond)
            .WithOutputFrom(childSecond)
            .WithOpenTelemetry(configure: options => options.EnableSensitiveData = true)
            .Build();
        ExecutorBinding child = childWorkflow.BindAsExecutor("ChildWorkflow");

        Workflow parentWorkflow = new WorkflowBuilder(child)
            .WithOutputFrom(child)
            .WithOpenTelemetry(configure: options =>
                options.IncludeSensitiveDataWhenHostedAsAgent = true)
            .Build();
        AIAgent hostedAgent = parentWorkflow.AsAIAgent(includeWorkflowOutputsInResponse: true);

        // Act
        AgentResponse response = await hostedAgent.RunAsync(
            new ChatMessage(ChatRole.User, "sensitive workflow input"));

        // Assert
        Assert.Contains("sensitive workflow input", response.Text);

        List<Activity> capturedActivities =
            this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        List<Activity> parentExecutorActivities = capturedActivities
            .Where(activity => activity.OperationName.Contains("ChildWorkflow", StringComparison.Ordinal))
            .ToList();
        List<Activity> childExecutorActivities = capturedActivities
            .Where(activity =>
                activity.OperationName.Contains("ChildFirstAgent", StringComparison.Ordinal) ||
                activity.OperationName.Contains("ChildSecondAgent", StringComparison.Ordinal))
            .ToList();

        Assert.NotEmpty(parentExecutorActivities);
        Assert.NotEmpty(childExecutorActivities);
        Assert.DoesNotContain(
            parentExecutorActivities.SelectMany(activity => activity.Tags),
            tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                   string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal));
        Assert.Contains(
            childExecutorActivities.SelectMany(activity => activity.Tags),
            tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                   string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal));
    }

    [Fact]
    public async Task HostedAsAgent_OuterSuppressionOverridesNestedHostedAgentOptInAsync()
    {
        // Arrange
        using var testActivity = new Activity("ObservabilityTest").Start();
        AIAgent innerEchoAgent = new TestEchoAgent(id: "inner-echo-agent", name: "InnerEchoAgent");
        ExecutorBinding innerEcho = innerEchoAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });

        Workflow innerWorkflow = new WorkflowBuilder(innerEcho)
            .WithOutputFrom(innerEcho)
            .WithOpenTelemetry(configure: options =>
            {
                options.EnableSensitiveData = true;
                options.IncludeSensitiveDataWhenHostedAsAgent = true;
            })
            .Build();
        AIAgent innerHostedAgent = innerWorkflow.AsAIAgent(
            name: "InnerHostedWorkflow",
            includeWorkflowOutputsInResponse: true);
        ExecutorBinding innerHosted = innerHostedAgent.BindAsExecutor(
            new AIAgentHostOptions { EmitAgentResponseEvents = true });

        Workflow outerWorkflow = new WorkflowBuilder(innerHosted)
            .WithOutputFrom(innerHosted)
            .WithOpenTelemetry(configure: options => options.EnableSensitiveData = true)
            .Build();
        AIAgent outerHostedAgent = outerWorkflow.AsAIAgent(includeWorkflowOutputsInResponse: true);

        // Act
        AgentResponse response = await outerHostedAgent.RunAsync(
            new ChatMessage(ChatRole.User, "sensitive workflow input"));

        // Assert
        Assert.Contains("sensitive workflow input", response.Text);

        List<Activity> capturedActivities =
            this._capturedActivities.Where(a => a.RootId == testActivity.RootId).ToList();
        Assert.Contains(
            capturedActivities,
            activity => activity.OperationName.Contains("InnerEchoAgent", StringComparison.Ordinal));
        Assert.DoesNotContain(
            capturedActivities.SelectMany(activity => activity.Tags),
            tag => string.Equals(tag.Key, Tags.ExecutorInput, StringComparison.Ordinal) ||
                   string.Equals(tag.Key, Tags.ExecutorOutput, StringComparison.Ordinal) ||
                   string.Equals(tag.Key, Tags.MessageContent, StringComparison.Ordinal));
    }

    [Fact]
    public async Task EnableSensitiveData_UnserializableMessage_DoesNotFailWorkflowAsync()
    {
        // Arrange
        const string SenderId = "UnserializableMessageSender";
        const string ReceiverId = "UnserializableMessageReceiver";
        const string ExpectedOutput = "done";
        string expectedFallback = $"[Unserializable: {typeof(ChatMessage).FullName}]";

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
        Workflow workflow = builder.WithOpenTelemetry(configure: opts => opts.EnableSensitiveData = true).Build();

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
        Assert.Contains(
            capturedActivities,
            activity => activity.OperationName.StartsWith(ActivityNames.MessageSend, StringComparison.Ordinal)
                && Equals(expectedFallback, activity.GetTagItem(Tags.MessageContent)));

        Assert.Contains(
            capturedActivities,
            activity => activity.OperationName.StartsWith(ActivityNames.ExecutorProcess, StringComparison.Ordinal)
                && Equals(expectedFallback, activity.GetTagItem(Tags.ExecutorInput)));
    }

    [Fact]
    public void EnableSensitiveData_UnserializableExecutorInputAndOutput_UsesFallback()
    {
        // Arrange
        string expectedFallback = $"[Unserializable: {typeof(ChatMessage).FullName}]";
        ChatMessage message = CreateUnserializableMessage();
        WorkflowTelemetryContext context = new(new WorkflowTelemetryOptions { EnableSensitiveData = true });

        // Act
        using Activity? activity = context.StartExecutorProcessActivity(
            "TestExecutor",
            typeof(ObservabilityTests).FullName,
            typeof(ChatMessage).FullName!,
            message);
        context.SetExecutorOutput(activity, message);

        // Assert
        Assert.NotNull(activity);
        Assert.Equal(expectedFallback, activity!.GetTagItem(Tags.ExecutorInput));
        Assert.Equal(expectedFallback, activity.GetTagItem(Tags.ExecutorOutput));
    }

    [Fact]
    public void EnableSensitiveData_SerializationThrowsInvalidOperation_UsesFallback()
    {
        // Arrange
        // Reflection-disabled (Native AOT) apps surface serialization failures as InvalidOperationException,
        // which System.Text.Json does not wrap. A throwing property getter reproduces that escape path.
        string expectedFallback = $"[Unserializable: {typeof(ThrowingMessage).FullName}]";
        WorkflowTelemetryContext context = new(new WorkflowTelemetryOptions { EnableSensitiveData = true });

        // Act
        using Activity? activity = context.StartMessageSendActivity("source", "target", new ThrowingMessage());

        // Assert
        Assert.NotNull(activity);
        Assert.Equal(expectedFallback, activity!.GetTagItem(Tags.MessageContent));
    }

    [Theory]
    [InlineData(typeof(ArgumentException))]
    [InlineData(typeof(IOException))]
    [InlineData(typeof(OperationCanceledException))]
    [InlineData(typeof(TimeoutException))]
    public void EnableSensitiveData_SerializationThrowsAnyException_UsesFallback(Type exceptionType)
    {
        // Arrange
        // System.Text.Json does not wrap property-getter exceptions, so serialization can surface any
        // exception type. Telemetry must fall back rather than fail the workflow for all of them.
        string expectedFallback = $"[Unserializable: {typeof(ThrowingMessage).FullName}]";
        WorkflowTelemetryContext context = new(new WorkflowTelemetryOptions { EnableSensitiveData = true });

        // Act
        using Activity? activity = context.StartMessageSendActivity("source", "target", new ThrowingMessage(exceptionType));

        // Assert
        Assert.NotNull(activity);
        Assert.Equal(expectedFallback, activity!.GetTagItem(Tags.MessageContent));
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

    private sealed class ThrowingMessage(Type exceptionType)
    {
        public ThrowingMessage() : this(typeof(InvalidOperationException))
        {
        }

        public string Value => throw (Exception)Activator.CreateInstance(exceptionType, "serialization failed")!;
    }
}
