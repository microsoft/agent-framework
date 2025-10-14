// Copyright (c) Microsoft. All rights reserved.

namespace RealtimeKeypoints.Memory;

/// <summary>
/// Abstract base class for in-memory vector stores.
/// </summary>
public abstract class InMemoryVectorStore
{
    /// <summary>
    /// Gets recent transcripts within the specified time window.
    /// </summary>
    public abstract Task<List<string>> GetRecentTranscriptsAsync(TimeSpan timeWindow, CancellationToken cancellationToken = default);
}
