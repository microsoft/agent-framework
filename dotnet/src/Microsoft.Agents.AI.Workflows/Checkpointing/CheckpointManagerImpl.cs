// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal sealed class CheckpointManagerImpl<TStoreObject> : ICheckpointManager
{
    private readonly IWireMarshaller<TStoreObject> _marshaller;
    private readonly ICheckpointStore<TStoreObject> _store;

    public CheckpointManagerImpl(IWireMarshaller<TStoreObject> marshaller, ICheckpointStore<TStoreObject> store)
    {
        this._marshaller = marshaller;
        this._store = store;
    }

    public ValueTask<CheckpointInfo> CommitCheckpointAsync(string sessionId, Checkpoint checkpoint)
    {
        TStoreObject storeObject = this._marshaller.Marshal(checkpoint);

        return this._store.CreateCheckpointAsync(sessionId, storeObject, checkpoint.Parent);
    }

    public async ValueTask<Checkpoint> LookupCheckpointAsync(string sessionId, CheckpointInfo checkpointInfo)
    {
        TStoreObject result = await this._store.RetrieveCheckpointAsync(sessionId, checkpointInfo).ConfigureAwait(false);
        return this._marshaller.Marshal<Checkpoint>(result);
    }

    public ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
        => this._store.RetrieveIndexAsync(sessionId, withParent);
}
