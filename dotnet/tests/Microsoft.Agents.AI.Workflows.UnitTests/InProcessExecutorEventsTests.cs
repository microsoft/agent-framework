// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class InProcessExecutorEventsTests
{
    [SendsMessage(typeof(string[]))]
    private sealed class EventTrackingExecutor(bool forwardMessages, string id) : Executor<IEnumerable<string>>(id)
    {
        public List<IEnumerable<string>> ReceivedMessages { get; } = [];

        private int _checkpointingCalls;
        public int CheckpointingCalls => this._checkpointingCalls;

        private int _checkpointRestoredCalls;
        public int CheckpointRestoredCalls => this._checkpointRestoredCalls;

        private int _deliveryStartingCalls;
        public int DeliveryStartingCalls => this._deliveryStartingCalls;

        private int _deliveryFinishedAsyncCalls;
        public int DeliveryFinishedCalls => this._deliveryFinishedAsyncCalls;

        protected internal override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._checkpointingCalls);
            return base.OnCheckpointingAsync(context, cancellationToken);
        }

        protected internal override ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._checkpointRestoredCalls);
            return base.OnCheckpointRestoredAsync(context, cancellationToken);
        }

        protected internal override ValueTask OnMessageDeliveryStartingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._deliveryStartingCalls);
            return base.OnMessageDeliveryStartingAsync(context, cancellationToken);
        }

        protected internal override ValueTask OnMessageDeliveryFinishedAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._deliveryFinishedAsyncCalls);
            return base.OnMessageDeliveryFinishedAsync(context, cancellationToken);
        }

        public override async ValueTask HandleAsync(IEnumerable<string> message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            this.ReceivedMessages.Add(message);

            if (forwardMessages)
            {
                foreach (string packedMessage in message)
                {
                    await context.SendMessageAsync(new[] { packedMessage }, cancellationToken);
                }
            }
        }
    }

    private sealed class TestFixture
    {
        public EventTrackingExecutor StartingExecutor { get; } = new(true, nameof(StartingExecutor));
        public EventTrackingExecutor ReceivesMessage { get; } = new(false, nameof(ReceivesMessage));
        public EventTrackingExecutor UninvokedExecutor { get; } = new(false, nameof(UninvokedExecutor));

        public Workflow Workflow { get; }

        public TestFixture()
        {
            this.Workflow = new WorkflowBuilder(this.StartingExecutor)
                                .AddEdge(this.StartingExecutor, this.ReceivesMessage)
                                // The uninvoked executor remains uninvoked because ReceivesMessage does not forward its incoming message
                                .AddEdge(this.ReceivesMessage, this.UninvokedExecutor)
                                .Build();
        }

        public const int StepsPerInputBatch = 2;
    }

    [Theory]
    [InlineData(1, ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(1, ExecutionEnvironment.InProcess_OffThread)]
    internal async Task Test_InProcessExecution_InvokesDeliveryEventsOnceAsync(int messageCount, ExecutionEnvironment environment)
    {
        // Arrange
        TestFixture fixture = new();
        InProcessExecutionEnvironment executionEnvironment = environment.ToWorkflowExecutionEnvironment();

        // Act
        IEnumerable<string> batch = Enumerable.Range(1, messageCount).Select(i => $"Message_{i}");
        await using StreamingRun streamingRun = await executionEnvironment.OpenStreamingAsync(fixture.Workflow);

        await streamingRun.TrySendMessageAsync(batch);
        await streamingRun.RunToCompletionAsync(ThrowOnError);

        // Assert
        Assert.Equal(1, fixture.StartingExecutor.DeliveryStartingCalls);
        Assert.Equal(1, fixture.StartingExecutor.DeliveryFinishedCalls);

        Assert.Equal(1, fixture.ReceivesMessage.DeliveryStartingCalls);
        Assert.Equal(1, fixture.ReceivesMessage.DeliveryFinishedCalls);

        Assert.Equal(0, fixture.UninvokedExecutor.DeliveryStartingCalls);
        Assert.Equal(0, fixture.UninvokedExecutor.DeliveryFinishedCalls);

        ExternalResponse? ThrowOnError(WorkflowEvent workflowEvent)
        {
            switch (workflowEvent)
            {
                case WorkflowErrorEvent workflowError:
                    Assert.Fail(workflowError.Exception?.ToString() ?? "Unknown error occurred while executing workflow.");
                    break;

                case ExecutorFailedEvent executorFailed:
                    Assert.Fail(executorFailed.Data != null
                                ? $"Executor {executorFailed.ExecutorId} failed with exception: {executorFailed.Data}"
                                : $"Executor {executorFailed.ExecutorId} failed with unknown error");
                    break;
            }

            return null;
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_InProcessExecution_InvokesCheckpointingEventIFFCheckpointingEnabledAsync(bool useCheckpointing)
    {
        // Arrange
        TestFixture fixture = new();

        InProcessExecutionEnvironment executionEnvironment = InProcessExecution.Default;

        if (useCheckpointing)
        {
            executionEnvironment = executionEnvironment.WithCheckpointing(CheckpointManager.CreateInMemory());
        }

        // Act
        string sessionId = Guid.NewGuid().ToString();
        await using Run run = await executionEnvironment.RunAsync<string[]>(fixture.Workflow, ["Message"], sessionId);

        // Assert
        Assert.Empty(run.OutgoingEvents.OfType<WorkflowErrorEvent>() ?? []);
        Assert.Empty(run.OutgoingEvents.OfType<ExecutorFailedEvent>() ?? []);

        const int ExpectedSteps = TestFixture.StepsPerInputBatch;
        Assert.Equal(ExpectedSteps, run.OutgoingEvents.OfType<SuperStepCompletedEvent>()?.Count());

        int expectedCheckpoints = useCheckpointing ? ExpectedSteps : 0;
        Assert.Equal(expectedCheckpoints, run.Checkpoints.Count);

        Assert.Equal(expectedCheckpoints, fixture.StartingExecutor.CheckpointingCalls);
        Assert.Equal(0, fixture.StartingExecutor.CheckpointRestoredCalls);

        Assert.Equal(expectedCheckpoints, fixture.ReceivesMessage.CheckpointingCalls);
        Assert.Equal(0, fixture.ReceivesMessage.CheckpointRestoredCalls);

        Assert.Equal(0, fixture.UninvokedExecutor.CheckpointingCalls); // Uninvoked executors don't get "instantiated" in the workflow context
        Assert.Equal(0, fixture.UninvokedExecutor.CheckpointRestoredCalls);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    //[InlineData(false, true)] - impossible to restore checkpoint with checkpointing disabled, will throw
    public async Task Test_InProcessExecution_InvokesRestoredEventIFFRestoringCheckpointAsync(bool restoreCheckpoint)
    {
        // Arrange
        TestFixture runFixture = new();
        InProcessExecutionEnvironment executionEnvironment = InProcessExecution.Default.WithCheckpointing(CheckpointManager.CreateInMemory());

        // Act
        string sessionId = Guid.NewGuid().ToString();
        Run run = await executionEnvironment.RunAsync<string[]>(runFixture.Workflow, ["Message"], sessionId);

        // Assert
        Assert.Empty(run.OutgoingEvents.OfType<WorkflowErrorEvent>() ?? []);
        Assert.Empty(run.OutgoingEvents.OfType<ExecutorFailedEvent>() ?? []);

        TestFixture validateFixture = runFixture;

        // Act 2
        int expectedCheckpoints = TestFixture.StepsPerInputBatch;

        if (restoreCheckpoint)
        {
            expectedCheckpoints--; // We are restoring from the first one, so skip one

            validateFixture = new();
            Assert.Equal(TestFixture.StepsPerInputBatch, run.Checkpoints.Count);

            CheckpointInfo firstCheckpoint = run.Checkpoints[0];

            await run.DisposeAsync();
            run = await executionEnvironment.ResumeAsync(validateFixture.Workflow, firstCheckpoint);
        }

        // Assert 2
        if (restoreCheckpoint)
        {
            // Make sure the second run did not have failures
            Assert.Empty(run.OutgoingEvents.OfType<WorkflowErrorEvent>() ?? []);
            Assert.Empty(run.OutgoingEvents.OfType<ExecutorFailedEvent>() ?? []);
        }

        int expectedRestoreCalls = restoreCheckpoint ? 1 : 0;

        Assert.Equal(expectedCheckpoints, validateFixture.StartingExecutor.CheckpointingCalls);
        Assert.Equal(expectedRestoreCalls, validateFixture.StartingExecutor.CheckpointRestoredCalls);

        Assert.Equal(expectedCheckpoints, validateFixture.ReceivesMessage.CheckpointingCalls);
        Assert.Equal(expectedRestoreCalls, validateFixture.ReceivesMessage.CheckpointRestoredCalls);

        Assert.Equal(0, validateFixture.UninvokedExecutor.CheckpointingCalls); // Uninvoked executors don't get "instantiated" in the workflow context
        Assert.Equal(0, validateFixture.UninvokedExecutor.CheckpointRestoredCalls);

        // Cleanup
        await run.DisposeAsync();
    }
}
