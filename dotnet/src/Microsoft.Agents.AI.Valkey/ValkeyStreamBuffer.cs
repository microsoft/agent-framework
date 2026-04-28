// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey;

/// <summary>
/// Provides a resumable streaming buffer backed by Valkey Streams.
/// </summary>
/// <remarks>
/// <para>
/// Writes <see cref="AgentResponseUpdate"/> chunks to a Valkey Stream via XADD and supports
/// replaying missed entries via XRANGE from a given entry ID, enabling clients to reconnect
/// mid-stream without data loss.
/// </para>
/// <para>
/// Each stream is keyed by a caller-provided response ID (typically session + response scoped).
/// The Valkey Stream entry ID serves as the continuation token for resumption.
/// </para>
/// <para>
/// <strong>Server requirements:</strong> Any Valkey (or Redis OSS) server. Uses core Stream
/// commands only (XADD, XRANGE, XLEN, XTRIM, DEL) — no modules required.
/// </para>
/// <para>
/// <strong>Data retention:</strong> Streams are bounded by <see cref="MaxLength"/> via XTRIM
/// approximate trimming. Callers can also explicitly delete streams via <see cref="DeleteStreamAsync"/>.
/// </para>
/// <para>
/// <strong>Security considerations:</strong>
/// <list type="bullet">
/// <item><description><strong>PII and sensitive data:</strong> Streamed response chunks may contain
/// PII. Ensure the Valkey server is configured with appropriate access controls and TLS.</description></item>
/// </list>
/// </para>
/// </remarks>
[RequiresUnreferencedCode("The ValkeyStreamBuffer uses JSON serialization which is incompatible with trimming.")]
[RequiresDynamicCode("The ValkeyStreamBuffer uses JSON serialization which is incompatible with NativeAOT.")]
public sealed class ValkeyStreamBuffer : IAsyncDisposable
{
    private const string ContentField = "content";

    private readonly IConnectionMultiplexer _connection;
    private readonly bool _ownsConnection;
    private readonly string _keyPrefix;
    private readonly ILogger<ValkeyStreamBuffer>? _logger;
    private volatile bool _disposed;

