// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests for <see cref="DeclarativeWorkflowOptions"/> telemetry configuration.
/// </summary>
[Collection("DeclarativeWorkflowOptionsTest")]
public sealed class DeclarativeWorkflowOptionsTest : IDisposable
{
    // These constants mirror Microsoft.Agents.AI.Workflows.Observability.ActivityNames
    // which is internal and not accessible from this test project.
    private const string WorkflowBuildActivityName = "workflow.build";
    private const string WorkflowRunActivityName = "workflow_invoke";

    // The default activity source name used by the workflow telemetry context.
    private const string DefaultTelemetrySourceName = "Microsoft.Agents.AI.Workflows";

    private const string SimpleWorkflowYaml = """
        kind: Workflow
        trigger:
          kind: OnConversationStart
          id: test_workflow
          actions:
            - kind: EndConversation
              id: end_all
        """;

    private readonly ActivitySource _activitySource = new("TestSource");
    private readonly ActivityListener _activityListener;
    private readonly ConcurrentBag<Activity> _capturedActivities = [];

    public DeclarativeWorkflowOptionsTest()
    {
        this._activityListener = new ActivityListener
        {
            ShouldListenTo = source =>
                source.Name == DefaultTelemetrySourceName ||
                source.Name == "TestSource",
            Sample = (ref ActivityCreationOptions<ActivityContext> options) => ActivitySamplingResult.AllData,
            ActivityStarted = activity => this._capturedActivities.Add(activity),
        };
        ActivitySource.AddActivityListener(this._activityListener);
    }

    public void Dispose()
    {
        this._activityListener.Dispose();
        this._activitySource.Dispose();
    }

    [Fact]
    public void ConfigureTelemetry_DefaultIsNull()
    {
        // Arrange
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();

        // Act
        DeclarativeWorkflowOptions options = new(mockProvider.Object);

        // Assert
        Assert.Null(options.ConfigureTelemetry);
    }

    [Fact]
    public void ConfigureTelemetry_CanBeSet()
    {
        // Arrange
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();
        bool callbackInvoked = false;

        // Act
        DeclarativeWorkflowOptions options = new(mockProvider.Object)
        {
            ConfigureTelemetry = opt =>
            {
                callbackInvoked = true;
                opt.EnableSensitiveData = true;
            }
        };

        // Assert
        Assert.NotNull(options.ConfigureTelemetry);
        WorkflowTelemetryOptions telemetryOptions = new();
        options.ConfigureTelemetry(telemetryOptions);
        Assert.True(callbackInvoked);
        Assert.True(telemetryOptions.EnableSensitiveData);
    }

    [Fact]
    public void TelemetryActivitySource_DefaultIsNull()
    {
        // Arrange
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();

        // Act
        DeclarativeWorkflowOptions options = new(mockProvider.Object);

        // Assert
        Assert.Null(options.TelemetryActivitySource);
    }

    [Fact]
    public void TelemetryActivitySource_CanBeSet()
    {
        // Arrange
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();

        // Act
        DeclarativeWorkflowOptions options = new(mockProvider.Object)
        {
            TelemetryActivitySource = this._activitySource
        };

        // Assert
        Assert.Same(this._activitySource, options.TelemetryActivitySource);
    }

    [Fact]
    public async Task BuildWorkflow_WithDefaultTelemetry_AppliesTelemetryAsync()
    {
        // Arrange
        using Activity testActivity = new Activity("DefaultTelemetryTest").Start()!;
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();
        DeclarativeWorkflowOptions options = new(mockProvider.Object)
        {
            ConfigureTelemetry = _ => { },
            LoggerFactory = NullLoggerFactory.Instance
        };

        // Act
        using StringReader reader = new(SimpleWorkflowYaml);
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(reader, options);

        await using Run run = await InProcessExecution.RunAsync(workflow, "test input");

        // Assert
        Activity[] capturedActivities = this._capturedActivities
            .Where(a => a.RootId == testActivity.RootId && a.Source.Name == DefaultTelemetrySourceName)
            .ToArray();

        Assert.NotEmpty(capturedActivities);
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(WorkflowBuildActivityName, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(WorkflowRunActivityName, StringComparison.Ordinal));
    }

