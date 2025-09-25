// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// An abstract base class for checkpoint stores that use JSON for serialization.
/// </summary>
public abstract class JsonCheckpointStore : ICheckpointStore<JsonElement>
{
    /// <summary>
    /// A default TypeInfo for serializing the <see cref="CheckpointInfo"/> type, if needed.
    /// </summary>
    protected static JsonTypeInfo<CheckpointInfo> KeyTypeInfo => WorkflowsJsonUtilities.JsonContext.Default.CheckpointInfo;

    /// <inheritdoc/>
    public abstract ValueTask<CheckpointInfo> CreateCheckpointAsync(string runId, JsonElement value, CheckpointInfo? parent = null);

    /// <inheritdoc/>
    public abstract ValueTask<JsonElement> RetrieveCheckpointAsync(string runId, CheckpointInfo key);

    /// <inheritdoc/>
    public abstract ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string runId, CheckpointInfo? withParent = null);
}
