// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
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

            Assert.NotEmpty(originalRequests);
            Assert.NotNull(checkpoint);
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

        Assert.Equal(originalRequests.Count, reEmittedRequests.Count);
        Assert.Equivalent(originalRequests.Select(r => r.RequestId), reEmittedRequests.Select(r => r.RequestId));
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

            Assert.NotNull(checkpoint);
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
        Assert.Equal(RunStatus.PendingRequests, status);
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

            Assert.NotNull(pendingRequest);
            Assert.NotNull(checkpoint);
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
                Assert.Equal(pendingRequest!.RequestId, requestInfo.Request.RequestId);
            }
        }

        Assert.Equal(1, requestEventCount);

        // Assert intermediate state before responding: the run should be in PendingRequests
        // and we should have observed the re-emitted request. If the first WatchStreamAsync
        // didn't complete or yielded nothing, these assertions catch it with a clear message.
        RunStatus statusBeforeResponse = await resumed.GetStatusAsync();
        Assert.Equal(RunStatus.PendingRequests, statusBeforeResponse);

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

        Assert.NotEmpty(postResponseEvents);
        Assert.Empty(postResponseEvents.OfType<WorkflowErrorEvent>() ?? []);
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
        Assert.Empty(firstCompletionEvents.OfType<WorkflowErrorEvent>() ?? []);
        RunStatus statusAfterFirstResponse = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, statusAfterFirstResponse);

        // Act
        await run.RestoreCheckpointAsync(checkpoint);

        // Assert
        List<WorkflowEvent> restoredEvents = await ReadToHaltAsync(run);
        ExternalRequest[] replayedRequests = [.. restoredEvents.OfType<RequestInfoEvent>().Select(evt => evt.Request)];

        Assert.Single(replayedRequests);
        Assert.Equal(pendingRequest.RequestId, replayedRequests[0].RequestId);

        await run.SendResponseAsync(replayedRequests[0].CreateResponse("Again"));

        List<WorkflowEvent> secondCompletionEvents = await ReadToHaltAsync(run);
        Assert.Empty(secondCompletionEvents.OfType<WorkflowErrorEvent>() ?? []);
        RunStatus statusAfterRestoreResponse = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, statusAfterRestoreResponse);
    }

    /// <summary>
    /// Verifies that restoring a live run clears any queued external responses from the
    /// superseded timeline before importing checkpoint state.
    /// </summary>
    [Fact]
    internal async Task Checkpoint_Restore_ClearsQueuedExternalResponsesBeforeImportAsync()
    {
        Workflow workflow = CreateSimpleRequestWorkflow();
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = ExecutionEnvironment.InProcess_Lockstep.ToWorkflowExecutionEnvironment();

        await using StreamingRun run = await env.WithCheckpointing(checkpointManager)
                                                .RunStreamingAsync(workflow, "Hello");

        (ExternalRequest pendingRequest, CheckpointInfo checkpoint) = await CapturePendingRequestAndCheckpointAsync(run);

        await run.SendResponseAsync(pendingRequest.CreateResponse("World"));
        await run.RestoreCheckpointAsync(checkpoint);

        List<WorkflowEvent> restoredEvents = await ReadToHaltAsync(run);
        ExternalRequest replayedRequest = Assert.Single(restoredEvents.OfType<RequestInfoEvent>()
                                                        .Select(evt => evt.Request));

        Assert.Empty(restoredEvents.OfType<WorkflowErrorEvent>() ?? []);
        RunStatus statusAfterRestore = await run.GetStatusAsync();
        Assert.Equal(RunStatus.PendingRequests, statusAfterRestore);

        await run.SendResponseAsync(replayedRequest.CreateResponse("Again"));

        List<WorkflowEvent> completionEvents = await ReadToHaltAsync(run);
        Assert.Empty(completionEvents.OfType<WorkflowErrorEvent>() ?? []);
        RunStatus finalStatus = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, finalStatus);
    }

    /// <summary>
    /// Verifies that fan-in edge state buffered before a checkpoint is still present after resume.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_PreservesFanInBarrierBufferedMessagesAsync(ExecutionEnvironment environment)
    {
        // Arrange
        Workflow workflow = CreateFanInBarrierWorkflow();
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        ExternalRequest pendingRequest;
        CheckpointInfo checkpoint;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "start"))
        {
            (pendingRequest, checkpoint) = await CapturePendingRequestAndCheckpointAsync(firstRun);
        }

        // Act + Assert
        ExternalRequest replayedRequest = await ResumeAndAssertBarrierReleasesAsync(
            env, checkpointManager, workflow, checkpoint, ["before", "after"]);

        Assert.Equal(replayedRequest.RequestId, pendingRequest.RequestId);
    }

    /// <summary>
    /// Verifies that fan-in barrier state is preserved across resume when more than two sources
    /// participate, and multiple contributions are buffered before the checkpoint.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_PreservesFanInBarrierBufferedMessages_MultiSourceAsync(ExecutionEnvironment environment)
    {
        // Arrange: a fan-out start broadcasts a trigger to two early barrier sources and to a
        // request-port kickoff. Both early sources contribute pre-checkpoint and only the port
        // response path is unseen at the checkpoint - the barrier must hold both buffered
        // contributions across resume and only release once the third source contributes.
        const string RequestPortId = "Approval";
        const string SinkId = "Sink";

        ForwardMessageExecutor<string> start = new("Start");
        ExecutorBinding earlyA = new BarrierContributor("EarlyA", SinkId, "before-1");
        ExecutorBinding earlyB = new BarrierContributor("EarlyB", SinkId, "before-2");
        ExecutorBinding kickoff = new RequestPortKickoff("Kickoff", RequestPortId);
        ExecutorBinding afterResume = new PostCheckpointBarrierSource("AfterResume", SinkId);
        ExecutorBinding sink = new BarrierSink(SinkId);
        RequestPort<ApprovalRequest, ApprovalReply> requestPort = RequestPort.Create<ApprovalRequest, ApprovalReply>(RequestPortId);

        Workflow workflow = new WorkflowBuilder(start)
            .AddEdge(start, earlyA)
            .AddEdge(start, earlyB)
            .AddEdge(start, kickoff)
            .AddEdge(kickoff, requestPort)
            .AddEdge(requestPort, afterResume)
            .AddFanInBarrierEdge([earlyA, earlyB, afterResume], sink)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        ExternalRequest pendingRequest;
        CheckpointInfo checkpoint;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, "start"))
        {
            (pendingRequest, checkpoint) = await CapturePendingRequestAndCheckpointAsync(firstRun);
        }

        // Act + Assert
        ExternalRequest replayedRequest = await ResumeAndAssertBarrierReleasesAsync(
            env, checkpointManager, workflow, checkpoint, ["before-1", "before-2", "after"]);

        Assert.Equal(replayedRequest.RequestId, pendingRequest.RequestId);
    }

    /// <summary>
    /// Verifies that the same checkpoint can be resumed independently more than once - i.e. that
    /// completing one resumed run does not mutate state inside the stored checkpoint.
    /// </summary>
    /// <remarks>
    /// Without a snapshot at the export/import boundary, <c>FanInEdgeRunner</c> would hand the
    /// in-memory <c>CheckpointManager</c> a live reference to the mutable <c>FanInEdgeState</c>.
    /// The first resume would then reset the buffer back to "all unseen" while completing, and a
    /// second resume from the same <see cref="CheckpointInfo"/> would deadlock waiting for the
    /// pre-checkpoint contribution that no longer exists.
    /// </remarks>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_FanInBarrierCheckpointCanBeResumedTwiceAsync(ExecutionEnvironment environment)
    {
        // Arrange
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        CheckpointInfo checkpoint;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(CreateFanInBarrierWorkflow(), "start"))
        {
            (_, checkpoint) = await CapturePendingRequestAndCheckpointAsync(firstRun);
        }

        // Act + Assert: each resume needs a fresh Workflow object because the previous run takes
        // ownership of it. Resuming the same CheckpointInfo more than once must yield identical
        // results - the first resume must not mutate state the checkpoint store is still holding.
        for (int attempt = 0; attempt < 2; attempt++)
        {
            await ResumeAndAssertBarrierReleasesAsync(
                env, checkpointManager, CreateFanInBarrierWorkflow(), checkpoint, ["before", "after"]);
        }
    }

    /// <summary>
    /// Verifies that fan-in barrier state buffered inside a subworkflow is preserved across a
    /// checkpoint/resume cycle of the parent workflow.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    internal async Task Checkpoint_Resume_PreservesFanInBarrierBufferedMessages_InSubworkflowAsync(ExecutionEnvironment environment)
    {
        // Arrange: the fan-in barrier lives inside a subworkflow; the fix has to apply to the
        // subworkflow's runner context too.
        const string InnerRequestPortId = "InnerApproval";
        const string ForwardedRequestId = "ForwardedInnerApproval";

        Workflow BuildOuter()
        {
            ExecutorBinding subworkflow = CreateFanInBarrierWorkflow(
                    requestPortId: InnerRequestPortId, sinkId: "InnerSink")
                .BindAsExecutor("InnerSubworkflow");

            return new WorkflowBuilder(subworkflow)
                .AddExternalRequest<ApprovalRequest, ApprovalReply>(subworkflow, id: ForwardedRequestId)
                .Build();
        }

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();

        ExternalRequest pendingRequest;
        CheckpointInfo checkpoint;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(BuildOuter(), "start"))
        {
            (pendingRequest, checkpoint) = await CapturePendingRequestAndCheckpointAsync(firstRun);
        }

        // Act + Assert
        ExternalRequest replayedRequest = await ResumeAndAssertBarrierReleasesAsync(
            env, checkpointManager, BuildOuter(), checkpoint, ["before", "after"]);

        Assert.Equal(replayedRequest.RequestId, pendingRequest.RequestId);
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

        Assert.Single(replayedRequests);
        Assert.Equal(pendingRequest.RequestId, replayedRequests[0].RequestId);
        Assert.Equal(pendingRequest.PortInfo.PortId, replayedRequests[0].PortInfo.PortId);

        await resumed.SendResponseAsync(replayedRequests[0].CreateResponse("World"));

        List<WorkflowEvent> completionEvents = await ReadToHaltAsync(resumed);
        Assert.Empty(completionEvents.OfType<RequestInfoEvent>() ?? []);
        Assert.Empty(completionEvents.OfType<WorkflowErrorEvent>() ?? []);
        RunStatus statusAfterSubworkflowResponse = await resumed.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, statusAfterSubworkflowResponse);
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

            Assert.NotNull(checkpoint);
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

        Assert.Equal(0, requestEventCount);
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

        Assert.NotNull(pendingRequest);
        Assert.NotNull(checkpoint);
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

    private static Workflow CreateFanInBarrierWorkflow(
        string requestPortId = "Approval",
        string sinkId = "Sink")
    {
        ExecutorBinding before = new PreCheckpointBarrierSource("BeforePause", requestPortId, sinkId);
        ExecutorBinding after = new PostCheckpointBarrierSource("AfterResume", sinkId);
        ExecutorBinding sink = new BarrierSink(sinkId);
        RequestPort<ApprovalRequest, ApprovalReply> requestPort =
            RequestPort.Create<ApprovalRequest, ApprovalReply>(requestPortId);

        return new WorkflowBuilder(before)
            .AddEdge(before, requestPort)
            .AddEdge(requestPort, after)
            .AddFanInBarrierEdge([before, after], sink)
            .Build();
    }

    private static async ValueTask<ExternalRequest> ResumeAndAssertBarrierReleasesAsync(
        InProcessExecutionEnvironment env,
        CheckpointManager checkpointManager,
        Workflow workflow,
        CheckpointInfo checkpoint,
        IEnumerable<string> expectedBarrierSources)
    {
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingAsync(workflow, checkpoint);

        List<WorkflowEvent> resumedEvents = await ReadToHaltAsync(resumed);
        ExternalRequest replayedRequest = Assert.Single(resumedEvents.OfType<RequestInfoEvent>()
                                                       .Select(evt => evt.Request));

        await resumed.SendResponseAsync(replayedRequest.CreateResponse(new ApprovalReply("yes")));

        List<WorkflowEvent> completionEvents = await ReadToHaltAsync(resumed);

        Assert.Empty(completionEvents.OfType<WorkflowErrorEvent>() ?? []);

        string[] outputs = [.. completionEvents.OfType<BarrierReleasedEvent>().Select(evt => evt.Source)];
        Assert.Equivalent(expectedBarrierSources, outputs);

        RunStatus status = await resumed.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, status);

        return replayedRequest;
    }

    private sealed record BarrierContribution(string Source);

    private sealed record ApprovalRequest(string Prompt);

    private sealed record ApprovalReply(string Value);

    private sealed class BarrierReleasedEvent(string source) : WorkflowEvent
    {
        public string Source { get; } = source;
    }

    private sealed class PreCheckpointBarrierSource(string id, string requestPortId, string sinkId) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .SendsMessage<BarrierContribution>()
                              .SendsMessage<ApprovalRequest>();

        private async ValueTask HandleAsync(string input, IWorkflowContext ctx)
        {
            await ctx.SendMessageAsync(new BarrierContribution("before"), sinkId).ConfigureAwait(false);
            await ctx.SendMessageAsync(new ApprovalRequest("continue?"), requestPortId).ConfigureAwait(false);
        }
    }

    private sealed class BarrierContributor(string id, string sinkId, string label) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .SendsMessage<BarrierContribution>();

        private ValueTask HandleAsync(string input, IWorkflowContext ctx)
            => ctx.SendMessageAsync(new BarrierContribution(label), sinkId);
    }

    private sealed class RequestPortKickoff(string id, string requestPortId) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .SendsMessage<ApprovalRequest>();

        private ValueTask HandleAsync(string input, IWorkflowContext ctx)
            => ctx.SendMessageAsync(new ApprovalRequest("continue?"), requestPortId);
    }

    private sealed class PostCheckpointBarrierSource(string id, string sinkId) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<ApprovalReply>(this.HandleAsync))
                              .SendsMessage<BarrierContribution>();

        private ValueTask HandleAsync(ApprovalReply reply, IWorkflowContext ctx)
            => ctx.SendMessageAsync(new BarrierContribution("after"), sinkId);
    }

    private sealed class BarrierSink(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<BarrierContribution>(this.HandleAsync));

        private ValueTask HandleAsync(BarrierContribution contribution, IWorkflowContext ctx)
            => ctx.AddEventAsync(new BarrierReleasedEvent(contribution.Source));
    }
}
