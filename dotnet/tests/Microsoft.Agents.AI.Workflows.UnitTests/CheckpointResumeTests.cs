// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Sample;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Regression tests for GH-2485: pending <see cref="RequestInfoEvent"/> objects must be
/// re-emitted after resuming a workflow from a checkpoint.
/// </summary>
public class CheckpointResumeTests
{
    /// <summary>
    /// Verifies that a resumed workflow re-emits <see cref="RequestInfoEvent"/>s for
    /// pending external requests that existed at the time of the checkpoint.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_WithPendingRequests_RepublishesRequestInfoEventsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        RequestPort<string, string> requestPort = RequestPort.Create<string, string>("TestPort");
        ForwardMessageExecutor<string> processor = new("Processor");

        Workflow workflow = new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, processor)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // Act 1: Run workflow, collect pending requests and a checkpoint.
        List<ExternalRequest> originalRequests = [];
        CheckpointInfo? checkpoint = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "Hello"))
        {
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    originalRequests.Add(requestInfo.Request);
                }

                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }

            originalRequests.Should().NotBeEmpty("the workflow should have created at least one external request");
            checkpoint.Should().NotBeNull("a checkpoint should have been created");
        }

        // Act 2: Resume from the checkpoint.
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingAsync(workflow, checkpoint!);

        // Assert: The pending requests should be re-emitted.
        List<ExternalRequest> reEmittedRequests = [];
        using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));

        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
        {
            if (evt is RequestInfoEvent requestInfo)
            {
                reEmittedRequests.Add(requestInfo.Request);
            }
        }

        reEmittedRequests.Should().HaveCount(originalRequests.Count,
            "all pending requests from the checkpoint should be re-emitted after resume");
        reEmittedRequests.Select(r => r.RequestId)
                         .Should().BeEquivalentTo(originalRequests.Select(r => r.RequestId),
            "the re-emitted request IDs should match the original pending request IDs");
    }

    /// <summary>
    /// Verifies that <see cref="RunStatus"/> transitions to <see cref="RunStatus.PendingRequests"/>
    /// after resuming from a checkpoint with pending external requests (not stuck at NotStarted).
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_WithPendingRequests_RunStatusIsPendingRequestsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        RequestPort<string, string> requestPort = RequestPort.Create<string, string>("TestPort");
        ForwardMessageExecutor<string> processor = new("Processor");

        Workflow workflow = new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, processor)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // First run: collect a checkpoint with pending requests.
        CheckpointInfo? checkpoint = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "Hello"))
        {
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }

            checkpoint.Should().NotBeNull();
        }

        // Act: Resume from the checkpoint and consume events so the run loop processes.
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingAsync(workflow, checkpoint!);

        using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));
        await foreach (WorkflowEvent _ in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
        {
            // Consume all events until the stream completes.
        }

        // Assert
        RunStatus status = await resumed.GetStatusAsync();
        status.Should().Be(RunStatus.PendingRequests,
            "the resumed workflow should report PendingRequests after rehydration");
    }

    /// <summary>
    /// Verifies the full roundtrip: resume from checkpoint, observe the re-emitted request,
    /// send a response, and verify the workflow completes without duplicating the request.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_RespondToPendingRequest_CompletesWithoutDuplicateAsync(ExecutionEnvironment environment)
    {
        // Arrange
        RequestPort<string, string> requestPort = RequestPort.Create<string, string>("TestPort");
        ForwardMessageExecutor<string> processor = new("Processor");

        Workflow workflow = new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, processor)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // First run: collect checkpoint + pending request.
        ExternalRequest? pendingRequest = null;
        CheckpointInfo? checkpoint = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "Hello"))
        {
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    pendingRequest = requestInfo.Request;
                }

                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }

            pendingRequest.Should().NotBeNull();
            checkpoint.Should().NotBeNull();
        }

        // Act: Resume and respond to the restored request.
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingAsync(workflow, checkpoint!);

        int requestEventCount = 0;

        using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));

        // Use blockOnPendingRequest: false for the first pass to see the re-emitted requests.
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
        {
            if (evt is RequestInfoEvent requestInfo)
            {
                requestEventCount++;
                requestInfo.Request.RequestId.Should().Be(pendingRequest!.RequestId,
                    "the re-emitted request should match the original");
            }
        }

        requestEventCount.Should().Be(1,
            "the pending request should be emitted exactly once (no duplicates)");

        // Assert intermediate state before responding: the run should be in PendingRequests
        // and we should have observed the re-emitted request. If the first WatchStreamAsync
        // didn't complete or yielded nothing, these assertions catch it with a clear message.
        RunStatus statusBeforeResponse = await resumed.GetStatusAsync();
        statusBeforeResponse.Should().Be(RunStatus.PendingRequests,
            "the run should be in PendingRequests state before we send a response");

        // Now send the response and verify the workflow processes it.
        ExternalResponse response = pendingRequest!.CreateResponse("World");
        await resumed.SendResponseAsync(response);

        // Consume the resulting events to verify the workflow progresses without errors.
        List<WorkflowEvent> postResponseEvents = [];

        using CancellationTokenSource cts2 = new(TimeSpan.FromSeconds(10));
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts2.Token))
        {
            postResponseEvents.Add(evt);
        }

        postResponseEvents.Should().NotBeEmpty(
            "the workflow should process the response and produce events");
        postResponseEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            "no errors should occur when processing the restored request's response");
    }

    /// <summary>
    /// Verifies that restoring a live run to a checkpoint re-emits pending requests and allows
    /// the workflow to continue from that restored point.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Restore_WithPendingRequests_RepublishesRequestInfoEventsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        Workflow workflow = CreateSimpleRequestWorkflow();
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        await using StreamingRun run = await env.WithCheckpointing(checkpointManager)
                                                .RunStreamingAsync(workflow, "Hello");

        (ExternalRequest pendingRequest, CheckpointInfo checkpoint) = await CapturePendingRequestAndCheckpointAsync(run);

        // Advance the run past the checkpoint so the restore has meaningful work to undo.
        await run.SendResponseAsync(pendingRequest.CreateResponse("World"));

        List<WorkflowEvent> firstCompletionEvents = await ReadToHaltAsync(run);
        firstCompletionEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            "the workflow should continue cleanly before we restore");
        RunStatus statusAfterFirstResponse = await run.GetStatusAsync();
        statusAfterFirstResponse.Should().Be(RunStatus.Idle,
            "the workflow should finish processing the first response before we restore");

        // Act
        await run.RestoreCheckpointAsync(checkpoint);

        // Assert
        List<WorkflowEvent> restoredEvents = await ReadToHaltAsync(run);
        ExternalRequest[] replayedRequests = [.. restoredEvents.OfType<RequestInfoEvent>().Select(evt => evt.Request)];

        replayedRequests.Should().ContainSingle("runtime restore should re-emit the restored pending request");
        replayedRequests[0].RequestId.Should().Be(pendingRequest.RequestId,
            "the replayed request should match the request captured at the checkpoint");

        await run.SendResponseAsync(replayedRequests[0].CreateResponse("Again"));

        List<WorkflowEvent> secondCompletionEvents = await ReadToHaltAsync(run);
        secondCompletionEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            "runtime restore replay should not introduce workflow errors");
        RunStatus statusAfterRestoreResponse = await run.GetStatusAsync();
        statusAfterRestoreResponse.Should().Be(RunStatus.Idle,
            "the workflow should be able to continue after the runtime restore replay");
    }

    /// <summary>
    /// Verifies that a resumed parent workflow re-emits pending requests that originated in a subworkflow.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_SubworkflowWithPendingRequests_RepublishesQualifiedRequestInfoEventsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        Workflow workflow = CreateCheckpointedSubworkflowRequestWorkflow();
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        ExternalRequest pendingRequest;
        CheckpointInfo checkpoint;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "Hello"))
        {
            (pendingRequest, checkpoint) = await CapturePendingRequestAndCheckpointAsync(firstRun);
        }

        // Act
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingAsync(workflow, checkpoint);

        // Assert
        List<WorkflowEvent> resumedEvents = await ReadToHaltAsync(resumed);
        ExternalRequest[] replayedRequests = [.. resumedEvents.OfType<RequestInfoEvent>().Select(evt => evt.Request)];

        replayedRequests.Should().ContainSingle("the resumed parent workflow should surface the subworkflow request once");
        replayedRequests[0].RequestId.Should().Be(pendingRequest.RequestId,
            "the replayed subworkflow request should match the checkpointed request");
        replayedRequests[0].PortInfo.PortId.Should().Be(pendingRequest.PortInfo.PortId,
            "the replayed request should remain qualified through the subworkflow boundary");

        await resumed.SendResponseAsync(replayedRequests[0].CreateResponse("World"));

        List<WorkflowEvent> completionEvents = await ReadToHaltAsync(resumed);
        completionEvents.OfType<RequestInfoEvent>().Should().BeEmpty(
            "the resumed subworkflow request should not be replayed twice");
        completionEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            "subworkflow replay should not introduce workflow errors");
        RunStatus statusAfterSubworkflowResponse = await resumed.GetStatusAsync();
        statusAfterSubworkflowResponse.Should().Be(RunStatus.Idle,
            "the resumed subworkflow should continue after responding to the replayed request");
    }

    /// <summary>
    /// Verifies that when <c>republishPendingEvents</c> is <see langword="false"/>,
    /// no <see cref="RequestInfoEvent"/> is re-emitted after resuming from a checkpoint.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_WithRepublishDisabled_DoesNotEmitRequestInfoEventsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        RequestPort<string, string> requestPort = RequestPort.Create<string, string>("TestPort");
        ForwardMessageExecutor<string> processor = new("Processor");

        Workflow workflow = new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, processor)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        // First run: collect a checkpoint with pending requests.
        CheckpointInfo? checkpoint = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "Hello"))
        {
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }

            checkpoint.Should().NotBeNull();
        }

        // Act: Resume with republishPendingEvents: false via the internal API.
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingInternalAsync(workflow, checkpoint!, republishPendingEvents: false);

        // Assert: No RequestInfoEvent should appear in the event stream.
        int requestEventCount = 0;
        using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
        {
            if (evt is RequestInfoEvent)
            {
                requestEventCount++;
            }
        }

        requestEventCount.Should().Be(0,
            "no RequestInfoEvent should be emitted when republishPendingEvents is false");
    }

    private static Workflow CreateSimpleRequestWorkflow(
        string requestPortId = "TestPort",
        string processorId = "Processor")
    {
        RequestPort<string, string> requestPort = RequestPort.Create<string, string>(requestPortId);
        ForwardMessageExecutor<string> processor = new(processorId);

        return new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, processor)
            .Build();
    }

    private static Workflow CreateCheckpointedSubworkflowRequestWorkflow()
    {
        ExecutorBinding subworkflow = CreateSimpleRequestWorkflow(
                requestPortId: "InnerTestPort",
                processorId: "InnerProcessor")
            .BindAsExecutor("Subworkflow");

        return new WorkflowBuilder(subworkflow)
            .AddExternalRequest<string, string>(subworkflow, id: "ForwardedSubworkflowRequest")
            .Build();
    }

    private static async ValueTask<(ExternalRequest PendingRequest, CheckpointInfo Checkpoint)> CapturePendingRequestAndCheckpointAsync(StreamingRun run)
    {
        ExternalRequest? pendingRequest = null;
        CheckpointInfo? checkpoint = null;

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false))
        {
            if (evt is RequestInfoEvent requestInfo)
            {
                pendingRequest ??= requestInfo.Request;
            }

            if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
            {
                checkpoint = cp;
            }
        }

        pendingRequest.Should().NotBeNull("the workflow should have emitted a pending request");
        checkpoint.Should().NotBeNull("the workflow should have produced a checkpoint");
        return (pendingRequest!, checkpoint!);
    }

    private static async ValueTask<List<WorkflowEvent>> ReadToHaltAsync(StreamingRun run)
    {
        List<WorkflowEvent> events = [];
        using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
        {
            events.Add(evt);
        }

        return events;
    }
}
