// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for the <see cref="HostedWorkflowState"/> class.
/// </summary>
public class HostedWorkflowStateTests
{
    [Fact]
    public void Constructor_NullWorkflow_Throws() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>("workflow", () => new HostedWorkflowState((Workflow)null!));

    [Fact]
    public void TryGetCheckpoint_UnknownSession_ReturnsFalse()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateTestWorkflow());

        // Act
        bool found = state.TryGetCheckpoint("unknown", out var checkpoint);

        // Assert
        Assert.False(found);
        Assert.Null(checkpoint);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public async Task RunOrResumeAsync_InvalidSessionId_ThrowsAsync(string? sessionId)
    {
        // Arrange
        var state = new HostedWorkflowState(CreateTestWorkflow());

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() => state.RunOrResumeAsync(sessionId!, "input").AsTask());
    }

    [Fact]
    public async Task RunOrResumeAsync_NullInput_ThrowsAsync()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateTestWorkflow());

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>("input", () => state.RunOrResumeAsync<string>("s1", null!).AsTask());
    }

    [Fact]
    public async Task RunOrResumeAsync_FirstTurn_RunsAndRecordsCheckpointAsync()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateEchoWorkflow());

        // Act
        HostedWorkflowRunResult result = await state.RunOrResumeAsync("s1", InputMessages("hello"));

        // Assert
        Assert.NotEmpty(result.Events);
        Assert.NotNull(result.Checkpoint);
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? checkpoint));
        Assert.Same(result.Checkpoint, checkpoint);
        Assert.Contains("hello", OutputText(result));
    }

    [Fact]
    public async Task RunOrResumeAsync_SecondTurn_ResumesWithNewInputAndCompletesAsync()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateEchoWorkflow());
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", InputMessages("hello"));
        CheckpointInfo? firstCheckpoint = first.Checkpoint;

        // Act: the second turn must restore the checkpoint and run forward with the NEW input.
        // A regression here (resuming with no input) would hang, so guard with a timeout.
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", InputMessages("world"))
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: the resumed turn processed the new input and advanced the checkpoint.
        Assert.NotEmpty(second.Events);
        Assert.Contains("world", OutputText(second));
        Assert.NotNull(second.Checkpoint);
        Assert.NotSame(firstCheckpoint, second.Checkpoint);
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? head));
        Assert.Same(second.Checkpoint, head);
    }

    [Fact]
    public async Task RunOrResumeAsync_ResumeWithPendingRequest_DoesNotBlockAsync()
    {
        // Arrange: a human-in-the-loop workflow whose start executor forwards its input to a request port,
        // so the workflow emits a RequestInfoEvent and halts awaiting an external response.
        var state = new HostedWorkflowState(ApprovalGateWorkflow.Build());

        // First turn halts at the pending request (the non-blocking baseline).
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "approve deploy")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));
        Assert.Contains(first.Events, e => e is RequestInfoEvent);
        Assert.NotNull(first.Checkpoint);

        // Act: resuming a workflow that halts at a pending request must also return instead of blocking
        // forever. A regression (blocking drain) hangs here, so guard with a timeout.
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", "approve deploy again")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: the resumed turn surfaced the pending request and returned.
        Assert.Contains(second.Events, e => e is RequestInfoEvent);
    }

    [Fact]
    public async Task RunOrResumeAsync_ResumeMakesNoProgress_LogsWarningAsync()
    {
        // Arrange: a non-chat-protocol workflow that completes on the first turn.
        var loggerFactory = new CapturingLoggerFactory();
        var state = new HostedWorkflowState(StringEchoWorkflow.Build(), loggerFactory: loggerFactory);
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "hello");
        Assert.NotEmpty(first.Events);
        Assert.NotNull(first.Checkpoint);

        // Act: resume with an input the start executor cannot handle, so the turn drives no work.
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", 42);

        // Assert: a resume that produced no events is surfaced as a warning (possible stale checkpoint /
        // mismatched input).
        Assert.Empty(second.Events);
        Assert.Contains(loggerFactory.Entries, e => e.Level == LogLevel.Warning);
    }

    [Fact]
    public async Task RunOrResumeAsync_CursorMiss_ResumesFromManagerLatestCheckpointAsync()
    {
        // Arrange: a shared checkpoint manager stands in for durable storage that outlives the in-memory
        // cursor. The first holder runs one turn; a counting workflow records count:1 in the checkpoint.
        var manager = CheckpointManager.CreateInMemory();
        var first = new HostedWorkflowState(CountingWorkflow.Build(), manager);
        HostedWorkflowRunResult firstResult = await first.RunOrResumeAsync("s1", "go");
        Assert.Contains("count:1", StringOutput(firstResult));

        // Act: a NEW holder over the SAME manager (fresh cursor, e.g. after a process restart) runs the
        // session again. With durable read-through it resumes from the manager's latest checkpoint.
        var second = new HostedWorkflowState(CountingWorkflow.Build(), manager);
        HostedWorkflowRunResult resumed = await second.RunOrResumeAsync("s1", "go")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: the count advanced to 2, proving it resumed from the prior checkpoint rather than
        // restarting from scratch (which would yield count:1 again).
        Assert.Contains("count:2", StringOutput(resumed));
        Assert.True(second.TryGetCheckpoint("s1", out _));
    }

    [Fact]
    public void Constructor_NullFactory_Throws() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>("workflowFactory", () => new HostedWorkflowState((Func<CancellationToken, ValueTask<Workflow>>)null!));

    [Fact]
    public async Task RunOrResumeAsync_Factory_ConcurrentDifferentSessions_RunInParallelAsync()
    {
        // Arrange: factory mode builds a fresh workflow instance per run, so independent sessions are NOT
        // serialized. The gated workflow signals on entry and blocks on a shared gate; both instances share the
        // same gate so the test can hold both turns "inside" the workflow at once.
        using var entered = new SemaphoreSlim(0, 2);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var state = new HostedWorkflowState(
            _ => new ValueTask<Workflow>(GatedCountingWorkflow.Build(entered, release.Task)),
            CheckpointManager.CreateInMemory());

        // Act: start two turns for DIFFERENT sessions.
        Task<HostedWorkflowRunResult> first = state.RunOrResumeAsync("s1", "go").AsTask();
        Task<HostedWorkflowRunResult> second = state.RunOrResumeAsync("s2", "go").AsTask();

        // Assert: BOTH turns enter the workflow before either is released — proving they run in parallel. In
        // shared-instance mode the second would wait on the holder lock and this second wait would time out.
        Assert.True(await entered.WaitAsync(TimeSpan.FromSeconds(10)), "the first turn should enter the workflow");
        Assert.True(await entered.WaitAsync(TimeSpan.FromSeconds(10)), "the second turn should enter concurrently in factory mode");

        // Release both and let them complete.
        release.SetResult();
        HostedWorkflowRunResult[] results = await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(30));

        // Each independent session produced its own first-turn count.
        Assert.All(results, r => Assert.Contains("count:1", StringOutput(r)));
    }

    [Fact]
    public async Task RunOrResumeAsync_Factory_FirstTurnThenResume_AdvancesCheckpointAsync()
    {
        // Arrange: factory mode with a fresh instance per run. A resume must rehydrate a fresh instance from the
        // session's checkpoint in the shared manager.
        var state = new HostedWorkflowState(_ => new ValueTask<Workflow>(CountingWorkflow.Build()));

        // Act: two turns for the same session.
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "go");
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", "go");

        // Assert: the second turn resumed the first's state (count advanced 1 -> 2), proving a fresh instance
        // resumed from the checkpoint rather than starting over.
        Assert.Contains("count:1", StringOutput(first));
        Assert.Contains("count:2", StringOutput(second));
    }

    [Fact]
    public async Task RunOrResumeAsync_CachedFactory_BuildsOnceAndReusesAsync()
    {
        // Arrange: a cached factory (cacheWorkflow: true) must build the workflow once and reuse it.
        int builds = 0;
        var state = new HostedWorkflowState(
            _ =>
            {
                Interlocked.Increment(ref builds);
                return new ValueTask<Workflow>(CountingWorkflow.Build());
            },
            cacheWorkflow: true);

        // Act: two turns for the same session.
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "go");
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", "go");

        // Assert: the factory ran exactly once (cached), and the reused instance still advanced state 1 -> 2.
        Assert.Equal(1, builds);
        Assert.Contains("count:1", StringOutput(first));
        Assert.Contains("count:2", StringOutput(second));
    }

    [Fact]
    public async Task RunOrResumeAsync_CachedFactory_RetriesAfterFaultedBuildAsync()
    {
        // Arrange: a cached factory whose first build faults, then succeeds. A faulted cached build must not be
        // reused; the next run must retry rather than re-observe the same failure forever. The first build faults
        // asynchronously so the faulted Task is actually cached, exercising the reuse guard.
        int builds = 0;
        var state = new HostedWorkflowState(
            _ =>
            {
                int attempt = Interlocked.Increment(ref builds);
                if (attempt == 1)
                {
                    return new ValueTask<Workflow>(Task.FromException<Workflow>(new InvalidOperationException("transient build failure")));
                }

                return new ValueTask<Workflow>(CountingWorkflow.Build());
            },
            cacheWorkflow: true);

        // Act & Assert: the first run surfaces the build failure.
        await Assert.ThrowsAsync<InvalidOperationException>(() => state.RunOrResumeAsync("s1", "go").AsTask());

        // A later run rebuilds (the faulted task was not cached) and succeeds.
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", "go");
        Assert.Equal(2, builds);
        Assert.Contains("count:1", StringOutput(second));

        // Once a successful build is cached, further runs reuse it (no additional builds).
        HostedWorkflowRunResult third = await state.RunOrResumeAsync("s1", "go");
        Assert.Equal(2, builds);
        Assert.Contains("count:2", StringOutput(third));
    }

    [Fact]
    public async Task RunOrResumeAsync_UncachedFactory_BuildsPerRunAsync()
    {
        // Arrange: the default (uncached) factory builds a fresh instance for every run.
        int builds = 0;
        var state = new HostedWorkflowState(
            _ =>
            {
                Interlocked.Increment(ref builds);
                return new ValueTask<Workflow>(CountingWorkflow.Build());
            });

        // Act: two turns for the same session.
        _ = await state.RunOrResumeAsync("s1", "go");
        _ = await state.RunOrResumeAsync("s1", "go");

        // Assert: the factory ran once per run.
        Assert.Equal(2, builds);
    }

    [Fact]
    public async Task RunOrResumeAsync_NonChatWorkflow_ResumesWithNewInputAsync()
    {
        // Arrange: a non-chat-protocol workflow (string start executor), so the resume path sends the input
        // without a TurnToken.
        var state = new HostedWorkflowState(CountingWorkflow.Build());
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "go");
        Assert.Contains("count:1", StringOutput(first));

        // Act
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", "go")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: the non-chat resume carried state and advanced the checkpoint.
        Assert.Contains("count:2", StringOutput(second));
        Assert.NotNull(second.Checkpoint);
        Assert.NotSame(first.Checkpoint, second.Checkpoint);
    }

    [Fact]
    public async Task RunOrResumeAsync_ThirdTurn_KeepsAdvancingCheckpointAsync()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateEchoWorkflow());

        // Act: three turns on the same session.
        HostedWorkflowRunResult r1 = await state.RunOrResumeAsync("s1", InputMessages("a"));
        HostedWorkflowRunResult r2 = await state.RunOrResumeAsync("s1", InputMessages("b"))
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));
        HostedWorkflowRunResult r3 = await state.RunOrResumeAsync("s1", InputMessages("c"))
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: the cursor keeps advancing past the second turn, and the head reflects the latest turn.
        Assert.Contains("c", OutputText(r3));
        Assert.NotNull(r1.Checkpoint);
        Assert.NotNull(r3.Checkpoint);
        Assert.NotSame(r1.Checkpoint, r2.Checkpoint);
        Assert.NotSame(r2.Checkpoint, r3.Checkpoint);
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? head));
        Assert.Same(r3.Checkpoint, head);
    }

    [Fact]
    public async Task RunOrResumeStreamingAsync_StreamsEventsAndResumesAsync()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateEchoWorkflow());

        // Act: first turn streamed.
        List<WorkflowEvent> firstEvents = [];
        await foreach (WorkflowEvent evt in state.RunOrResumeStreamingAsync("s1", InputMessages("hello")))
        {
            firstEvents.Add(evt);
        }

        // Assert: events streamed and the checkpoint was recorded after the stream completed.
        Assert.NotEmpty(firstEvents);
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? firstCheckpoint));
        Assert.NotNull(firstCheckpoint);

        // Act: second turn streamed via the resume path with new input.
        List<WorkflowEvent> secondEvents = [];
        await foreach (WorkflowEvent evt in state.RunOrResumeStreamingAsync("s1", InputMessages("world")))
        {
            secondEvents.Add(evt);
        }

        // Assert: the resumed stream processed the new input and advanced the checkpoint.
        string output = string.Concat(
            secondEvents
                .OfType<WorkflowOutputEvent>()
                .Select(e => e.Data)
                .OfType<IEnumerable<ChatMessage>>()
                .SelectMany(messages => messages)
                .Select(m => m.Text));
        Assert.Contains("world", output);
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? secondCheckpoint));
        Assert.NotSame(firstCheckpoint, secondCheckpoint);
    }

    [Fact]
    public async Task RunOrResumeAsync_AdaptsResponsesInputToTypedStartExecutorAsync()
    {
        // Arrange: a workflow whose start executor takes a typed WriterBrief rather than List<ChatMessage>.
        // The application adapts the Responses input into that type before calling RunOrResumeAsync via the
        // generic TInput.
        var state = new HostedWorkflowState(BriefWorkflow.Build());

        // Simulate parsing a structured Responses text payload into the start executor's input type.
        const string ResponsesText = "{\"topic\":\"electric SUV\",\"style\":\"playful\"}";
        using JsonDocument doc = JsonDocument.Parse(ResponsesText);
        var brief = new BriefWorkflow.WriterBrief(
            doc.RootElement.GetProperty("topic").GetString()!,
            doc.RootElement.GetProperty("style").GetString()!);

        // Act
        HostedWorkflowRunResult result = await state.RunOrResumeAsync("s1", brief);

        // Assert: the adapted input drove the typed start executor.
        Assert.Contains("[playful] electric SUV", StringOutput(result));
    }

    [Fact]
    public async Task RunOrResumeAsync_ResumeWithRejectedInput_DoesNotHangAsync()
    {
        // Arrange: a non-chat human-in-the-loop workflow whose first turn emits a request and halts.
        var state = new HostedWorkflowState(ApprovalGateWorkflow.Build());
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "approve")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));
        Assert.Contains(first.Events, e => e is RequestInfoEvent);

        // Act: resume with an input the start executor cannot handle (wrong type), so no superstep runs.
        // A drain that blocks on the restored pending request would hang here; guard with a timeout.
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", 42)
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: it returned (surfacing the restored pending request) rather than blocking indefinitely.
        Assert.Contains(second.Events, e => e is RequestInfoEvent);
    }

    [Fact]
    public async Task RunOrResumeAsync_ResumeSuperstepWithRequestAndDownstream_DoesNotTruncateAsync()
    {
        // Arrange: a workflow whose start executor, in one superstep, emits a request AND queues a message to
        // a downstream executor that yields output. The first turn establishes a checkpoint.
        var state = new HostedWorkflowState(FanOutRequestWorkflow.Build());
        HostedWorkflowRunResult first = await state.RunOrResumeAsync("s1", "one")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));
        Assert.Contains(first.Events, e => e is RequestInfoEvent);

        // Act: resume with new input, which again fans out to the request port and the downstream executor.
        HostedWorkflowRunResult second = await state.RunOrResumeAsync("s1", "two")
            .AsTask()
            .WaitAsync(TimeSpan.FromSeconds(30));

        // Assert: the resumed turn drained past the request-bearing superstep so the downstream output is
        // present (a drain that broke at the request would truncate it).
        Assert.Contains(second.Events, e => e is RequestInfoEvent);
        Assert.Contains(FanOutRequestWorkflow.DownstreamPrefix, StringOutput(second));
    }

    [Fact]
    public async Task RunOrResumeStreamingAsync_AbandonedAfterCheckpoint_AdvancesCursorAsync()
    {
        // Arrange
        var state = new HostedWorkflowState(CreateEchoWorkflow());
        await foreach (WorkflowEvent _ in state.RunOrResumeStreamingAsync("s1", InputMessages("a")))
        {
            // Enumerate the first turn to completion so the cursor holds its head checkpoint.
        }
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? cp1));

        // Act: abandon the second turn after a superstep has committed a checkpoint.
        await foreach (WorkflowEvent evt in state.RunOrResumeStreamingAsync("s1", InputMessages("b")))
        {
            if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: not null })
            {
                break;
            }
        }

        // Assert: the abandoned turn still advanced the cursor to the last committed checkpoint, so a later
        // turn resumes from there rather than re-running from the previous head.
        Assert.True(state.TryGetCheckpoint("s1", out CheckpointInfo? cp2));
        Assert.NotEqual(cp1, cp2);
    }

    private static List<ChatMessage> InputMessages(string text) => [new(ChatRole.User, text)];

    private static string OutputText(HostedWorkflowRunResult result) =>
        string.Concat(
            result.Events
                .OfType<WorkflowOutputEvent>()
                .Select(e => e.Data)
                .OfType<IEnumerable<ChatMessage>>()
                .SelectMany(messages => messages)
                .Select(m => m.Text));

    private static string StringOutput(HostedWorkflowRunResult result) =>
        string.Concat(
            result.Events
                .OfType<WorkflowOutputEvent>()
                .Select(e => e.Data)
                .OfType<string>());

    private static Workflow CreateEchoWorkflow() =>
        AgentWorkflowBuilder.BuildSequential(workflowName: "echo", agents: [new TestEchoAgent(name: "echo")]);

    private static Workflow CreateTestWorkflow()
    {
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("testAgent");
        return AgentWorkflowBuilder.BuildSequential(workflowName: "wf", agents: [mockAgent.Object]);
    }
}
