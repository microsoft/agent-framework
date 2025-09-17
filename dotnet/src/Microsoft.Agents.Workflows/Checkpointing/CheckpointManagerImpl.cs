// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

internal sealed class CheckpointManagerImpl<TStoreObject> : ICheckpointManager
{
    private readonly IWireMarshaller<TStoreObject> _marshaller;
    private readonly ICheckpointStore<TStoreObject> _store;

    public CheckpointManagerImpl(IWireMarshaller<TStoreObject> marshaller, ICheckpointStore<TStoreObject> store)
    {
        this._marshaller = marshaller;
        this._store = store;
    }

    public ValueTask<CheckpointInfo> CommitCheckpointAsync(string runId, Checkpoint checkpoint)
    {
        TStoreObject storeObject = this._marshaller.Marshal(checkpoint);

        return this._store.CreateCheckpointAsync(runId, storeObject, checkpoint.Parent);
    }

    public async ValueTask<Checkpoint> LookupCheckpointAsync(string runId, CheckpointInfo checkpointInfo)
    {
        TStoreObject result = await this._store.RetrieveCheckpointAsync(runId, checkpointInfo).ConfigureAwait(false);
        return this._marshaller.Marshal<Checkpoint>(result);
    }
}
