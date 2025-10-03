// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace RealtimeKeypoints.Memory;

/// <summary>
/// Abstract base class for in-memory vector stores.
/// </summary>
public abstract class InMemoryVectorStore
{
    /// <summary>
    /// Gets recent transcripts within the specified time window.
    /// </summary>
    public abstract List<string> GetRecentTranscripts(TimeSpan timeWindow);
}
