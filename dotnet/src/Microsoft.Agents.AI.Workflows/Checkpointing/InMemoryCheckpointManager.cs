// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// An in-memory implementation of <see cref="ICheckpointManager"/> that stores checkpoints in a dictionary.
/// </summary>
internal sealed class InMemoryCheckpointManager : ICheckpointManager
{
    private readonly Dictionary<string, RunCheckpointCache<Checkpoint>> _store = [];

    public InMemoryCheckpointManager() { }

    [JsonConstructor]
    internal InMemoryCheckpointManager(Dictionary<string, RunCheckpointCache<Checkpoint>> store)
    {
        this._store = store;
    }

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

    internal bool HasCheckpoints(string runId) => this.GetRunStore(runId).HasCheckpoints;

    public bool TryGetLastCheckpoint(string runId, [NotNullWhen(true)] out CheckpointInfo? checkpoint)
        => this.GetRunStore(runId).TryGetLastCheckpointInfo(out checkpoint);
}
