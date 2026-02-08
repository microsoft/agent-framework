// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents a workflow run that supports checkpointing.
/// </summary>
/// <typeparam name="TRun">The type of the underlying workflow run handle.</typeparam>
/// <seealso cref="Run"/>
/// <seealso cref="StreamingRun"/>
public sealed class Checkpointed<TRun> : IAsyncDisposable
{
    private readonly ICheckpointingHandle _runner;

    internal Checkpointed(TRun run, ICheckpointingHandle runner)
    {
        this.Run = Throw.IfNull(run);
        this._runner = Throw.IfNull(runner);
    }

    /// <summary>
    /// Gets the workflow run associated with this <see cref="Checkpointed{TRun}"/> instance.
    /// </summary>
    /// <seealso cref="Run"/>
    /// <seealso cref="StreamingRun"/>
    public TRun Run { get; }

    /// <inheritdoc cref="ICheckpointingHandle.Checkpoints"/>
    public IReadOnlyList<CheckpointInfo> Checkpoints => this._runner.Checkpoints;

    /// <summary>
    /// Gets the most recent checkpoint information.
    /// </summary>
    public CheckpointInfo? LastCheckpoint
    {
        get
        {
            var checkpoints = this.Checkpoints;
            return checkpoints.Count > 0 ? checkpoints[checkpoints.Count - 1] : null;
        }
    }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        if (this.Run is IAsyncDisposable asyncDisposable)
        {
            await asyncDisposable.DisposeAsync().ConfigureAwait(false);
        }
        else if (this.Run is IDisposable disposable)
        {
            disposable.Dispose();
        }
    }

    /// <inheritdoc cref="ICheckpointingHandle.RestoreCheckpointAsync"/>
    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellationToken = default)
        => this._runner.RestoreCheckpointAsync(checkpointInfo, cancellationToken);
}
