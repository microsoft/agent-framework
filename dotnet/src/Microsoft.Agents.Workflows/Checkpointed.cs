// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Represents a workflow run that supports checkpointing.
/// </summary>
/// <typeparam name="TRun">The type of the underlying workflow run handle.</typeparam>
/// <seealso cref="Run"/>
/// <seealso cref="Run{TResult}"/>
/// <seealso cref="StreamingRun"/>
/// <seealso cref="StreamingRun{TResult}"/>
public class Checkpointed<TRun>
{
    private readonly ICheckpointingRunner _runner;

    internal Checkpointed(TRun run, ICheckpointingRunner runner)
    {
        this.Run = Throw.IfNull(run);
        this._runner = Throw.IfNull(runner);
    }

    /// <summary>
    /// Gets the workflow run associated with this <see cref="Checkpointed{TRun}"/> instance.
    /// </summary>
    /// <seealso cref="Run"/>
    /// <seealso cref="Run{TResult}"/>
    /// <seealso cref="StreamingRun"/>
    /// <seealso cref="StreamingRun{TResult}"/>
    public TRun Run { get; }

    /// <inheritdoc cref="ICheckpointingRunner.Checkpoints"/>
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

    /// <inheritdoc cref="ICheckpointingRunner.RestoreCheckpointAsync"/>
    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellation = default)
        => this._runner.RestoreCheckpointAsync(checkpointInfo, cancellation);
}
