// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Moq;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

public sealed class DurableStreamingWorkflowRunTests
{
    private const string InstanceId = "test-instance-123";
    private const string WorkflowTestName = "TestWorkflow";

    private static Workflow CreateTestWorkflow() =>
        new WorkflowBuilder(new FunctionExecutor<string>("start", (_, _, _) => default))
            .WithName(WorkflowTestName)
            .Build();

    private static OrchestrationMetadata CreateMetadata(
        OrchestrationRuntimeStatus status,
        string? serializedCustomStatus = null,
        string? serializedOutput = null,
        TaskFailureDetails? failureDetails = null)
    {
        return new OrchestrationMetadata(WorkflowTestName, InstanceId)
        {
            RuntimeStatus = status,
            SerializedCustomStatus = serializedCustomStatus,
            SerializedOutput = serializedOutput,
            FailureDetails = failureDetails,
        };
    }

    private static string SerializeCustomStatus(List<string> events)
    {
        DurableWorkflowCustomStatus status = new() { Events = events };
        return JsonSerializer.Serialize(status, DurableWorkflowJsonContext.Default.DurableWorkflowCustomStatus);
    }

    private static string SerializeWorkflowResult(string? result, List<string> events)
    {
        DurableWorkflowResult workflowResult = new() { Result = result, Events = events };
        string inner = JsonSerializer.Serialize(workflowResult, DurableWorkflowJsonContext.Default.DurableWorkflowResult);
        return JsonSerializer.Serialize(inner);
    }

    private static string SerializeEvent(WorkflowEvent evt)
    {
        Type eventType = evt.GetType();
        TypedPayload wrapper = new()
        {
            TypeName = eventType.AssemblyQualifiedName,
            Data = JsonSerializer.Serialize(evt, eventType, DurableSerialization.Options)
        };

        return JsonSerializer.Serialize(wrapper, DurableWorkflowJsonContext.Default.TypedPayload);
    }

    #region Constructor and Properties

    [Fact]
    public void Constructor_SetsRunIdAndWorkflowName()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");

