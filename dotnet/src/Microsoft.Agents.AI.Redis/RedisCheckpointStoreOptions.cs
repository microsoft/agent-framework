// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Options for configuring <see cref="RedisCheckpointStore"/>.
/// </summary>
public sealed class RedisCheckpointStoreOptions
{
    /// <summary>
    /// Gets or sets the prefix for all Redis keys written by the store. Defaults to "checkpoints".
    /// </summary>
    /// <remarks>
    /// The keys of a session are <c>{KeyPrefix}:{sessionId}:index</c>, <c>:data</c>, <c>:parents</c> and <c>:seq</c>,
    /// with the session id wrapped in braces so that all keys of a session share a Redis Cluster hash tag.
    /// </remarks>
    public string KeyPrefix { get; set; } = "checkpoints";

    /// <summary>
    /// Gets or sets the Redis database number. Defaults to -1, the default database of the connection.
    /// </summary>
    public int Database { get; set; } = -1;

    /// <summary>
    /// Gets or sets how long the checkpoints of a session are kept after its most recent checkpoint was created.
    /// Null (the default) keeps checkpoints until they are deleted; otherwise the value must be greater than zero.
    /// </summary>
    /// <remarks>
    /// Every new checkpoint resets the expiration of all keys of its session, so a session expires as a whole.
    /// </remarks>
    public TimeSpan? TimeToLive { get; set; }
}
