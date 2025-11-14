// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class AsyncRunHandle : ICheckpointingHandle, IAsyncDisposable
{
    private readonly ISuperStepRunner _stepRunner;
    private readonly ICheckpointingHandle _checkpointingHandle;

    private readonly IRunEventStream _eventStream;
    private readonly CancellationTokenSource _endRunSource = new();
    private int _isDisposed;
    private int _isEventStreamTaken;

    internal AsyncRunHandle(ISuperStepRunner stepRunner, ICheckpointingHandle checkpointingHandle, ExecutionMode mode)
    {
        this._stepRunner = Throw.IfNull(stepRunner);
        this._checkpointingHandle = Throw.IfNull(checkpointingHandle);

        this._eventStream = mode switch
        {
            ExecutionMode.OffThread => new StreamingRunEventStream(stepRunner),
            ExecutionMode.Subworkflow => new StreamingRunEventStream(stepRunner, disableRunLoop: true),
            ExecutionMode.Lockstep => new LockstepRunEventStream(stepRunner),
            _ => throw new ArgumentOutOfRangeException(nameof(mode), $"Unknown execution mode {mode}")
        };

        this._eventStream.Start();

        // If there are already unprocessed messages (e.g., from a checkpoint restore that happened
        // before this handle was created), signal the run loop to start processing them
        if (stepRunner.HasUnprocessedMessages)
        {
            this.SignalInputToRunLoop();
        }
    }

    public string RunId => this._stepRunner.RunId;

    public IReadOnlyList<CheckpointInfo> Checkpoints => this._checkpointingHandle.Checkpoints;

    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellationToken = default)
        => this._eventStream.GetStatusAsync(cancellationToken);

    public async IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync(bool blockOnPendingRequest, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        //Debug.Assert(breakOnHalt);
        // Enforce single active enumerator (this runs when enumeration begins)
        if (Interlocked.CompareExchange(ref this._isEventStreamTaken, 1, 0) != 0)
        {
            throw new InvalidOperationException("The event stream has already been taken. Only one enumerator is allowed at a time.");
        }

        CancellationTokenSource? linked = null;
        try
        {
            linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, this._endRunSource.Token);
            var token = linked.Token;

            // Build the inner stream before the loop so synchronous exceptions still release the gate
            var inner = this._eventStream.TakeEventStreamAsync(blockOnPendingRequest, token);

            await foreach (var ev in inner.WithCancellation(token).ConfigureAwait(false))
            {
                // Filter out the RequestHaltEvent, since it is an internal signalling event.
                if (ev is RequestHaltEvent)
                {
                    yield break;
                }

                yield return ev;
            }
        }
        finally
        {
            linked?.Dispose();
            Interlocked.Exchange(ref this._isEventStreamTaken, 0);
        }
    }

    public ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellationToken = default)
        => this._stepRunner.IsValidInputTypeAsync<T>(cancellationToken);

    public async ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellationToken = default)
    {
        if (message is ExternalResponse response)
        {
            // EnqueueResponseAsync handles signaling
            await this.EnqueueResponseAsync(response, cancellationToken)
                      .ConfigureAwait(false);

            return true;
        }

        bool result = await this._stepRunner.EnqueueMessageAsync(message, cancellationToken)
                                            .ConfigureAwait(false);

        // Signal the run loop that new input is available
        this.SignalInputToRunLoop();

        return result;
    }

    public async ValueTask<bool> EnqueueMessageUntypedAsync([NotNull] object message, Type? declaredType = null, CancellationToken cancellationToken = default)
    {
        if (declaredType?.IsInstanceOfType(message) == false)
        {
            throw new ArgumentException($"Message is not of the declared type {declaredType}. Actual type: {message.GetType()}", nameof(message));
        }

        if (declaredType != null && typeof(ExternalResponse).IsAssignableFrom(declaredType))
        {
            // EnqueueResponseAsync handles signaling
            await this.EnqueueResponseAsync((ExternalResponse)message, cancellationToken)
                      .ConfigureAwait(false);

            return true;
        }
        else if (declaredType == null && message is ExternalResponse response)
        {
            // EnqueueResponseAsync handles signaling
            await this.EnqueueResponseAsync(response, cancellationToken)
                      .ConfigureAwait(false);

            return true;
        }

        bool result = await this._stepRunner.EnqueueMessageUntypedAsync(message, declaredType ?? message.GetType(), cancellationToken)
                                            .ConfigureAwait(false);

        // Signal the run loop that new input is available
        this.SignalInputToRunLoop();

        return result;
    }

    public async ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellationToken = default)
    {
        await this._stepRunner.EnqueueResponseAsync(response, cancellationToken).ConfigureAwait(false);

        // Signal the run loop that new input is available
        this.SignalInputToRunLoop();
    }

    private void SignalInputToRunLoop()
    {
        this._eventStream.SignalInput();
    }

    public async ValueTask CancelRunAsync()
    {
        this._endRunSource.Cancel();

        await this._eventStream.StopAsync().ConfigureAwait(false);
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref this._isDisposed, 1) == 0)
        {
            // Cancel the run if it is still running
            await this.CancelRunAsync().ConfigureAwait(false);

            // These actually release and clean up resources
            await this._stepRunner.RequestEndRunAsync().ConfigureAwait(false);
            this._endRunSource.Dispose();

            await this._eventStream.DisposeAsync().ConfigureAwait(false);
        }
    }

    public async ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
    {
        // Clear buffered events from the channel BEFORE restoring to discard stale events from supersteps
        // that occurred after the checkpoint we're restoring to
        // This must happen BEFORE the restore so that events republished during restore aren't cleared
        if (this._eventStream is StreamingRunEventStream streamingEventStream)
        {
            streamingEventStream.ClearBufferedEvents();
        }

        // Restore the workflow state - this will republish unserviced requests as new events
        await this._checkpointingHandle.RestoreCheckpointAsync(checkpointInfo, cancellationToken).ConfigureAwait(false);

        // After restore, signal the run loop to process any restored messages
        // This is necessary because ClearBufferedEvents() doesn't signal, and the restored
        // queued messages won't automatically wake up the run loop
        this.SignalInputToRunLoop();
    }
}