    /// <summary>
    /// Gets or sets the maximum number of entries to retain per stream.
    /// When set, XTRIM with approximate trimming (~) is applied after each XADD,
    /// which may retain slightly more entries than the specified limit for performance.
    /// Null means no trimming.
    /// </summary>
    public int? MaxLength { get; set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyStreamBuffer"/> class using a connection string.
    /// </summary>
    /// <param name="connectionString">The Valkey connection string (e.g., "localhost:6379").</param>
    /// <param name="keyPrefix">Prefix for Valkey stream keys. Defaults to "agent_stream".</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    /// <remarks>
    /// This constructor opens a synchronous connection to Valkey. For ASP.NET Core / DI scenarios,
    /// prefer the <see cref="IConnectionMultiplexer"/> overload with a pre-connected instance to
    /// avoid blocking the thread pool.
    /// </remarks>
    public ValkeyStreamBuffer(
        string connectionString,
        string keyPrefix = "agent_stream",
        ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNullOrWhitespace(connectionString);
        this._connection = ConnectionMultiplexer.Connect(connectionString);
        this._ownsConnection = true;
        this._keyPrefix = keyPrefix;
        this._logger = loggerFactory?.CreateLogger<ValkeyStreamBuffer>();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyStreamBuffer"/> class using an existing connection.
    /// </summary>
    /// <param name="connection">An existing <see cref="IConnectionMultiplexer"/> instance.</param>
    /// <param name="keyPrefix">Prefix for Valkey stream keys. Defaults to "agent_stream".</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public ValkeyStreamBuffer(
        IConnectionMultiplexer connection,
        string keyPrefix = "agent_stream",
        ILoggerFactory? loggerFactory = null)
    {
        this._connection = Throw.IfNull(connection);
        this._ownsConnection = false;
        this._keyPrefix = keyPrefix;
        this._logger = loggerFactory?.CreateLogger<ValkeyStreamBuffer>();
    }

    /// <summary>
    /// Appends an <see cref="AgentResponseUpdate"/> to the stream for the given response ID.
    /// </summary>
    /// <param name="responseId">The unique identifier for this streaming response.</param>
    /// <param name="update">The response update to append.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The Valkey Stream entry ID, usable as a continuation token for resumption.</returns>
    /// <exception cref="ObjectDisposedException">The buffer has been disposed.</exception>
    /// <exception cref="ArgumentNullException"><paramref name="responseId"/> or <paramref name="update"/> is null.</exception>
    public async Task<string> AppendAsync(string responseId, AgentResponseUpdate update, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(responseId);
        Throw.IfNull(update);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var db = this._connection.GetDatabase();
        var key = this.BuildKey(responseId);
        var serialized = JsonSerializer.Serialize(update);

        var entries = new NameValueEntry[] { new(ContentField, serialized) };
        var entryId = await db.StreamAddAsync(
            key,
            entries,
            maxLength: this.MaxLength.HasValue ? this.MaxLength.Value : null,
            useApproximateMaxLength: this.MaxLength.HasValue).ConfigureAwait(false);

        this._logger?.LogDebug(
            "ValkeyStreamBuffer: Appended entry {EntryId} to stream for response.",
            entryId);

        return entryId.ToString();
    }

    /// <summary>
    /// Reads all entries from the stream for the given response ID, starting after the specified entry ID.
    /// </summary>
    /// <param name="responseId">The unique identifier for the streaming response.</param>
    /// <param name="afterEntryId">
    /// The entry ID to start reading after (exclusive). Use <c>"0-0"</c> to read from the beginning,
    /// or a previously received entry ID to resume from that point.
    /// </param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An async enumerable of tuples containing the entry ID and the deserialized <see cref="AgentResponseUpdate"/>.</returns>
    /// <exception cref="ObjectDisposedException">The buffer has been disposed.</exception>
    public async IAsyncEnumerable<(string EntryId, AgentResponseUpdate Update)> ReadAsync(
        string responseId,
        string afterEntryId = "0-0",
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(responseId);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var db = this._connection.GetDatabase();
        var key = this.BuildKey(responseId);

        var entries = await db.StreamRangeAsync(
            key,
            minId: afterEntryId == "0-0" ? "-" : $"({afterEntryId}",
            maxId: "+").ConfigureAwait(false);

        if (entries is null || entries.Length == 0)
        {
            yield break;
        }

        foreach (var entry in entries)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var contentValue = GetContentValue(entry);
            if (contentValue is null)
            {
                continue;
            }

            AgentResponseUpdate? update;
            try
            {
                update = JsonSerializer.Deserialize<AgentResponseUpdate>(contentValue);
            }
            catch (JsonException ex)
            {
                this._logger?.LogWarning(ex, "ValkeyStreamBuffer: Skipping malformed entry {EntryId}.", entry.Id);
                continue;
            }

            if (update is not null)
            {
                yield return (entry.Id.ToString(), update);
            }
        }
    }

    /// <summary>
    /// Gets the number of entries in the stream for the given response ID.
    /// </summary>
    /// <param name="responseId">The unique identifier for the streaming response.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The number of entries in the stream, or 0 if the stream does not exist.</returns>
    public async Task<long> GetEntryCountAsync(string responseId, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(responseId);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var db = this._connection.GetDatabase();
        var key = this.BuildKey(responseId);
        return await db.StreamLengthAsync(key).ConfigureAwait(false);
    }

    /// <summary>
    /// Deletes the stream for the given response ID.
    /// </summary>
    /// <param name="responseId">The unique identifier for the streaming response.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>True if the stream was deleted, false if it did not exist.</returns>
    public async Task<bool> DeleteStreamAsync(string responseId, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(responseId);
        this.ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();

        var db = this._connection.GetDatabase();
        var key = this.BuildKey(responseId);
        return await db.KeyDeleteAsync(key).ConfigureAwait(false);
    }

    private string BuildKey(string responseId) => $"{this._keyPrefix}:{responseId}";

    private static string? GetContentValue(StreamEntry entry)
    {
        foreach (var nv in entry.Values)
        {
            if (nv.Name == ContentField && !nv.Value.IsNullOrEmpty)
            {
                return nv.Value.ToString();
            }
        }

        return null;
    }

    private void ThrowIfDisposed()
    {
#if NET8_0_OR_GREATER
        ObjectDisposedException.ThrowIf(this._disposed, this);
#else
        if (this._disposed)
        {
            throw new ObjectDisposedException(this.GetType().Name);
        }
#endif
    }

    /// <inheritdoc />
    public async ValueTask DisposeAsync()
    {
        if (this._disposed)
        {
            return;
        }

        this._disposed = true;

        if (this._ownsConnection)
        {
            await this._connection.CloseAsync().ConfigureAwait(false);
            this._connection.Dispose();
        }
    }
}
