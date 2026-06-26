// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Default <see cref="IHostedTargetRunner"/> for <see cref="Workflow"/> targets. Drives execution via
/// <see cref="InProcessExecution"/> and projects pause / completion / failure into
/// <see cref="WorkflowRunResult"/>.
/// </summary>
/// <remarks>
/// When the host state store yields a persistent checkpoint location for the request's isolation key, the
/// runner enables per-isolation-key file checkpointing: each run is checkpointed under that directory, the
/// resulting checkpoint id is surfaced on the result session attributes (<c>"workflow.checkpoint_id"</c>),
/// and a subsequent request carrying that id on <see cref="ChannelRequest.Attributes"/> resumes from it. With
/// the in-memory store (no persistent location) the runner simply runs forward.
/// </remarks>
public sealed class WorkflowRunner : IHostedTargetRunner
{
    /// <summary>Attribute key for caller-supplied checkpoint resume (and the surfaced resume token).</summary>
    public const string CheckpointIdAttribute = "workflow.checkpoint_id";

    private readonly IHostStateStore? _stateStore;

    /// <summary>Initializes a new instance.</summary>
    public WorkflowRunner(Workflow workflow) : this(workflow, stateStore: null)
    {
    }

    /// <summary>Initializes a new instance with a host state store for per-isolation-key checkpointing.</summary>
    public WorkflowRunner(Workflow workflow, IHostStateStore? stateStore)
    {
        this.Workflow = Throw.IfNull(workflow);
        this._stateStore = stateStore;
    }

    /// <summary>The wrapped workflow.</summary>
    public Workflow Workflow { get; }