        // Act
        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Assert
        Assert.Equal(InstanceId, run.RunId);
        Assert.Equal(WorkflowTestName, run.WorkflowName);
    }

    [Fact]
    public void Constructor_NoWorkflowName_SetsEmptyString()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        Workflow workflow = new WorkflowBuilder(new FunctionExecutor<string>("start", (_, _, _) => default)).Build();

        // Act
        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, workflow);

        // Assert
        Assert.Equal(string.Empty, run.WorkflowName);
    }

    #endregion

    #region GetStatusAsync

    [Theory]
    [InlineData(OrchestrationRuntimeStatus.Pending, DurableRunStatus.Pending)]
    [InlineData(OrchestrationRuntimeStatus.Running, DurableRunStatus.Running)]
    [InlineData(OrchestrationRuntimeStatus.Completed, DurableRunStatus.Completed)]
    [InlineData(OrchestrationRuntimeStatus.Failed, DurableRunStatus.Failed)]
    [InlineData(OrchestrationRuntimeStatus.Terminated, DurableRunStatus.Terminated)]
    [InlineData(OrchestrationRuntimeStatus.Suspended, DurableRunStatus.Suspended)]

    public async Task GetStatusAsync_MapsRuntimeStatusCorrectlyAsync(
        OrchestrationRuntimeStatus runtimeStatus,
        DurableRunStatus expectedStatus)
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, false, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(runtimeStatus));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        DurableRunStatus status = await run.GetStatusAsync();

        // Assert
        Assert.Equal(expectedStatus, status);
    }

    [Fact]
    public async Task GetStatusAsync_InstanceNotFound_ReturnsNotFoundAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, false, It.IsAny<CancellationToken>()))
            .ReturnsAsync((OrchestrationMetadata?)null);

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        DurableRunStatus status = await run.GetStatusAsync();

        // Assert
        Assert.Equal(DurableRunStatus.NotFound, status);
    }

    #endregion

    #region WatchStreamAsync

    [Fact]
    public async Task WatchStreamAsync_InstanceNotFound_YieldsNoEventsAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync((OrchestrationMetadata?)null);

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Empty(events);
    }

    [Fact]
    public async Task WatchStreamAsync_CompletedWithResult_YieldsCompletedEventAsync()
    {
        // Arrange
        string serializedOutput = SerializeWorkflowResult("done", []);
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: serializedOutput));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Single(events);
        DurableWorkflowCompletedEvent completedEvent = Assert.IsType<DurableWorkflowCompletedEvent>(events[0]);
        Assert.Equal("done", completedEvent.Data);
    }

    [Fact]
    public async Task WatchStreamAsync_CompletedWithEventsInOutput_YieldsEventsAndCompletionAsync()
    {
        // Arrange
        DurableHaltRequestedEvent haltEvent = new("executor-1");
        string serializedEvent = SerializeEvent(haltEvent);
        string serializedOutput = SerializeWorkflowResult("result", [serializedEvent]);

        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: serializedOutput));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Equal(2, events.Count);
        Assert.IsType<DurableHaltRequestedEvent>(events[0]);
        Assert.IsType<DurableWorkflowCompletedEvent>(events[1]);
    }

    [Fact]
    public async Task WatchStreamAsync_CompletedWithoutWrapper_YieldsRawOutputAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: "\"raw output\""));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Single(events);
        DurableWorkflowCompletedEvent completedEvent = Assert.IsType<DurableWorkflowCompletedEvent>(events[0]);
        Assert.Equal("\"raw output\"", completedEvent.Data);
    }

    [Fact]
    public async Task WatchStreamAsync_Failed_YieldsFailedEventAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(
                OrchestrationRuntimeStatus.Failed,
                failureDetails: new TaskFailureDetails("ErrorType", "Something went wrong", null, null, null)));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Single(events);
        DurableWorkflowFailedEvent failedEvent = Assert.IsType<DurableWorkflowFailedEvent>(events[0]);
        Assert.Equal("Something went wrong", failedEvent.Data);
    }

    [Fact]
    public async Task WatchStreamAsync_FailedWithNoDetails_YieldsDefaultMessageAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Failed));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Single(events);
        DurableWorkflowFailedEvent failedEvent = Assert.IsType<DurableWorkflowFailedEvent>(events[0]);
        Assert.Equal("Workflow execution failed.", failedEvent.Data);
    }

    [Fact]
    public async Task WatchStreamAsync_Terminated_YieldsFailedEventAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Terminated));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Single(events);
        DurableWorkflowFailedEvent failedEvent = Assert.IsType<DurableWorkflowFailedEvent>(events[0]);
        Assert.Equal("Workflow was terminated.", failedEvent.Data);
    }

    [Fact]
    public async Task WatchStreamAsync_EventsInCustomStatus_YieldsEventsBeforeCompletionAsync()
    {
        // Arrange
        DurableHaltRequestedEvent haltEvent = new("exec-1");
        string serializedEvent = SerializeEvent(haltEvent);
        string customStatus = SerializeCustomStatus([serializedEvent]);
        string serializedOutput = SerializeWorkflowResult("final", []);

        int callCount = 0;
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(() =>
            {
                callCount++;
                if (callCount == 1)
                {
                    return CreateMetadata(OrchestrationRuntimeStatus.Running, serializedCustomStatus: customStatus);
                }

                return CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: serializedOutput);
            });

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        Assert.Equal(2, events.Count);
        Assert.IsType<DurableHaltRequestedEvent>(events[0]);
        Assert.IsType<DurableWorkflowCompletedEvent>(events[1]);
    }

    [Fact]
    public async Task WatchStreamAsync_IncrementalEvents_YieldsOnlyNewEventsPerPollAsync()
    {
        // Arrange — simulate 3 poll cycles where events accumulate in custom status,
        // then a final completion poll. This validates:
        //   1. Events arriving across multiple poll cycles are yielded incrementally
        //   2. Already-seen events are not re-yielded (lastReadEventIndex dedup)
        //   3. Completion event follows all streamed events
        DurableHaltRequestedEvent event1 = new("executor-1");
        DurableHaltRequestedEvent event2 = new("executor-2");
        DurableHaltRequestedEvent event3 = new("executor-3");

        string serializedEvent1 = SerializeEvent(event1);
        string serializedEvent2 = SerializeEvent(event2);
        string serializedEvent3 = SerializeEvent(event3);

        // Poll 1: 1 event in custom status
        string customStatus1 = SerializeCustomStatus([serializedEvent1]);
        // Poll 2: same event + 1 new event (accumulating list)
        string customStatus2 = SerializeCustomStatus([serializedEvent1, serializedEvent2]);
        // Poll 3: all 3 events accumulated
        string customStatus3 = SerializeCustomStatus([serializedEvent1, serializedEvent2, serializedEvent3]);
        // Poll 4: completed, all events also in output
        string serializedOutput = SerializeWorkflowResult("done", [serializedEvent1, serializedEvent2, serializedEvent3]);

        int callCount = 0;
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(() =>
            {
                callCount++;
                return callCount switch
                {
                    1 => CreateMetadata(OrchestrationRuntimeStatus.Running, serializedCustomStatus: customStatus1),
                    2 => CreateMetadata(OrchestrationRuntimeStatus.Running, serializedCustomStatus: customStatus2),
                    3 => CreateMetadata(OrchestrationRuntimeStatus.Running, serializedCustomStatus: customStatus3),
                    _ => CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: serializedOutput),
                };
            });

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert — exactly 4 events: 3 incremental halt events + 1 completion
        Assert.Equal(4, events.Count);
        DurableHaltRequestedEvent halt1 = Assert.IsType<DurableHaltRequestedEvent>(events[0]);
        DurableHaltRequestedEvent halt2 = Assert.IsType<DurableHaltRequestedEvent>(events[1]);
        DurableHaltRequestedEvent halt3 = Assert.IsType<DurableHaltRequestedEvent>(events[2]);
        Assert.Equal("executor-1", halt1.ExecutorId);
        Assert.Equal("executor-2", halt2.ExecutorId);
        Assert.Equal("executor-3", halt3.ExecutorId);
        DurableWorkflowCompletedEvent completed = Assert.IsType<DurableWorkflowCompletedEvent>(events[3]);
        Assert.Equal("done", completed.Data);
    }

    [Fact]
    public async Task WatchStreamAsync_NoNewEventsOnRepoll_DoesNotDuplicateAsync()
    {
        // Arrange — simulate polling where custom status doesn't change between polls,
        // validating that events are not duplicated when the list is unchanged.
        DurableHaltRequestedEvent event1 = new("executor-1");
        string serializedEvent1 = SerializeEvent(event1);
        string customStatus = SerializeCustomStatus([serializedEvent1]);
        string serializedOutput = SerializeWorkflowResult("result", [serializedEvent1]);

        int callCount = 0;
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(() =>
            {
                callCount++;
                return callCount switch
                {
                    // First 3 polls return the same custom status (no new events after first)
                    <= 3 => CreateMetadata(OrchestrationRuntimeStatus.Running, serializedCustomStatus: customStatus),
                    _ => CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: serializedOutput),
                };
            });

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert — event1 appears exactly once despite 3 polls with the same status
        Assert.Equal(2, events.Count);
        Assert.IsType<DurableHaltRequestedEvent>(events[0]);
        Assert.IsType<DurableWorkflowCompletedEvent>(events[1]);
    }

    [Fact]
    public async Task WatchStreamAsync_Cancellation_EndsGracefullyAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        int pollCount = 0;
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.GetInstanceAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(() =>
            {
                if (++pollCount >= 2)
                {
                    cts.Cancel();
                }

                return CreateMetadata(OrchestrationRuntimeStatus.Running);
            });

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(cts.Token))
        {
            events.Add(evt);
        }

        // Assert — no exception thrown, stream ends cleanly
        Assert.Empty(events);
    }

    #endregion

    #region WaitForCompletionAsync

    [Fact]
    public async Task WaitForCompletionAsync_Completed_ReturnsResultAsync()
    {
        // Arrange
        string serializedOutput = SerializeWorkflowResult("hello world", []);
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.WaitForInstanceCompletionAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Completed, serializedOutput: serializedOutput));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act
        string? result = await run.WaitForCompletionAsync<string>();

        // Assert
        Assert.Equal("hello world", result);
    }

    [Fact]
    public async Task WaitForCompletionAsync_Failed_ThrowsWithErrorMessageAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.WaitForInstanceCompletionAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(
                OrchestrationRuntimeStatus.Failed,
                failureDetails: new TaskFailureDetails("Error", "kaboom", null, null, null)));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act & Assert
        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => run.WaitForCompletionAsync<string>().AsTask());
        Assert.Equal("kaboom", ex.Message);
    }

    [Fact]
    public async Task WaitForCompletionAsync_UnexpectedStatus_ThrowsAsync()
    {
        // Arrange
        Mock<DurableTaskClient> mockClient = new("test");
        mockClient.Setup(c => c.WaitForInstanceCompletionAsync(InstanceId, true, It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMetadata(OrchestrationRuntimeStatus.Terminated));

        DurableStreamingWorkflowRun run = new(mockClient.Object, InstanceId, CreateTestWorkflow());

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => run.WaitForCompletionAsync<string>().AsTask());
    }

    #endregion

    #region ExtractResult

    [Fact]
    public void ExtractResult_NullOutput_ReturnsDefault()
    {
        // Act
        string? result = DurableStreamingWorkflowRun.ExtractResult<string>(null);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ExtractResult_WrappedStringResult_ReturnsUnwrappedString()
    {
        // Arrange
        string serializedOutput = SerializeWorkflowResult("hello", []);

        // Act
        string? result = DurableStreamingWorkflowRun.ExtractResult<string>(serializedOutput);

        // Assert
        Assert.Equal("hello", result);
    }

    [Fact]
    public void ExtractResult_UnwrappedStringOutput_FallsBackToDirectDeserialization()
    {
        // Arrange — raw DurableDataConverter-style output (JSON-encoded string)
        string serializedOutput = JsonSerializer.Serialize("raw value");

        // Act
        string? result = DurableStreamingWorkflowRun.ExtractResult<string>(serializedOutput);

        // Assert
        Assert.Equal("raw value", result);
    }

    [Fact]
    public void ExtractResult_WrappedObjectResult_DeserializesCorrectly()
    {
        // Arrange
        TestPayload original = new() { Name = "test", Value = 42 };
        string resultJson = JsonSerializer.Serialize(original);
        string serializedOutput = SerializeWorkflowResult(resultJson, []);

        // Act
        TestPayload? result = DurableStreamingWorkflowRun.ExtractResult<TestPayload>(serializedOutput);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("test", result.Name);
        Assert.Equal(42, result.Value);
    }

    #endregion

    private sealed class TestPayload
    {
        public string? Name { get; set; }

        public int Value { get; set; }
    }
}
