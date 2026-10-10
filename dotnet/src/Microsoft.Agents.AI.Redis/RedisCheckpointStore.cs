// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Provides a Redis implementation of the <see cref="JsonCheckpointStore"/> abstract class, built on StackExchange.Redis.
/// </summary>
/// <remarks>
/// <para>
/// For each session the store keeps a sorted set of checkpoint ids scored by a per-session commit counter, a hash with the
/// checkpoint JSON (stored verbatim) and a hash with the parent checkpoint ids. A Lua script writes all of them in one atomic
/// step, so <see cref="RetrieveIndexAsync"/> always returns checkpoints in commit order, also when several processes write
/// to the same session. All keys of a session share the hash tag <c>{sessionId}</c>, so the store also works with Redis Cluster.
/// </para>
/// <para>
/// The store does not own the <see cref="IConnectionMultiplexer"/>; the application creates it, shares it and disposes it.
/// The store holds no other resources and is safe to use from multiple threads.
/// </para>
/// <para>
/// <strong>Data retention:</strong> Without <see cref="RedisCheckpointStoreOptions.TimeToLive"/> checkpoints are kept until the
/// keys are deleted, since the checkpoint store contract has no delete operation.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> Checkpoints contain the workflow state, which may include PII and sensitive
/// conversation content. Configure the Redis server with appropriate access controls and encryption in transit (TLS).
/// Agent Framework does not validate checkpoints loaded from the store, so if the store is compromised, adversarial state could
/// be injected into a resumed workflow.
/// </para>
/// </remarks>
public sealed class RedisCheckpointStore : JsonCheckpointStore
{
    // KEYS: sequence, index, data, parents. ARGV: checkpoint id, payload, parent id ('' for none), time to live in ms (0 for none).
    private const string CreateCheckpointScript = """
        local seq = redis.call('INCR', KEYS[1])
        redis.call('ZADD', KEYS[2], seq, ARGV[1])
        redis.call('HSET', KEYS[3], ARGV[1], ARGV[2])
        if ARGV[3] ~= '' then
          redis.call('HSET', KEYS[4], ARGV[1], ARGV[3])
        end
        local ttl = tonumber(ARGV[4])
        if ttl > 0 then
          for i = 1, 4 do
            redis.call('PEXPIRE', KEYS[i], ttl)
          end
        end
        return seq
        """;

    private readonly IConnectionMultiplexer _connection;
    private readonly int _database;
    private readonly string _keyPrefix;
    private readonly long _timeToLiveMilliseconds;

    /// <summary>
    /// Initializes a new instance of the <see cref="RedisCheckpointStore"/> class.
    /// </summary>
    /// <param name="connection">The Redis connection to use. The store does not dispose it.</param>
    /// <param name="options">Optional configuration options.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connection"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <see cref="RedisCheckpointStoreOptions.KeyPrefix"/> is null or whitespace.</exception>
    /// <exception cref="ArgumentOutOfRangeException">Thrown when <see cref="RedisCheckpointStoreOptions.TimeToLive"/> is not positive.</exception>
    public RedisCheckpointStore(IConnectionMultiplexer connection, RedisCheckpointStoreOptions? options = null)
    {
        this._connection = Throw.IfNull(connection);
        this._database = options?.Database ?? -1;
        this._keyPrefix = Throw.IfNullOrWhitespace(options?.KeyPrefix ?? "checkpoints", nameof(options.KeyPrefix));

        if (options?.TimeToLive is TimeSpan timeToLive)
        {
            if (timeToLive <= TimeSpan.Zero)
            {
                throw new ArgumentOutOfRangeException(nameof(options), timeToLive, "TimeToLive must be greater than zero.");
            }

            this._timeToLiveMilliseconds = (long)Math.Ceiling(timeToLive.TotalMilliseconds);
        }
    }

    /// <inheritdoc />
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string sessionId, JsonElement value, CheckpointInfo? parent = null)
    {
        SessionKeys keys = this.GetSessionKeys(sessionId);
        CheckpointInfo checkpoint = new(sessionId, Guid.NewGuid().ToString("N"));

        await this.GetDatabase().ScriptEvaluateAsync(
            CreateCheckpointScript,
            [keys.Sequence, keys.Index, keys.Data, keys.Parents],
            [checkpoint.CheckpointId, value.GetRawText(), parent?.CheckpointId ?? string.Empty, this._timeToLiveMilliseconds]).ConfigureAwait(false);

        return checkpoint;
    }

    /// <inheritdoc />
    /// <exception cref="KeyNotFoundException">Thrown when the checkpoint does not exist or has expired.</exception>
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
    {
        Throw.IfNull(key);
        SessionKeys keys = this.GetSessionKeys(sessionId);

        RedisValue payload = await this.GetDatabase().HashGetAsync(keys.Data, key.CheckpointId).ConfigureAwait(false);
        if (payload.IsNull)
        {
            throw new KeyNotFoundException($"Checkpoint '{key.CheckpointId}' for session '{sessionId}' was not found.");
        }

        using JsonDocument document = JsonDocument.Parse((byte[])payload!);
        return document.RootElement.Clone();
    }

    /// <inheritdoc />
    public override async ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
    {
        SessionKeys keys = this.GetSessionKeys(sessionId);
        IDatabase database = this.GetDatabase();

        RedisValue[] checkpointIds = await database.SortedSetRangeByRankAsync(keys.Index).ConfigureAwait(false);
        if (withParent is not null && checkpointIds.Length > 0)
        {
            RedisValue[] parentIds = await database.HashGetAsync(keys.Parents, checkpointIds).ConfigureAwait(false);
            checkpointIds = checkpointIds.Where((_, i) => parentIds[i] == withParent.CheckpointId).ToArray();
        }

        return checkpointIds.Select(id => new CheckpointInfo(sessionId, id.ToString())).ToArray();
    }

    private IDatabase GetDatabase() => this._connection.GetDatabase(this._database);

    private SessionKeys GetSessionKeys(string sessionId)
    {
        Throw.IfNullOrWhitespace(sessionId);

        string root = $"{this._keyPrefix}:{{{sessionId}}}";
        return new SessionKeys($"{root}:seq", $"{root}:index", $"{root}:data", $"{root}:parents");
    }

    private readonly record struct SessionKeys(RedisKey Sequence, RedisKey Index, RedisKey Data, RedisKey Parents);
}