    /// <inheritdoc />
    public async ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken)
    {
        Throw.IfNull(request);
        var (run, store) = await this.OpenRunAsync(request, cancellationToken).ConfigureAwait(false);
        try
        {
            var outputs = new List<object?>();
            ExternalRequest? pending = null;

            await foreach (var evt in run.WatchStreamAsync(cancellationToken).ConfigureAwait(false))
            {
                switch (evt)
                {
                    case RequestInfoEvent rie:
                        // The workflow paused awaiting external input; stop consuming or the stream blocks.
                        pending = rie.Request;
                        goto done;
                    case AgentResponseUpdateEvent:
                        // Streaming delta from an agent-based workflow; not a terminal output.
                        break;
                    case WorkflowOutputEvent woe:
                        outputs.Add(woe.Data);
                        break;
                    case WorkflowErrorEvent err:
                        return Build(new WorkflowRunResult { Status = WorkflowRunStatus.Failed, Error = err.Data?.ToString(), Outputs = outputs, SessionId = run.SessionId }, request.Session);
                }
            }

done:
            return BuildResult(run, pending, outputs, request);
        }
        finally
        {
            store?.Dispose();
        }
    }

    /// <inheritdoc />
    public async IAsyncEnumerable<HostedStreamItem> StreamAsync(
        ChannelRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        Throw.IfNull(request);
        var (run, store) = await this.OpenRunAsync(request, cancellationToken).ConfigureAwait(false);
        try
        {
            var outputs = new List<object?>();
            ExternalRequest? pending = null;

            await foreach (var evt in run.WatchStreamAsync(cancellationToken).ConfigureAwait(false))
            {
                yield return new HostedStreamEvent(evt);
                if (evt is RequestInfoEvent rie)
                {
                    // The workflow paused awaiting external input; stop consuming or the stream blocks.
                    pending = rie.Request;
                    break;
                }

                if (evt is WorkflowOutputEvent woe and not AgentResponseUpdateEvent)
                {
                    outputs.Add(woe.Data);
                }
            }

            yield return new HostedStreamCompleted(BuildResult(run, pending, outputs, request));
        }
        finally
        {
            store?.Dispose();
        }
    }

    private async ValueTask<(StreamingRun Run, FileSystemJsonCheckpointStore? Store)> OpenRunAsync(ChannelRequest request, CancellationToken cancellationToken)
    {
        var sessionKey = request.Session?.IsolationKey ?? request.Session?.Key;

        string? location = null;
        if (this._stateStore is not null && !string.IsNullOrEmpty(sessionKey))
        {
            location = await this._stateStore.GetCheckpointLocationAsync(sessionKey!, cancellationToken).ConfigureAwait(false);
        }

        if (location is null)
        {
            var plain = await InProcessExecution.OpenStreamingAsync(this.Workflow, request.Session?.Key, cancellationToken).ConfigureAwait(false);
            await SendInputAsync(plain, request.Input).ConfigureAwait(false);
            return (plain, null);
        }

        var store = new FileSystemJsonCheckpointStore(new DirectoryInfo(location));
        var manager = CheckpointManager.CreateJson(store);

        if (request.Attributes.TryGetValue(CheckpointIdAttribute, out var raw) && raw is string checkpointId && !string.IsNullOrEmpty(checkpointId))
        {
            // Rehydrate the workflow from the caller-supplied checkpoint, then apply the new input so the
            // resumed run advances and produces output (mirrors Python's restore-then-run seam).
            var resumed = await InProcessExecution.ResumeStreamingAsync(this.Workflow, new CheckpointInfo(sessionKey!, checkpointId), manager, cancellationToken).ConfigureAwait(false);
            await SendInputAsync(resumed, request.Input).ConfigureAwait(false);
            return (resumed, store);
        }

        var run = await InProcessExecution.OpenStreamingAsync(this.Workflow, manager, sessionKey, cancellationToken).ConfigureAwait(false);
        await SendInputAsync(run, request.Input).ConfigureAwait(false);
        return (run, store);
    }

    /// <summary>
    /// Send the channel input to the run using its <b>runtime</b> type so the workflow's typed start executor
    /// receives it. Passing <see cref="ChannelRequest.Input"/> directly to a generic run API would declare the
    /// message type as <see cref="object"/>, which a typed executor never matches. A subsequent
    /// <see cref="TurnToken"/> drives agent-based workflows (built via <c>AgentWorkflowBuilder</c>) to take a
    /// turn and emit their outputs; it is harmlessly undelivered for plain executor workflows that have no
    /// <see cref="TurnToken"/> handler, so it is sent unconditionally for parity with Python's high-level
    /// <c>Workflow.run(message)</c> seam.
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2060:MakeGenericMethod", Justification = "Input is a reference type (string / ChatMessage list / workflow input); shared generics keep TrySendMessageAsync reachable.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Hosting runner is not used in AOT scenarios; the workflow input type is a reference type.")]
    private static async ValueTask SendInputAsync(StreamingRun run, object input)
    {
        var send = s_trySendMessage.MakeGenericMethod(input.GetType());
        await ((ValueTask<bool>)send.Invoke(run, [input])!).ConfigureAwait(false);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true)).ConfigureAwait(false);
    }

    private static readonly MethodInfo s_trySendMessage =
        typeof(StreamingRun).GetMethod(nameof(StreamingRun.TrySendMessageAsync))!;

    private static HostedRunResult<WorkflowRunResult> BuildResult(StreamingRun run, ExternalRequest? pending, List<object?> outputs, ChannelRequest request)
    {
        var session = new ChannelSession(request.Session ?? new ChannelSession()) { Key = run.SessionId };

        var checkpointId = run.LastCheckpoint?.CheckpointId;
        if (checkpointId is not null)
        {
            session.Attributes = new Dictionary<string, object?>(session.Attributes) { [CheckpointIdAttribute] = checkpointId };
        }

        var result = pending is not null
            ? new WorkflowRunResult { Status = WorkflowRunStatus.AwaitingInput, PendingRequest = pending, Outputs = outputs, SessionId = run.SessionId }
            : new WorkflowRunResult { Status = WorkflowRunStatus.Completed, Outputs = outputs, SessionId = run.SessionId };
        return Build(result, session);
    }

    private static HostedRunResult<WorkflowRunResult> Build(WorkflowRunResult result, ChannelSession? session) =>
        new(result) { Session = session };
}
