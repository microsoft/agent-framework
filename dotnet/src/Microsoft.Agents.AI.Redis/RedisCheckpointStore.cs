// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Provides a Redis implementation of the <see cref="JsonCheckpointStore"/> abstract class.
/// </summary>
/// <typeparam name="T">The type of objects to store as checkpoint values.</typeparam>
[RequiresUnreferencedCode("The RedisCheckpointStore uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The RedisCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
public class RedisCheckpointStore<T> : JsonCheckpointStore, IDisposable
{
    private readonly IConnectionMultiplexer _connectionMultiplexer;
    private readonly IDatabase _database;
    private readonly RedisCheckpointStoreOptions _options;
    private readonly bool _ownsConnection;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="RedisCheckpointStore{T}"/> class using a Redis connection string.
    /// </summary>
    /// <param name="connectionString">The Redis connection string (e.g., "localhost:6379").</param>
    /// <param name="options">Optional configuration for the checkpoint store.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connectionString"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="connectionString"/> is empty or whitespace.</exception>
    public RedisCheckpointStore(string connectionString, RedisCheckpointStoreOptions? options = null)
    {
        this._connectionMultiplexer = ConnectionMultiplexer.Connect(Throw.IfNullOrWhitespace(connectionString));
        this._options = options ?? new RedisCheckpointStoreOptions();
        this._database = this._connectionMultiplexer.GetDatabase(this._options.Database);
        this._ownsConnection = true;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="RedisCheckpointStore{T}"/> class using an existing <see cref="IConnectionMultiplexer"/>.
    /// </summary>
    /// <param name="connectionMultiplexer">An existing Redis connection multiplexer.</param>
    /// <param name="options">Optional configuration for the checkpoint store.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="connectionMultiplexer"/> is null.</exception>
    public RedisCheckpointStore(IConnectionMultiplexer connectionMultiplexer, RedisCheckpointStoreOptions? options = null)
    {
        this._connectionMultiplexer = Throw.IfNull(connectionMultiplexer);
        this._options = options ?? new RedisCheckpointStoreOptions();
        this._database = this._connectionMultiplexer.GetDatabase(this._options.Database);
        this._ownsConnection = false;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="RedisCheckpointStore{T}"/> class using <see cref="ConfigurationOptions"/>.
    /// </summary>
    /// <param name="configuration">Redis configuration options.</param>
    /// <param name="options">Optional configuration for the checkpoint store.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="configuration"/> is null.</exception>
    public RedisCheckpointStore(ConfigurationOptions configuration, RedisCheckpointStoreOptions? options = null)
    {
        Throw.IfNull(configuration);
        this._connectionMultiplexer = ConnectionMultiplexer.Connect(configuration);
        this._options = options ?? new RedisCheckpointStoreOptions();
        this._database = this._connectionMultiplexer.GetDatabase(this._options.Database);
        this._ownsConnection = true;
    }

    /// <summary>
    /// Gets the key prefix used for Redis keys.
    /// </summary>
    public string KeyPrefix => this._options.KeyPrefix;

    /// <summary>
    /// Gets the Time-To-Live (TTL) configuration for checkpoints.
    /// </summary>
    public TimeSpan? TimeToLive => this._options.TimeToLive;

    /// <inheritdoc />
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string runId, JsonElement value, CheckpointInfo? parent = null)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(runId));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var checkpointId = Guid.NewGuid().ToString("N");
        var checkpointInfo = new CheckpointInfo(runId, checkpointId);
        var checkpointKey = this.GetCheckpointKey(runId, checkpointId);
        var indexKey = this.GetIndexKey(runId);

        var timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        var document = new RedisCheckpointDocument
        {
            RunId = runId,
            CheckpointId = checkpointId,
            Value = value.GetRawText(),
            ParentCheckpointId = parent?.CheckpointId,
            Timestamp = timestamp
        };

        var serializedDocument = JsonSerializer.Serialize(document, RedisJsonContext.Default.RedisCheckpointDocument);

        var transaction = this._database.CreateTransaction();
        _ = transaction.StringSetAsync(checkpointKey, serializedDocument);
        _ = transaction.SortedSetAddAsync(indexKey, checkpointId, timestamp);

        if (this._options.TimeToLive.HasValue)
        {
            _ = transaction.KeyExpireAsync(checkpointKey, this._options.TimeToLive.Value);
            _ = transaction.KeyExpireAsync(indexKey, this._options.TimeToLive.Value);
        }

        var committed = await transaction.ExecuteAsync().ConfigureAwait(false);
        if (!committed)
        {
            throw new InvalidOperationException($"Failed to create checkpoint '{checkpointId}' for run '{runId}'.");
        }

        return checkpointInfo;
    }

    /// <inheritdoc />
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string runId, CheckpointInfo key)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(runId));
        }

        if (key is null)
        {
            throw new ArgumentNullException(nameof(key));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var checkpointKey = this.GetCheckpointKey(runId, key.CheckpointId);
        var redisValue = await this._database.StringGetAsync(checkpointKey).ConfigureAwait(false);

        if (redisValue.IsNullOrEmpty)
        {
            throw new InvalidOperationException($"Checkpoint with ID '{key.CheckpointId}' for run '{runId}' not found.");
        }

        var document = JsonSerializer.Deserialize(redisValue.ToString(), RedisJsonContext.Default.RedisCheckpointDocument);
        if (document is null)
        {
            throw new InvalidOperationException($"Failed to deserialize checkpoint '{key.CheckpointId}' for run '{runId}'.");
        }

        using var jsonDocument = JsonDocument.Parse(document.Value);
        return jsonDocument.RootElement.Clone();
    }

    /// <inheritdoc />
    public override async ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string runId, CheckpointInfo? withParent = null)
    {
        if (string.IsNullOrWhiteSpace(runId))
        {
            throw new ArgumentException("Cannot be null or whitespace", nameof(runId));
        }

#pragma warning disable CA1513 // Use ObjectDisposedException.ThrowIf - not available on all target frameworks
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().FullName);
        }
