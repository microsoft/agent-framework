// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal interface ICheckpointingRunner
{
    // TODO: Convert this to a multi-timeline (e.g.: Live timeline + forks for orphaned checkpoints due to timetravel)
    IReadOnlyList<CheckpointInfo> Checkpoints { get; }

    ValueTask RestoreCheckpointAsync(CheckpointInfo checkpointInfo, CancellationToken cancellation = default);
}
