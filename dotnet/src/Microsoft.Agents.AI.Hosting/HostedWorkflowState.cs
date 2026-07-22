// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Optional shared execution state for applications that own their own hosting route and want to expose a
/// workflow with per-session checkpoint resume. Pairs a <see cref="Workflow"/> target with a
/// <see cref="CheckpointManager"/> and an application-scoped <c>sessionId -&gt; CheckpointInfo</c> head cursor.
/// </summary>
/// <remarks>
/// <para>
/// The .NET workflow checkpoint store is already keyed by session id, but <see cref="CheckpointInfo"/> carries
/// no ordering, so this holder remembers the head checkpoint per session to resume the correct one. It does not
/// own routing, authentication, or storage policy.
/// </para>
/// <para>
/// The in-memory head cursor accelerates the common case, but when it misses (for example a new holder or a
/// process restart) the holder falls back to <see cref="CheckpointManager.GetLatestCheckpointAsync"/>. A durable
/// <see cref="CheckpointManager"/> therefore resumes correctly across restarts; the default in-memory manager does
/// not persist, so with it a restart starts the session fresh.
/// </para>
/// <para>
/// <strong>Trust boundary.</strong> <c>sessionId</c> is an application-selected partition key. When it originates
/// from the wire, the application must authenticate the caller and authorize the key before using it here. The
/// checkpoint boundary must be at least as specific as the authorized session boundary.
/// </para>
/// </remarks>
public sealed class HostedWorkflowState
{
    private readonly CheckpointManager _checkpointManager;
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;
    private readonly Workflow? _workflow;
    private readonly Func<CancellationToken, ValueTask<Workflow>>? _workflowFactory;
    // Cached-factory mode: the factory runs once, on first use, guarded by _cacheSync, and the built workflow task
    // is reused for every run thereafter.
    private readonly bool _cacheWorkflow;
    private readonly object _cacheSync = new();
    private Task<Workflow>? _cachedWorkflowTask;
    private readonly ILogger _logger;
    private readonly ConcurrentDictionary<string, CheckpointInfo> _cursor = new(StringComparer.Ordinal);

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedWorkflowState"/> class over a single shared workflow
    /// instance.
    /// </summary>
    /// <param name="workflow">The workflow target.</param>
    /// <param name="checkpointManager">
    /// The checkpoint manager to use. Defaults to <see cref="CheckpointManager.CreateInMemory"/> when not provided.
    /// </param>
    /// <param name="executionEnvironment">
    /// The workflow execution environment used to run and resume the workflow. Defaults to an in-process environment
    /// (<see cref="InProcessExecutionEnvironment"/>) configured with <paramref name="checkpointManager"/>. Supplying a
    /// custom environment (for example a future durable/out-of-process environment) is supported; the supplied
    /// environment must be configured to checkpoint into the same store as <paramref name="checkpointManager"/>, since
    /// the holder reads that manager directly to recover the head checkpoint when its in-memory cursor misses.
    /// </param>
    /// <param name="loggerFactory">
    /// The logger factory used to report resume diagnostics (for example, a resume turn that made no progress).
    /// Defaults to <see cref="NullLoggerFactory"/> when not provided.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="workflow"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// A single workflow instance cannot be run by two runners at once, so concurrent runs against this holder are
    /// not supported; process turns one at a time. To run independent sessions concurrently, use the factory
    /// constructor
    /// (<see cref="HostedWorkflowState(Func{CancellationToken, ValueTask{Workflow}}, CheckpointManager?, IWorkflowExecutionEnvironment?, ILoggerFactory?, bool)"/>),
    /// which builds a fresh workflow instance per run.
    /// </remarks>
    public HostedWorkflowState(
        Workflow workflow,
        CheckpointManager? checkpointManager = null,
        IWorkflowExecutionEnvironment? executionEnvironment = null,
        ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(workflow);

        this._workflow = workflow;
        this._checkpointManager = checkpointManager ?? CheckpointManager.CreateInMemory();
        this._executionEnvironment = executionEnvironment ?? InProcessExecution.Default.WithCheckpointing(this._checkpointManager);
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger(typeof(HostedWorkflowState));
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedWorkflowState"/> class that builds its workflow from a
    /// factory.
    /// </summary>
    /// <param name="workflowFactory">
    /// A factory that produces a workflow instance. Every produced instance must have the same executor topology,
    /// because a resume rehydrates an instance from the session's checkpoint in the shared
    /// <paramref name="checkpointManager"/>. By default (<paramref name="cacheWorkflow"/> is <see langword="false"/>)
    /// it is invoked once per run, so independent sessions each get their own instance and run concurrently. When
    /// <paramref name="cacheWorkflow"/> is <see langword="true"/> it is invoked once, on first use, and the built
    /// instance is reused for every run.
    /// </param>
    /// <param name="checkpointManager">
    /// The checkpoint manager to use. Defaults to <see cref="CheckpointManager.CreateInMemory"/> when not provided.
    /// </param>
    /// <param name="executionEnvironment">
    /// The workflow execution environment used to run and resume the workflow. Defaults to an in-process environment
    /// (<see cref="InProcessExecutionEnvironment"/>) configured with <paramref name="checkpointManager"/>. A supplied
    /// environment must checkpoint into the same store as <paramref name="checkpointManager"/>, since the holder reads
    /// that manager directly to recover the head checkpoint when its in-memory cursor misses.
    /// </param>
    /// <param name="loggerFactory">
    /// The logger factory used to report resume diagnostics (for example, a resume turn that made no progress).
    /// Defaults to <see cref="NullLoggerFactory"/> when not provided.
    /// </param>
    /// <param name="cacheWorkflow">
    /// When <see langword="false"/> (the default), the factory is invoked once per run, so independent sessions run
    /// in parallel. When <see langword="true"/>, the factory is invoked once, lazily on first use, and the built
    /// workflow is cached and reused for every run, a deferred, cached target. Because that reuses a single
    /// instance (which cannot be run by two runners at once), a cached workflow's turns cannot run concurrently,
    /// exactly like the instance constructor. The cached build uses <see cref="CancellationToken.None"/> because the
    /// single built instance is shared across runs and must not be tied to one request's cancellation. If a cached
    /// build faults or is canceled, it is not reused: the next run starts a fresh build so a transient setup failure
    /// does not poison every later run.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="workflowFactory"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// With the default (uncached) factory, turns are not serialized: independent sessions run in parallel, and
    /// concurrent turns against the <em>same</em> session id are not serialized either — an application that needs a
    /// single writer per session owns that coordination.
    /// </remarks>
    public HostedWorkflowState(
        Func<CancellationToken, ValueTask<Workflow>> workflowFactory,
        CheckpointManager? checkpointManager = null,
        IWorkflowExecutionEnvironment? executionEnvironment = null,
        ILoggerFactory? loggerFactory = null,
        bool cacheWorkflow = false)
    {
        _ = Throw.IfNull(workflowFactory);

        this._workflowFactory = workflowFactory;
        this._cacheWorkflow = cacheWorkflow;

        this._checkpointManager = checkpointManager ?? CheckpointManager.CreateInMemory();
        this._executionEnvironment = executionEnvironment ?? InProcessExecution.Default.WithCheckpointing(this._checkpointManager);
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger(typeof(HostedWorkflowState));
    }

    // Resolves the workflow for a turn: the shared instance in instance mode; the cached instance in cached-factory
    // mode (built once on first use); or a fresh instance from the factory in the default (uncached) factory mode.
    private async ValueTask<Workflow> ResolveWorkflowAsync(CancellationToken cancellationToken)
    {
        if (this._workflow is not null)
        {
            return this._workflow;
        }

        if (!this._cacheWorkflow)
        {
            return await this._workflowFactory!(cancellationToken).ConfigureAwait(false);
        }

        // Cached factory: build the workflow once. The lock guards only the one-time task assignment (and the
        // factory's synchronous prefix); the actual build is awaited outside the lock. CancellationToken.None is
        // used because the single built instance is shared across runs and must not be tied to one request.
        // A previously cached build that faulted or was canceled is not reused: the next call starts a fresh
        // build so a transient setup failure does not poison every later run with the same cached failure.
        Task<Workflow> buildTask;
        lock (this._cacheSync)
        {
            // Reuse the cached build only when it exists and has not faulted or been canceled; otherwise start a
            // fresh build so a transient setup failure does not poison every later run.
            if (this._cachedWorkflowTask is not { IsFaulted: false, IsCanceled: false })
            {
                this._cachedWorkflowTask = this._workflowFactory!(CancellationToken.None).AsTask();
            }

            buildTask = this._cachedWorkflowTask;
        }

        return await buildTask.ConfigureAwait(false);
    }

    /// <summary>
    /// Runs the workflow forward for <paramref name="sessionId"/> with checkpointing on the first turn, or, on
    /// subsequent turns, restores the session's recorded head checkpoint and then runs the workflow forward with
    /// the new turn's <paramref name="input"/>. The new head checkpoint is recorded for the session afterwards.
    /// </summary>
    /// <remarks>
    /// The resume semantics restore then run: each turn restores the latest checkpoint to rehydrate accumulated
    /// workflow state and then applies the new input, rather than continuing a halted run with no input (which
    /// would leave the run waiting for input indefinitely). For agent (chat-protocol) workflows the new input is
    /// accompanied by a
    /// <see cref="TurnToken"/> so the turn is driven, matching the fresh-run path.
    /// </remarks>
    /// <typeparam name="TInput">The workflow input type.</typeparam>
    /// <param name="sessionId">The application-selected session id.</param>
    /// <param name="input">The input to run on this turn (used both when starting a new run and when resuming).</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>The run result, including the events emitted on this turn and the recorded head checkpoint.</returns>
    public async ValueTask<HostedWorkflowRunResult> RunOrResumeAsync<TInput>(string sessionId, TInput input, CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        _ = Throw.IfNullOrEmpty(sessionId);
        _ = Throw.IfNull(input);

        return await this.RunOrResumeCoreAsync(sessionId, input, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask<HostedWorkflowRunResult> RunOrResumeCoreAsync<TInput>(string sessionId, TInput input, CancellationToken cancellationToken)
        where TInput : notnull
    {
        Workflow workflow = await this.ResolveWorkflowAsync(cancellationToken).ConfigureAwait(false);

        if (!this._cursor.TryGetValue(sessionId, out CheckpointInfo? head))
        {
            // The in-memory cursor is empty for this session. Fall back to the checkpoint manager so a durable
            // manager still resumes after the cursor is lost (for example a process restart or a new holder over
            // the same store).
            head = await this._checkpointManager.GetLatestCheckpointAsync(sessionId, cancellationToken).ConfigureAwait(false);
        }

        if (head is null)
        {
            // First turn for this session: run the workflow forward from its start executor with the input.
            Run freshRun = await this._executionEnvironment.RunAsync(workflow, input, sessionId, cancellationToken).ConfigureAwait(false);
            await using (freshRun.ConfigureAwait(false))
            {
                return this.Record(sessionId, freshRun.OutgoingEvents.ToList(), freshRun.LastCheckpoint);
            }
        }

        // Subsequent turn: restore the session's latest checkpoint to rehydrate accumulated workflow state, then
        // run the workflow forward with the new turn's input. Agent workflows use the chat protocol, which requires
        // a TurnToken to drive the turn (mirroring how the fresh-run path seeds one).
        //
        // The streaming resume restores state without draining to a halt first; the non-streaming resume would
        // block waiting for input immediately after restore (before we can deliver the new input).
        ProtocolDescriptor descriptor = await workflow.DescribeProtocolAsync(cancellationToken).ConfigureAwait(false);

        StreamingRun resumed = await this._executionEnvironment.ResumeStreamingAsync(workflow, head, cancellationToken).ConfigureAwait(false);
        await using (resumed.ConfigureAwait(false))
        {
            await resumed.TrySendMessageAsync(input).ConfigureAwait(false);
            if (descriptor.IsChatProtocol() && input is not TurnToken)
            {
                await resumed.TrySendMessageAsync(new TurnToken(emitEvents: true)).ConfigureAwait(false);
            }

            List<WorkflowEvent> events = [];
            // Drain non-blocking on pending requests, matching the first-turn RunAsync path
            // (Run.RunToNextHaltAsync also uses blockOnPendingRequest: false): the workflow may halt awaiting an
            // external response, and blocking there would wait indefinitely.
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cancellationToken).ConfigureAwait(false))
            {
                events.Add(evt);
            }

            if (events.Count == 0)
            {
                this.WarnOnNoProgress(sessionId);
            }

            return this.Record(sessionId, events, resumed.LastCheckpoint);
        }
    }

    /// <summary>
    /// Streams the events of a run-or-resume turn as they occur, applying the same restore-then-run semantics as
    /// <see cref="RunOrResumeAsync{TInput}(string, TInput, CancellationToken)"/>: the first turn runs the workflow
    /// forward from its start executor, and subsequent turns restore the session's latest checkpoint and run
    /// forward with <paramref name="input"/>. The session's head checkpoint is recorded when the stream ends,
    /// including when the consumer abandons enumeration early.
    /// </summary>
    /// <remarks>
    /// The head checkpoint is recorded from the run's last committed checkpoint when the stream ends — whether it
    /// completes normally or the consumer disposes it early — so an interrupted turn still advances the session
    /// cursor.
    /// </remarks>
    /// <typeparam name="TInput">The workflow input type.</typeparam>
    /// <param name="sessionId">The application-selected session id.</param>
    /// <param name="input">The input to run on this turn.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>An asynchronous stream of the <see cref="WorkflowEvent"/>s emitted during this turn.</returns>
    public async IAsyncEnumerable<WorkflowEvent> RunOrResumeStreamingAsync<TInput>(string sessionId, TInput input, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        where TInput : notnull
    {
        _ = Throw.IfNullOrEmpty(sessionId);
        _ = Throw.IfNull(input);

        Workflow workflow = await this.ResolveWorkflowAsync(cancellationToken).ConfigureAwait(false);

        if (!this._cursor.TryGetValue(sessionId, out CheckpointInfo? head))
        {
            head = await this._checkpointManager.GetLatestCheckpointAsync(sessionId, cancellationToken).ConfigureAwait(false);
        }

        ProtocolDescriptor descriptor = await workflow.DescribeProtocolAsync(cancellationToken).ConfigureAwait(false);

        // The fresh streaming run enqueues the input itself; the streaming resume restores state and needs the
        // input delivered explicitly. Neither streaming entry point seeds a TurnToken, so drive chat-protocol
        // workflows with one on both paths.
        StreamingRun run = head is null
            ? await this._executionEnvironment.RunStreamingAsync(workflow, input, sessionId, cancellationToken).ConfigureAwait(false)
            : await this._executionEnvironment.ResumeStreamingAsync(workflow, head, cancellationToken).ConfigureAwait(false);

        await using (run.ConfigureAwait(false))
        {
            if (head is not null)
            {
                await run.TrySendMessageAsync(input).ConfigureAwait(false);
            }

            if (descriptor.IsChatProtocol() && input is not TurnToken)
            {
                await run.TrySendMessageAsync(new TurnToken(emitEvents: true)).ConfigureAwait(false);
            }

            int eventCount = 0;
            try
            {
                // Drain non-blocking on pending requests (see RunOrResumeCoreAsync) so a workflow that halts
                // awaiting an external response ends the stream instead of blocking indefinitely.
                await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false, cancellationToken).ConfigureAwait(false))
                {
                    eventCount++;
                    yield return evt;
                }

                if (eventCount == 0 && head is not null)
                {
                    this.WarnOnNoProgress(sessionId);
                }
            }
            finally
            {
                // Record the head checkpoint even when the consumer abandons the stream (for example an SSE
                // client disconnect), so an interrupted turn still advances the session cursor to the last
                // committed checkpoint and a later turn resumes from there rather than re-running prior work.
                this.UpdateCursor(sessionId, run.LastCheckpoint);
            }
        }
    }