#pragma warning restore CA1513

        var indexKey = this.GetIndexKey(runId);

        var checkpointIds = await this._database.SortedSetRangeByScoreAsync(indexKey).ConfigureAwait(false);

        if (checkpointIds.Length == 0)
        {
            return Enumerable.Empty<CheckpointInfo>();
        }

        if (withParent != null)
        {
            var results = new List<CheckpointInfo>();
            foreach (var checkpointId in checkpointIds)
            {
                var checkpointKey = this.GetCheckpointKey(runId, checkpointId.ToString());
                var redisValue = await this._database.StringGetAsync(checkpointKey).ConfigureAwait(false);

                if (!redisValue.IsNullOrEmpty)
                {
                    var document = JsonSerializer.Deserialize(redisValue.ToString(), RedisJsonContext.Default.RedisCheckpointDocument);
                    if (document?.ParentCheckpointId == withParent.CheckpointId)
                    {
                        results.Add(new CheckpointInfo(runId, checkpointId.ToString()));
                    }
                }
            }

            return results;
        }

        return checkpointIds.Select(id => new CheckpointInfo(runId, id.ToString()));
    }

    /// <inheritdoc />
    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// Releases the unmanaged resources used by the <see cref="RedisCheckpointStore{T}"/> and optionally releases the managed resources.
    /// </summary>
    /// <param name="disposing">true to release both managed and unmanaged resources; false to release only unmanaged resources.</param>
    protected virtual void Dispose(bool disposing)
    {
        if (!this._disposed)
        {
            if (disposing && this._ownsConnection)
            {
                this._connectionMultiplexer?.Dispose();
            }

            this._disposed = true;
        }
    }

    /// <summary>
    /// Gets the Redis key for a checkpoint.
    /// </summary>
    /// <param name="runId">The run identifier.</param>
    /// <param name="checkpointId">The checkpoint identifier.</param>
    /// <returns>The Redis key for the checkpoint.</returns>
    private string GetCheckpointKey(string runId, string checkpointId)
        => $"{this._options.KeyPrefix}:{runId}:{checkpointId}";

    /// <summary>
    /// Gets the Redis key for the run index.
    /// </summary>
    /// <param name="runId">The run identifier.</param>
    /// <returns>The Redis key for the index.</returns>
    private string GetIndexKey(string runId)
        => $"{this._options.KeyPrefix}:{runId}:_index";
}

/// <summary>
/// Provides a non-generic Redis implementation of the <see cref="JsonCheckpointStore"/> abstract class.
/// </summary>
[RequiresUnreferencedCode("The RedisCheckpointStore uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The RedisCheckpointStore uses JSON serialization which is incompatible with NativeAOT.")]
public sealed class RedisCheckpointStore : RedisCheckpointStore<JsonElement>
{
    /// <inheritdoc />
    public RedisCheckpointStore(string connectionString, RedisCheckpointStoreOptions? options = null)
        : base(connectionString, options)
    {
    }

    /// <inheritdoc />
    public RedisCheckpointStore(IConnectionMultiplexer connectionMultiplexer, RedisCheckpointStoreOptions? options = null)
        : base(connectionMultiplexer, options)
    {
    }

    /// <inheritdoc />
    public RedisCheckpointStore(ConfigurationOptions configuration, RedisCheckpointStoreOptions? options = null)
        : base(configuration, options)
    {
    }
}

/// <summary>
/// Represents a checkpoint document stored in Redis.
/// </summary>
internal sealed class RedisCheckpointDocument
{
    /// <summary>
    /// Gets or sets the run identifier.
    /// </summary>
    public string RunId { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the checkpoint identifier.
    /// </summary>
    public string CheckpointId { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the JSON value of the checkpoint.
    /// </summary>
    public string Value { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the parent checkpoint identifier.
    /// </summary>
    public string? ParentCheckpointId { get; set; }

    /// <summary>
    /// Gets or sets the Unix timestamp when the checkpoint was created.
    /// </summary>
    public long Timestamp { get; set; }
}

/// <summary>
/// JSON serialization context for Redis checkpoint documents.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(RedisCheckpointDocument))]
internal sealed partial class RedisJsonContext : JsonSerializerContext
{
}
