// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// .
/// </summary>
/// <typeparam name="TRun"></typeparam>
public class Checkpointed<TRun>
{
    internal Checkpointed(TRun run, ICheckpointingRunner runner)
    {
        this.Run = Throw.IfNull(run);
        this._runner = Throw.IfNull(runner);
    }

    private readonly ICheckpointingRunner _runner;

    /// <summary>
    /// .
    /// </summary>
    public TRun Run { get; }

    /// <inheritdoc cref="ICheckpointingRunner.Checkpoints"/>
    public IReadOnlyList<CheckpointInfo> Checkpoints => this._runner.Checkpoints;

    /// <summary>
    /// Gets the most recent checkpoint information.
    /// </summary>
    public CheckpointInfo? LastCheckpoint => this.Checkpoints[this.Checkpoints.Count];

    /// <inheritdoc cref="ICheckpointingRunner.RestoreCheckpointAsync"/>
    public ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellation = default)
        => this._runner.RestoreCheckpointAsync(checkpointInfo, cancellation);
}

//internal interface ISerializer
//{
//    ValueTask<Checkpoint> DeserializeAsync(Stream stream);
//    ValueTask SerializeAsync(Stream stream, Checkpoint checkpoint);
//}