    [Fact]
    public async Task BuildWorkflow_WithTelemetryActivitySource_AppliesTelemetryAsync()
    {
        // Arrange
        using Activity testActivity = new Activity("TelemetryActivitySourceTest").Start()!;
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();
        DeclarativeWorkflowOptions options = new(mockProvider.Object)
        {
            TelemetryActivitySource = this._activitySource,
            LoggerFactory = NullLoggerFactory.Instance
        };

        // Act
        using StringReader reader = new(SimpleWorkflowYaml);
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(reader, options);

        await using Run run = await InProcessExecution.RunAsync(workflow, "test input");

        // Assert
        Activity[] capturedActivities = this._capturedActivities
            .Where(a => a.RootId == testActivity.RootId && a.Source.Name == "TestSource")
            .ToArray();

        Assert.NotEmpty(capturedActivities);
        Assert.All(capturedActivities, a => Assert.Equal("TestSource", a.Source.Name));
    }

    [Fact]
    public async Task BuildWorkflow_WithConfigureTelemetry_AppliesConfigurationAsync()
    {
        // Arrange
        using Activity testActivity = new Activity("ConfigureTelemetryTest").Start()!;
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();
        bool configureInvoked = false;
        DeclarativeWorkflowOptions options = new(mockProvider.Object)
        {
            ConfigureTelemetry = opt =>
            {
                configureInvoked = true;
                opt.EnableSensitiveData = true;
            },
            LoggerFactory = NullLoggerFactory.Instance
        };

        // Act
        using StringReader reader = new(SimpleWorkflowYaml);
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(reader, options);

        await using Run run = await InProcessExecution.RunAsync(workflow, "test input");

        // Assert
        Assert.True(configureInvoked);

        Activity[] capturedActivities = this._capturedActivities
            .Where(a => a.RootId == testActivity.RootId && a.Source.Name == DefaultTelemetrySourceName)
            .ToArray();

        Assert.NotEmpty(capturedActivities);
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(WorkflowBuildActivityName, StringComparison.Ordinal));
        Assert.Contains(capturedActivities, a => a.OperationName.StartsWith(WorkflowRunActivityName, StringComparison.Ordinal));
    }

    [Fact]
    public async Task BuildWorkflow_WithoutTelemetry_DoesNotCreateActivitiesAsync()
    {
        // Arrange
        using Activity testActivity = new Activity("NoTelemetryTest").Start()!;
        Mock<ResponseAgentProvider> mockProvider = CreateMockProvider();
        DeclarativeWorkflowOptions options = new(mockProvider.Object)
        {
            LoggerFactory = NullLoggerFactory.Instance
        };

        // Act
        using StringReader reader = new(SimpleWorkflowYaml);
        Workflow workflow = DeclarativeWorkflowBuilder.Build<string>(reader, options);

        await using Run run = await InProcessExecution.RunAsync(workflow, "test input");

        // Assert - No workflow activities should be created when telemetry is disabled
        Activity[] capturedActivities = this._capturedActivities
            .Where(a => a.RootId == testActivity.RootId &&
                       (a.OperationName.StartsWith(WorkflowBuildActivityName, StringComparison.Ordinal) ||
                        a.OperationName.StartsWith(WorkflowRunActivityName, StringComparison.Ordinal)))
            .ToArray();

        Assert.Empty(capturedActivities);
    }

    private static Mock<ResponseAgentProvider> CreateMockProvider()
    {
        Mock<ResponseAgentProvider> mockAgentProvider = new(MockBehavior.Strict);
        mockAgentProvider
            .Setup(provider => provider.CreateConversationAsync(It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(Guid.NewGuid().ToString("N")));
        mockAgentProvider
            .Setup(provider => provider.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()))
            .Returns(Task.FromResult(new ChatMessage(ChatRole.Assistant, "Test response")));
        return mockAgentProvider;
    }
}
