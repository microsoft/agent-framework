// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using Valkey.Glide;

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
/// <strong>Data retention:</strong> Streams are bounded by <see cref="ValkeyStreamBufferOptions.MaxLength"/> via XTRIM
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
public sealed class ValkeyStreamBuffer
{
    private const string ContentField = "content";

    private readonly IConnectionMultiplexer _connection;
    private readonly string _keyPrefix;
    private readonly int? _maxLength;
    private readonly JsonSerializerOptions _jsonSerializerOptions;
    private readonly ILogger<ValkeyStreamBuffer>? _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="ValkeyStreamBuffer"/> class.
    /// </summary>
    /// <param name="connection">An existing <see cref="IConnectionMultiplexer"/> instance.</param>
    /// <param name="options">Optional configuration options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public ValkeyStreamBuffer(
        IConnectionMultiplexer connection,
        ValkeyStreamBufferOptions? options = null,
        ILoggerFactory? loggerFactory = null)
    {
        this._connection = Throw.IfNull(connection);
        this._keyPrefix = options?.KeyPrefix ?? "agent_stream";
        this._maxLength = options?.MaxLength;
        this._jsonSerializerOptions = options?.JsonSerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
        this._logger = loggerFactory?.CreateLogger<ValkeyStreamBuffer>();
    }

    /// <summary>
    /// Appends an <see cref="AgentResponseUpdate"/> to the stream for the given response ID.
    /// </summary>
    /// <param name="responseId">The unique identifier for this streaming response.</param>
    /// <param name="update">The response update to append.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The Valkey Stream entry ID, usable as a continuation token for resumption.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="responseId"/> or <paramref name="update"/> is null.</exception>
    public async Task<string> AppendAsync(string responseId, AgentResponseUpdate update, CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(responseId);
        Throw.IfNull(update);
        cancellationToken.ThrowIfCancellationRequested();

        var db = this._connection.GetDatabase();
        var key = this.BuildKey(responseId);
        var serialized = JsonSerializer.Serialize(update, (JsonTypeInfo<AgentResponseUpdate>)this._jsonSerializerOptions.GetTypeInfo(typeof(AgentResponseUpdate)));

        var entries = new NameValueEntry[] { new(ContentField, serialized) };
        var entryId = await db.StreamAddAsync(
            key,
            entries,
            maxLength: this._maxLength,
            useApproximateMaxLength: this._maxLength.HasValue).ConfigureAwait(false);

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
    public async IAsyncEnumerable<(string EntryId, AgentResponseUpdate Update)> ReadAsync(
        string responseId,
        string afterEntryId = "0-0",
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNullOrWhitespace(responseId);
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
                update = JsonSerializer.Deserialize(contentValue, (JsonTypeInfo<AgentResponseUpdate>)this._jsonSerializerOptions.GetTypeInfo(typeof(AgentResponseUpdate)));
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
}
