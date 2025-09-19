// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// An in-memory implementation of <see cref="ICheckpointManager"/> that stores checkpoints in a dictionary.
/// </summary>
internal sealed class InMemoryCheckpointManager : ICheckpointManager
{
    private readonly Dictionary<string, RunCheckpointCache<Checkpoint>> _store = [];

    private RunCheckpointCache<Checkpoint> GetRunStore(string runId)
    {
        if (!this._store.TryGetValue(runId, out RunCheckpointCache<Checkpoint>? runStore))
        {
            runStore = this._store[runId] = new();
        }

        return runStore;
    }

    public ValueTask<CheckpointInfo> CommitCheckpointAsync(string runId, Checkpoint checkpoint)
    {
        RunCheckpointCache<Checkpoint> runStore = this.GetRunStore(runId);

        CheckpointInfo key;
        do
        {
            key = new(runId);
        } while (!runStore.Add(key, checkpoint));

        return new(key);
    }

    public ValueTask<Checkpoint> LookupCheckpointAsync(string runId, CheckpointInfo checkpointInfo)
    {
        if (!this.GetRunStore(runId).TryGet(checkpointInfo, out Checkpoint? value))
        {
            throw new KeyNotFoundException($"Could not retrieve checkpoint with id {checkpointInfo.CheckpointId} for run {runId}");
        }

        return new(value);
    }
}
