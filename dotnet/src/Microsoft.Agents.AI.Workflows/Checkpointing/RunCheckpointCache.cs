// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal sealed class RunCheckpointCache<TStoreObject>
{
    [JsonInclude]
    internal List<CheckpointInfo> CheckpointIndex { get; } = [];

    [JsonInclude]
    internal Dictionary<CheckpointInfo, TStoreObject> Cache { get; } = [];

    public RunCheckpointCache() { }

    [JsonConstructor]
    internal RunCheckpointCache(List<CheckpointInfo> checkpointIndex, Dictionary<CheckpointInfo, TStoreObject> cache)
    {
        this.CheckpointIndex = checkpointIndex;
        this.Cache = cache;
    }

    [JsonIgnore]
    public IEnumerable<CheckpointInfo> Index => this.CheckpointIndex;

    public bool IsInIndex(CheckpointInfo key) => this.Cache.ContainsKey(key);
    public bool TryGet(CheckpointInfo key, [MaybeNullWhen(false)] out TStoreObject value) => this.Cache.TryGetValue(key, out value);

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

        this.Cache[key] = value;
        this.CheckpointIndex.Add(key);
        return true;
    }

    [JsonIgnore]
    public bool HasCheckpoints => this.CheckpointIndex.Count > 0;
    public bool TryGetLastCheckpointInfo([NotNullWhen(true)] out CheckpointInfo? checkpointInfo)
    {
        if (this.HasCheckpoints)
        {
            checkpointInfo = this.CheckpointIndex[this.CheckpointIndex.Count - 1];
            return true;
        }
        checkpointInfo = default;
        return false;
    }
}
