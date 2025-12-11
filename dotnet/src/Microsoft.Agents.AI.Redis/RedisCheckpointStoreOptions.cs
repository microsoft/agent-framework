// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Configuration options for <see cref="RedisCheckpointStore"/>.
/// </summary>
public sealed class RedisCheckpointStoreOptions
{
    /// <summary>
    /// Gets or sets the key prefix for Redis keys.
    /// Default: "checkpoint".
    /// </summary>
    /// <remarks>
    /// The full key format is: {KeyPrefix}:{runId}:{checkpointId}.
    /// The index key format is: {KeyPrefix}:{runId}:_index.
    /// </remarks>
    public string KeyPrefix { get; set; } = "checkpoint";

    /// <summary>
    /// Gets or sets the Time-To-Live (TTL) for checkpoints.
    /// </summary>
    /// <remarks>
    /// When set, checkpoints will automatically expire after this duration.
    /// When null, checkpoints do not expire.
    /// </remarks>
    public TimeSpan? TimeToLive { get; set; }

    /// <summary>
    /// Gets or sets the Redis database index.
    /// Default: -1 (use the default database).
    /// </summary>
    public int Database { get; set; } = -1;
}
