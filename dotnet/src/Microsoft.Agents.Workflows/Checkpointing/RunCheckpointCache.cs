// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class RunCheckpointCache<TStoreObject>
{
    private readonly HashSet<CheckpointInfo> _checkpointIndex = [];
    private readonly Dictionary<CheckpointInfo, TStoreObject> _cache = [];

    public IEnumerable<CheckpointInfo> Index => this._checkpointIndex;

    public bool IsInIndex(CheckpointInfo key) => this._checkpointIndex.Contains(key);
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
        bool added = this._checkpointIndex.Add(key);
        if (added)
        {
            this._cache[key] = value;
        }

        return added;
    }
}
