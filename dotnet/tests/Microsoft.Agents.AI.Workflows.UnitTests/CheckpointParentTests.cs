// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for verifying that CheckpointInfo.Parent is properly populated
/// when checkpoints are created during workflow execution (GH #3796).
/// </summary>
public class CheckpointParentTests
{
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task Checkpoint_FirstCheckpoint_ShouldHaveNullParentAsync(ExecutionEnvironment environment)
    {
        // Arrange: A simple two-step workflow that will produce at least one checkpoint.
        ForwardMessageExecutor<string> executorA = new("A");
        ForwardMessageExecutor<string> executorB = new("B");

        Workflow workflow = new WorkflowBuilder(executorA)
            .AddEdge(executorA, executorB)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // Act
        StreamingRun run =
            await env.WithCheckpointing(checkpointManager).StreamAsync(workflow, "Hello");

        List<CheckpointInfo> checkpoints = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is SuperStepCompletedEvent stepEvt && stepEvt.CompletionInfo?.Checkpoint is { } cp)
            {
                checkpoints.Add(cp);
            }
        }

        // Assert: The first checkpoint should have been created and stored with a null parent.
        checkpoints.Should().NotBeEmpty("at least one checkpoint should have been created");

        CheckpointInfo firstCheckpoint = checkpoints[0];
        Checkpoint storedFirst = await ((ICheckpointManager)checkpointManager)
            .LookupCheckpointAsync(firstCheckpoint.RunId, firstCheckpoint);
        storedFirst.Parent.Should().BeNull("the first checkpoint should have no parent");
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task Checkpoint_SubsequentCheckpoints_ShouldChainParentsAsync(ExecutionEnvironment environment)
    {
        // Arrange: A workflow with a loop that will produce multiple checkpoints.
        ForwardMessageExecutor<string> executorA = new("A");
        ForwardMessageExecutor<string> executorB = new("B");

        // A -> B -> A (loop) to generate multiple supersteps/checkpoints.
        Workflow workflow = new WorkflowBuilder(executorA)
            .AddEdge(executorA, executorB)
            .AddEdge(executorB, executorA)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // Act
        await using StreamingRun run = await env.WithCheckpointing(checkpointManager).StreamAsync(workflow, "Hello");

        List<CheckpointInfo> checkpoints = [];
        using CancellationTokenSource cts = new();

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(cts.Token))
        {
            if (evt is SuperStepCompletedEvent stepEvt && stepEvt.CompletionInfo?.Checkpoint is { } cp)
            {
                checkpoints.Add(cp);
                if (checkpoints.Count >= 3)
                {
                    cts.Cancel();
                }
            }
        }

        // Assert: We should have at least 3 checkpoints
        checkpoints.Should().HaveCountGreaterThanOrEqualTo(3);

        // Verify the parent chain
        Checkpoint stored0 = await ((ICheckpointManager)checkpointManager)
            .LookupCheckpointAsync(checkpoints[0].RunId, checkpoints[0]);
        stored0.Parent.Should().BeNull("the first checkpoint should have no parent");

        Checkpoint stored1 = await ((ICheckpointManager)checkpointManager)
            .LookupCheckpointAsync(checkpoints[1].RunId, checkpoints[1]);
        stored1.Parent.Should().NotBeNull("the second checkpoint should have a parent");
        stored1.Parent.Should().Be(checkpoints[0], "the second checkpoint's parent should be the first checkpoint");

        Checkpoint stored2 = await ((ICheckpointManager)checkpointManager)
            .LookupCheckpointAsync(checkpoints[2].RunId, checkpoints[2]);
        stored2.Parent.Should().NotBeNull("the third checkpoint should have a parent");
        stored2.Parent.Should().Be(checkpoints[1], "the third checkpoint's parent should be the second checkpoint");
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task Checkpoint_AfterResume_ShouldHaveResumedCheckpointAsParentAsync(ExecutionEnvironment environment)
    {
        // Arrange: A looping workflow that produces checkpoints.
        ForwardMessageExecutor<string> executorA = new("A");
        ForwardMessageExecutor<string> executorB = new("B");

        Workflow workflow = new WorkflowBuilder(executorA)
            .AddEdge(executorA, executorB)
            .AddEdge(executorB, executorA)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // First run: collect a checkpoint to resume from
        await using StreamingRun run = await env.WithCheckpointing(checkpointManager).StreamAsync(workflow, "Hello");

        List<CheckpointInfo> firstRunCheckpoints = [];
        using CancellationTokenSource cts = new();
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(cts.Token))
        {
            if (evt is SuperStepCompletedEvent stepEvt && stepEvt.CompletionInfo?.Checkpoint is { } cp)
            {
                firstRunCheckpoints.Add(cp);
                if (firstRunCheckpoints.Count >= 2)
                {
                    cts.Cancel();
                }
            }
        }

        firstRunCheckpoints.Should().HaveCountGreaterThanOrEqualTo(2);
        CheckpointInfo resumePoint = firstRunCheckpoints[0];

        // Dispose the first run to release workflow ownership before resuming.
        await run.DisposeAsync();

        // Act: Resume from the first checkpoint
        StreamingRun resumed = await env.WithCheckpointing(checkpointManager).ResumeStreamAsync(workflow, resumePoint);

        List<CheckpointInfo> resumedCheckpoints = [];
        using CancellationTokenSource cts2 = new();
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(cts2.Token))
        {
            if (evt is SuperStepCompletedEvent stepEvt && stepEvt.CompletionInfo?.Checkpoint is { } cp)
            {
                resumedCheckpoints.Add(cp);
                if (resumedCheckpoints.Count >= 1)
                {
                    cts2.Cancel();
                }
            }
        }

        // Assert: The first checkpoint after resume should have the resume point as its parent.
        resumedCheckpoints.Should().NotBeEmpty();
        Checkpoint storedResumed = await ((ICheckpointManager)checkpointManager)
            .LookupCheckpointAsync(resumedCheckpoints[0].RunId, resumedCheckpoints[0]);
        storedResumed.Parent.Should().NotBeNull("checkpoint created after resume should have a parent");
        storedResumed.Parent.Should().Be(resumePoint, "checkpoint after resume should reference the checkpoint we resumed from");
    }
}
