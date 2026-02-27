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
    [JsonInclude]
    internal Dictionary<string, SessionCheckpointCache<Checkpoint>> Store { get; } = [];

    public InMemoryCheckpointManager() { }

    [JsonConstructor]
    internal InMemoryCheckpointManager(Dictionary<string, SessionCheckpointCache<Checkpoint>> store)
    {
        this.Store = store;
    }

    private SessionCheckpointCache<Checkpoint> GetSessionStore(string sessionId)
    {
        if (!this.Store.TryGetValue(sessionId, out SessionCheckpointCache<Checkpoint>? sessionStore))
        {
            sessionStore = this.Store[sessionId] = new();
        }

        return sessionStore;
    }

    public ValueTask<CheckpointInfo> CommitCheckpointAsync(string sessionId, Checkpoint checkpoint)
    {
        SessionCheckpointCache<Checkpoint> sessionStore = this.GetSessionStore(sessionId);

        CheckpointInfo key;
        do
        {
            key = new(sessionId);
        } while (!sessionStore.Add(key, checkpoint));

        return new(key);
    }

    public ValueTask<Checkpoint> LookupCheckpointAsync(string sessionId, CheckpointInfo checkpointInfo)
    {
        if (!this.GetSessionStore(sessionId).TryGet(checkpointInfo, out Checkpoint? value))
        {
            throw new KeyNotFoundException($"Could not retrieve checkpoint with id {checkpointInfo.CheckpointId} for session {sessionId}");
        }

        return new(value);
    }

    internal bool HasCheckpoints(string sessionId) => this.GetSessionStore(sessionId).HasCheckpoints;

    public bool TryGetLastCheckpoint(string sessionId, [NotNullWhen(true)] out CheckpointInfo? checkpoint)
        => this.GetSessionStore(sessionId).TryGetLastCheckpointInfo(out checkpoint);

    public ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
        => new(this.GetSessionStore(sessionId).CheckpointIndex.AsReadOnly());
}
