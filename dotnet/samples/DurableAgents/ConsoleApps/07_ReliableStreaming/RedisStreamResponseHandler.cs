// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using StackExchange.Redis;

namespace ReliableStreaming;

/// <summary>
/// Represents a chunk of data read from a Redis stream.
/// </summary>
/// <param name="EntryId">The Redis stream entry ID (can be used as a cursor for resumption).</param>
/// <param name="Text">The text content of the chunk, or null if this is a completion/error marker.</param>
/// <param name="IsDone">True if this chunk marks the end of the stream.</param>
/// <param name="Error">An error message if something went wrong, or null otherwise.</param>
public readonly record struct StreamChunk(string EntryId, string? Text, bool IsDone, string? Error);

/// <summary>
/// An implementation of <see cref="IAgentResponseHandler"/> that publishes agent response updates
/// to Redis Streams for reliable delivery. This enables clients to disconnect and reconnect
/// to ongoing agent responses without losing messages.
/// </summary>
/// <remarks>
/// <para>
/// Redis Streams provide a durable, append-only log that supports consumer groups and message
/// acknowledgment. This implementation uses auto-generated IDs (which are timestamp-based)
/// as sequence numbers, allowing clients to resume from any point in the stream.
/// </para>
/// <para>
/// Each agent session gets its own Redis Stream, keyed by session ID. The stream entries
/// contain text chunks extracted from <see cref="AgentRunResponseUpdate"/> objects.
/// </para>
/// </remarks>
public sealed class RedisStreamResponseHandler : IAgentResponseHandler
{
    private const int MaxEmptyReads = 300; // 5 minutes at 1 second intervals
    private const int PollIntervalMs = 1000;

    private readonly IConnectionMultiplexer _redis;
    private readonly TimeSpan _streamTtl;

    /// <summary>
    /// Initializes a new instance of the <see cref="RedisStreamResponseHandler" /> class.
    /// </summary>
    /// <param name="redis">The Redis connection multiplexer.</param>
    /// <param name="streamTtl">The time-to-live for stream entries. Streams will expire after this duration of inactivity.</param>
    public RedisStreamResponseHandler(IConnectionMultiplexer redis, TimeSpan streamTtl)
    {
        this._redis = redis;
        this._streamTtl = streamTtl;
    }

    /// <inheritdoc/>
    public async ValueTask OnStreamingResponseUpdateAsync(
        IAsyncEnumerable<AgentRunResponseUpdate> messageStream,
        CancellationToken cancellationToken)
    {
        // Get the current session ID from the DurableAgentContext
        // This is set by the AgentEntity before invoking the response handler
        DurableAgentContext? context = DurableAgentContext.Current;
        if (context is null)
        {
            throw new InvalidOperationException(
                "DurableAgentContext.Current is not set. This handler must be used within a durable agent context.");
        }

        // Get conversation ID from the current thread context, which is only available in the context of
        // a durable agent execution.
        string conversationId = context.CurrentThread.GetService<AgentThreadMetadata>()?.ConversationId
            ?? throw new InvalidOperationException("Unable to determine conversation ID from the current thread.");
        string streamKey = GetStreamKey(conversationId);

        IDatabase db = this._redis.GetDatabase();
        int sequenceNumber = 0;

        await foreach (AgentRunResponseUpdate update in messageStream.WithCancellation(cancellationToken))
        {
            // Extract just the text content - this avoids serialization round-trip issues
            string text = update.Text;

            // Only publish non-empty text chunks
            if (!string.IsNullOrEmpty(text))
            {
                // Create the stream entry with the text and metadata
                NameValueEntry[] entries =
                [
                    new NameValueEntry("text", text),
                    new NameValueEntry("sequence", sequenceNumber++),
                    new NameValueEntry("timestamp", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()),
                ];

                // Add to the Redis Stream with auto-generated ID (timestamp-based)
                await db.StreamAddAsync(streamKey, entries);

                // Refresh the TTL on each write to keep the stream alive during active streaming
                await db.KeyExpireAsync(streamKey, this._streamTtl);
            }
        }

        // Add a sentinel entry to mark the end of the stream
        NameValueEntry[] endEntries =
        [
            new NameValueEntry("text", ""),
            new NameValueEntry("sequence", sequenceNumber),
            new NameValueEntry("timestamp", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()),
            new NameValueEntry("done", "true"),
        ];
        await db.StreamAddAsync(streamKey, endEntries);

        // Set final TTL - the stream will be cleaned up after this duration
        await db.KeyExpireAsync(streamKey, this._streamTtl);
    }

    /// <inheritdoc/>
    public ValueTask OnAgentResponseAsync(AgentRunResponse message, CancellationToken cancellationToken)
    {
        // This handler is optimized for streaming responses.
        // For non-streaming responses, we don't need to store in Redis since
        // the response is returned directly to the caller.
        return ValueTask.CompletedTask;
    }

    /// <summary>
    /// Reads chunks from a Redis stream for the given session, yielding them as they become available.
    /// </summary>
    /// <param name="conversationId">The conversation ID to read from.</param>
    /// <param name="cursor">Optional cursor to resume from. If null, reads from the beginning.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>An async enumerable of stream chunks.</returns>
    public async IAsyncEnumerable<StreamChunk> ReadStreamAsync(
        string conversationId,
        string? cursor,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        string streamKey = GetStreamKey(conversationId);

        IDatabase db = this._redis.GetDatabase();
        string startId = string.IsNullOrEmpty(cursor) ? "0-0" : cursor;

        int emptyReadCount = 0;
        bool hasSeenData = false;

        while (!cancellationToken.IsCancellationRequested)
        {
            StreamEntry[]? entries = null;
            string? errorMessage = null;

            try
            {
                entries = await db.StreamReadAsync(streamKey, startId, count: 100);
            }
            catch (Exception ex)
            {
                errorMessage = ex.Message;
            }

            if (errorMessage != null)
            {
                yield return new StreamChunk(startId, null, false, errorMessage);
                yield break;
            }

            // entries is guaranteed to be non-null if errorMessage is null
            if (entries!.Length == 0)
            {
                if (!hasSeenData)
                {
                    emptyReadCount++;
                    if (emptyReadCount >= MaxEmptyReads)
                    {
                        yield return new StreamChunk(
                            startId,
                            null,
                            false,
                            $"Stream not found or timed out after {MaxEmptyReads * PollIntervalMs / 1000} seconds");
                        yield break;
                    }
                }

                await Task.Delay(PollIntervalMs, cancellationToken);
                continue;
            }

            hasSeenData = true;

            foreach (StreamEntry entry in entries)
            {
                startId = entry.Id.ToString();
                string? text = entry["text"];
                string? done = entry["done"];

                if (done == "true")
                {
                    yield return new StreamChunk(startId, null, true, null);
                    yield break;
                }

                if (!string.IsNullOrEmpty(text))
                {
                    yield return new StreamChunk(startId, text, false, null);
                }
            }
        }
    }

    /// <summary>
    /// Gets the Redis Stream key for a given conversation ID.
    /// </summary>
    /// <param name="conversationId">The conversation ID.</param>
    /// <returns>The Redis Stream key.</returns>
    internal static string GetStreamKey(string conversationId) => $"agent-stream:{conversationId}";
}
