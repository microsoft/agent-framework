// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests cache expiration, entry replacement, and clearing stored values.
/// </summary>
public sealed class McpCacheTests
{
    [Theory]
    [InlineData(-1)]
    [InlineData(0)]
    [InlineData(1000)]
    public void IsFresh_UsesExactExpirationWithoutRemovingEntry(long ttlMilliseconds)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var entry = new McpCacheEntry<string>("content", new(clock.GetTimestamp(), TimeSpan.FromMilliseconds(ttlMilliseconds)));
        cache.Set("resource", entry);

        // Act & Assert
        Assert.Equal(ttlMilliseconds > 0, cache.IsFresh(entry));
        if (ttlMilliseconds > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(ttlMilliseconds - 1));
            Assert.True(cache.IsFresh(entry));
            Assert.Same(entry, cache.Get("resource"));
            clock.Advance(TimeSpan.FromMilliseconds(1));
            Assert.False(cache.IsFresh(entry));
        }

        Assert.Same(entry, cache.Get("resource"));
    }

    [Fact]
    public void Set_ReplacesValueAndLifetimeTogether()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var first = new McpCacheEntry<string>("first", new(clock.GetTimestamp(), TimeSpan.FromSeconds(1)));
        cache.Set("resource", first);
        clock.Advance(TimeSpan.FromSeconds(1));
        var replacement = new McpCacheEntry<string>("second", new(clock.GetTimestamp(), TimeSpan.FromSeconds(2)));

        // Act
        cache.Set("resource", replacement);

        // Assert
        Assert.Same(replacement, cache.Get("resource"));
        Assert.True(cache.IsFresh(replacement));
        Assert.False(cache.IsFresh(first));
        Assert.Null(cache.Get("RESOURCE"));
    }

    [Fact]
    public void Clear_RemovesAllEntries()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        cache.Set("first", new("one", new(0, TimeSpan.FromSeconds(1))));
        cache.Set("second", new("two", new(0, TimeSpan.FromSeconds(1))));

        // Act
        cache.Clear();

        // Assert
        Assert.Null(cache.Get("first"));
        Assert.Null(cache.Get("second"));
    }

    /// <summary>
    /// Provides a clock that tests can advance without waiting.
    /// </summary>
    private sealed class ManualTimeProvider : TimeProvider
    {
        private long _timestamp;

        // Deliberately different from TimeSpan ticks to check timestamp-unit conversions.
        public override long TimestampFrequency => 1000;

        public override long GetTimestamp() => Interlocked.Read(ref this._timestamp);

        public void Advance(TimeSpan duration) => Interlocked.Add(ref this._timestamp, (long)duration.TotalMilliseconds);
    }
}
