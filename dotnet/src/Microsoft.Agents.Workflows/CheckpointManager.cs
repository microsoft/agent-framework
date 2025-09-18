// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// A manager for storing and retrieving workflow execution checkpoints.
/// </summary>
public sealed class CheckpointManager : ICheckpointManager
{
    private readonly ICheckpointManager _impl;

    private static CheckpointManagerImpl<TStoreObject> CreateImpl<TStoreObject>(
        IWireMarshaller<TStoreObject> marshaller,
        ICheckpointStore<TStoreObject> store)
    {
        return new CheckpointManagerImpl<TStoreObject>(marshaller, store);
    }

    private CheckpointManager(ICheckpointManager impl)
    {
        this._impl = impl;
    }

    /// <summary>
    /// Creates a new instance of <see cref="ICheckpointManager"/> that uses the specified marshaller and store.
    /// </summary>
    /// <returns></returns>
    public static CheckpointManager CreateInMemory() => new(new InMemoryCheckpointManager());

    /// <summary>
    /// Gets the default in-memory checkpoint manager instance.
    /// </summary>
    public static CheckpointManager Default { get; } = CreateInMemory();

    /// <summary>
    /// Creates a new instance of the CheckpointManager that uses JSON serialization for checkpoint data.
    /// </summary>
    /// <param name="store">The checkpoint store to use for persisting and retrieving checkpoint data as JSON elements. Cannot be null.</param>
    /// <param name="customOptions">Optional custom JSON serializer options to use for serialization and deserialization. Must be provided if
    /// using custom types in messages or state.</param>
    /// <returns>A CheckpointManager instance configured to serialize checkpoint data as JSON.</returns>
    public static CheckpointManager CreateJson(ICheckpointStore<JsonElement> store, JsonSerializerOptions? customOptions = null)
    {
        JsonMarshaller marshaller = new(customOptions);
        return new(CreateImpl(marshaller, store));
    }

    ValueTask<CheckpointInfo> ICheckpointManager.CommitCheckpointAsync(string runId, Checkpoint checkpoint)
        => this._impl.CommitCheckpointAsync(runId, checkpoint);

    ValueTask<Checkpoint> ICheckpointManager.LookupCheckpointAsync(string runId, CheckpointInfo checkpointInfo)
        => this._impl.LookupCheckpointAsync(runId, checkpointInfo);
}
