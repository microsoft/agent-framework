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

internal sealed class AsyncRunHandle : ICheckpointingHandle, IAsyncDisposable, IInputCoordinator
{
    private readonly AsyncCoordinator _waitForResponseCoordinator = new();
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
            ExecutionMode.OffThread => new OffThreadRunEventStream(stepRunner, this),
            ExecutionMode.Lockstep => new LockstepRunEventStream(stepRunner),
            _ => throw new ArgumentOutOfRangeException(nameof(mode), $"Unknown execution mode {mode}")
        };
        this._eventStream.Start();
    }

    public ValueTask WaitForNextInputAsync(CancellationToken cancellation = default)
        => this._waitForResponseCoordinator.WaitForCoordinationAsync(cancellation);

    public void ReleaseResponseWaiter() => this._waitForResponseCoordinator.MarkCoordinationPoint();

    public string RunId => this._stepRunner.RunId;

    public IReadOnlyList<CheckpointInfo> Checkpoints => this._checkpointingHandle.Checkpoints;

    public ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellation = default)
        => this._eventStream.GetStatusAsync(cancellation);

    public async IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync(bool breakOnHalt, [EnumeratorCancellation] CancellationToken cancellation = default)
    {
        // Create a linked cancellation token that combines the provided token with the end-run token
        using var linkedSource = CancellationTokenSource.CreateLinkedTokenSource(cancellation, this._endRunSource.Token);

        // Only one enumerator of this is allowed at a time
        if (Interlocked.CompareExchange(ref this._isEventStreamTaken, 1, 0) != 0)
        {
            throw new InvalidOperationException("The event stream has already been taken. Only one enumerator is allowed at a time.");
        }

        try
        {
            await foreach (WorkflowEvent @event in this._eventStream.TakeEventStreamAsync(linkedSource.Token)
                                                                    .ConfigureAwait(false))
            {
                yield return @event;
            }
        }
        finally
        {
            Volatile.Write(ref this._isEventStreamTaken, 0);
        }
    }

    public ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellation = default)
        => this._stepRunner.IsValidInputTypeAsync<T>(cancellation);

    public async ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellation = default)
    {
        if (message is ExternalResponse response)
        {
            // EnqueueResponseAsync marks the coordination point itself
            await this.EnqueueResponseAsync(response, cancellation)
                      .ConfigureAwait(false);

            return true;
        }

        bool result = await this._stepRunner.EnqueueMessageAsync(message, cancellation)
                                            .ConfigureAwait(false);

        this._waitForResponseCoordinator.MarkCoordinationPoint();

        return result;
    }

    public async ValueTask<bool> EnqueueMessageUntypedAsync([NotNull] object message, Type? declaredType = null, CancellationToken cancellation = default)
    {
        if (declaredType?.IsInstanceOfType(message) == false)
        {
            throw new ArgumentException($"Message is not of the declared type {declaredType}. Actual type: {message.GetType()}", nameof(message));
        }

        if (declaredType != null && typeof(ExternalResponse).IsAssignableFrom(declaredType))
        {
            // EnqueueResponseAsync marks the coordination point itself
            await this.EnqueueResponseAsync((ExternalResponse)message, cancellation)
                      .ConfigureAwait(false);

            return true;
        }
        else if (declaredType == null && message is ExternalResponse response)
        {
            // EnqueueResponseAsync marks the coordination point itself
            await this.EnqueueResponseAsync(response, cancellation)
                      .ConfigureAwait(false);

            return true;
        }

        bool result = await this._stepRunner.EnqueueMessageUntypedAsync(message, declaredType ?? message.GetType(), cancellation)
                                            .ConfigureAwait(false);

        this._waitForResponseCoordinator.MarkCoordinationPoint();

        return result;
    }

    public async ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellation = default)
    {
        await this._stepRunner.EnqueueResponseAsync(response, cancellation).ConfigureAwait(false);

        this._waitForResponseCoordinator.MarkCoordinationPoint();
    }

    public ValueTask RequestEndRunAsync()
    {
        this._endRunSource.Cancel();
        return this._stepRunner.RequestEndRunAsync();
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref this._isDisposed, 1) == 0)
        {
            this._endRunSource.Cancel();
            await this.RequestEndRunAsync().ConfigureAwait(false);
            this._endRunSource.Dispose();

            await this._eventStream.DisposeAsync().ConfigureAwait(false);
        }
    }

    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
        => this._checkpointingHandle.RestoreCheckpointAsync(checkpointInfo, cancellationToken);
}
