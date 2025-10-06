// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal sealed class RunCheckpointCache<TStoreObject>
{
    private readonly List<CheckpointInfo> _checkpointIndex = [];
    private readonly Dictionary<CheckpointInfo, TStoreObject> _cache = [];

    public RunCheckpointCache() { }

    [JsonConstructor]
    internal RunCheckpointCache(List<CheckpointInfo> checkpointIndex, Dictionary<CheckpointInfo, TStoreObject> cache)
    {
        this._checkpointIndex = checkpointIndex;
        this._cache = cache;
    }

    [JsonIgnore]
    public IEnumerable<CheckpointInfo> Index => this._checkpointIndex;

    public bool IsInIndex(CheckpointInfo key) => this._cache.ContainsKey(key);
    public bool TryGet(CheckpointInfo key, [MaybeNullWhen(false)] out TStoreObject value) => this._cache.TryGetValue(key, out value);

    public CheckpointInfo Add(string runId, TStoreObject value)
    {
        CheckpointInfo key;

        do
        {
            key = new(runId);
        } while (!this.Add(key, value));

        return key;
    }

    public bool Add(CheckpointInfo key, TStoreObject value)
    {
        if (this.IsInIndex(key))
        {
            return false;
        }

        this._cache[key] = value;
        this._checkpointIndex.Add(key);
        return true;
    }

    [JsonIgnore]
    public bool HasCheckpoints => this._checkpointIndex.Count > 0;
    public bool TryGetLastCheckpointInfo([NotNullWhen(true)] out CheckpointInfo? checkpointInfo)
    {
        if (this.HasCheckpoints)
        {
            checkpointInfo = this._checkpointIndex[this._checkpointIndex.Count - 1];
            return true;
        }
        checkpointInfo = default;
        return false;
    }
}
