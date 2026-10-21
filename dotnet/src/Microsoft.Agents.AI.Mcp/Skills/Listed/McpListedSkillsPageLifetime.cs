// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI;

/// <summary>
/// The receipt timestamp and TTL of a discovery page.
/// </summary>
internal sealed class McpListedSkillsPageLifetime
{
    /// <summary>
    /// Initializes a page lifetime with its receipt timestamp and TTL.
    /// </summary>
    /// <param name="receivedTimestamp">The timestamp recorded when the page response was received.</param>
    /// <param name="timeToLive">The duration for which the page remains fresh.</param>
    public McpListedSkillsPageLifetime(long receivedTimestamp, TimeSpan timeToLive)
    {
        this.ReceivedTimestamp = receivedTimestamp;
        this.TimeToLive = timeToLive;
    }

    /// <summary>
    /// Gets the timestamp recorded when the page response was received.
    /// </summary>
    public long ReceivedTimestamp { get; }

    /// <summary>
    /// Gets the duration for which the page remains fresh.
    /// </summary>
    public TimeSpan TimeToLive { get; }
}
