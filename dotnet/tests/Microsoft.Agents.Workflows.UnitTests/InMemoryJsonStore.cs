// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.UnitTests;

internal sealed class InMemoryJsonStore : JsonCheckpointStore
{
    private readonly Dictionary<string, RunCheckpointCache<JsonElement>> _store = [];

    private RunCheckpointCache<JsonElement> EnsureRunStore(string runId)
    {
        if (!this._store.TryGetValue(runId, out RunCheckpointCache<JsonElement>? runStore))
        {
            runStore = this._store[runId] = new();
        }

        return runStore;
    }

    public override ValueTask<CheckpointInfo> CreateCheckpointAsync(string runId, JsonElement value, CheckpointInfo? parent = null)
    {
        return new(this.EnsureRunStore(runId).Add(runId, value));
    }

    public override ValueTask<JsonElement> RetrieveCheckpointAsync(string runId, CheckpointInfo key)
    {
        if (!this.EnsureRunStore(runId).TryGet(key, out JsonElement result))
        {
            throw new KeyNotFoundException("Could not retrieve checkpoint with id {key.CheckpointId} for run {runId}");
        }

        return new(result);
    }

    public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string runId, CheckpointInfo? withParent = null)
    {
        return new(this.EnsureRunStore(runId).Index);
    }
}