    private HostedWorkflowRunResult Record(string sessionId, List<WorkflowEvent> events, CheckpointInfo? checkpoint)
    {
        this.UpdateCursor(sessionId, checkpoint);
        return new HostedWorkflowRunResult(sessionId, events, checkpoint);
    }

    private void UpdateCursor(string sessionId, CheckpointInfo? checkpoint)
    {
        if (checkpoint is not null)
        {
            this._cursor[sessionId] = checkpoint;
        }
    }

    private void WarnOnNoProgress(string sessionId)
        // The resumed turn drove no work: the checkpoint may be stale or the input may not match the workflow's
        // expected type, so the session's state may not have progressed.
        => this._logger.LogWorkflowResumeMadeNoProgress(sessionId);

    /// <summary>
    /// Gets the recorded head checkpoint for <paramref name="sessionId"/>, if any.
    /// </summary>
    /// <param name="sessionId">The application-selected session id.</param>
    /// <param name="checkpoint">When this method returns, the recorded head checkpoint, or <see langword="null"/>.</param>
    /// <returns><see langword="true"/> when a checkpoint is recorded for the session; otherwise <see langword="false"/>.</returns>
    /// <remarks>
    /// Internal cursor-inspection helper used by tests; not part of the public surface.
    /// </remarks>
    internal bool TryGetCheckpoint(string sessionId, out CheckpointInfo? checkpoint)
    {
        _ = Throw.IfNullOrEmpty(sessionId);
        return this._cursor.TryGetValue(sessionId, out checkpoint);
    }
}

[System.Diagnostics.CodeAnalysis.ExcludeFromCodeCoverage]
internal static partial class HostedWorkflowStateLogMessages
{
    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Resuming workflow session '{SessionId}' produced no events; the checkpoint may be stale or the input may not match the workflow's expected input type. Session state may not have progressed.")]
    public static partial void LogWorkflowResumeMadeNoProgress(this ILogger logger, string sessionId);
}
