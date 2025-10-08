// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics.Tensors;
using System.Threading;
using System.Threading.Tasks;

namespace RealtimeKeypoints.Memory;

/// <summary>
/// Simple in-memory vector store for transcript segments with semantic search capability.
/// </summary>
public sealed class TranscriptMemoryStore : InMemoryVectorStore, IDisposable
{
    private readonly List<TranscriptEntry> _entries = [];
    private readonly SemaphoreSlim _lock = new(1, 1);
    private readonly int _maxEntries;

    public TranscriptMemoryStore(int maxEntries = 1000)
    {
        this._maxEntries = maxEntries;
    }

    public void Dispose()
    {
        this._lock.Dispose();
    }

    public async Task AddAsync(string text, DateTimeOffset timestamp, IReadOnlyList<float>? embedding = null, CancellationToken cancellationToken = default)
    {
        await this._lock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var entry = new TranscriptEntry(text, timestamp, embedding);
            this._entries.Add(entry);

            // Keep memory bounded
            while (this._entries.Count > this._maxEntries)
            {
                this._entries.RemoveAt(0);
            }
        }
        finally
        {
            this._lock.Release();
        }
    }

    public async Task<IReadOnlyList<TranscriptEntry>> GetRecentAsync(int count, CancellationToken cancellationToken = default)
    {
        await this._lock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return this._entries.TakeLast(count).ToList();
        }
        finally
        {
            this._lock.Release();
        }
    }

    public async Task<IReadOnlyList<TranscriptEntry>> SearchAsync(IReadOnlyList<float> queryEmbedding, int topK = 5, CancellationToken cancellationToken = default)
    {
        await this._lock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return this._entries
                .Where(e => e.Embedding is not null)
                .Select(e => new
                {
                    Entry = e,
                    Score = CosineSimilarity(queryEmbedding, e.Embedding!)
                })
                .OrderByDescending(x => x.Score)
                .Take(topK)
                .Select(x => x.Entry)
                .ToList();
        }
        finally
        {
            this._lock.Release();
        }
    }

    public async Task<string> GetContextWindowAsync(int maxCharacters = 6000, CancellationToken cancellationToken = default)
    {
        await this._lock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var recent = this._entries.TakeLast(50).ToList();
            int charCount = 0;
            var contextParts = new List<string>();

            for (int i = recent.Count - 1; i >= 0; i--)
            {
                string text = recent[i].Text;
                if (charCount + text.Length > maxCharacters)
                {
                    break;
                }

                contextParts.Insert(0, text);
                charCount += text.Length;
            }

            return string.Join(" ", contextParts);
        }
        finally
        {
            this._lock.Release();
        }
    }

    public override async Task<List<string>> GetRecentTranscriptsAsync(TimeSpan timeWindow, CancellationToken cancellationToken = default)
    {
        var cutoff = DateTimeOffset.UtcNow - timeWindow;
        await this._lock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return this._entries
                .Where(e => e.Timestamp >= cutoff)
                .Select(e => e.Text)
                .ToList();
        }
        finally
        {
            this._lock.Release();
        }
    }

    /// <summary>
    /// Gets the timestamp of a specific transcript text.
    /// Returns DateTimeOffset.MinValue if not found.
    /// </summary>
    public async Task<DateTimeOffset> GetTranscriptTimestampAsync(string text, CancellationToken cancellationToken = default)
    {
        await this._lock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var entry = this._entries.FirstOrDefault(e => e.Text == text);
            return entry?.Timestamp ?? DateTimeOffset.MinValue;
        }
        finally
        {
            this._lock.Release();
        }
    }

    private static float CosineSimilarity(IReadOnlyList<float> a, IReadOnlyList<float> b)
    {
        if (a.Count != b.Count)
        {
            return 0f;
        }

        Span<float> spanA = a is float[] arrayA ? arrayA : a.ToArray();
        Span<float> spanB = b is float[] arrayB ? arrayB : b.ToArray();
        return TensorPrimitives.CosineSimilarity(spanA, spanB);
    }

    public sealed record TranscriptEntry(string Text, DateTimeOffset Timestamp, IReadOnlyList<float>? Embedding = null);
}
