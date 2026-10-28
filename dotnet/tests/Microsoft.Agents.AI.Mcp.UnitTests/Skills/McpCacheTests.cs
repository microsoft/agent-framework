// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests cache expiration, queued refreshes, entry replacement, and clearing stored values.
/// </summary>
public sealed class McpCacheTests
{
    [Fact]
    public void LifetimeIsFresh_InfiniteLifetime_DoesNotExpire()
    {
        // Arrange
        var clock = new ManualTimeProvider();

        // Act
        clock.Advance(TimeSpan.MaxValue);

        // Assert
        Assert.True(McpCacheLifetime.Infinite.IsFresh(clock));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrRefreshAsync_InfiniteLifetime_RefreshesOnlyWhenRequestedOrClearedAsync(bool needsRefresh)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var original = new McpCacheEntry<string>("original", McpCacheLifetime.Infinite);
        await cache.GetOrRefreshAsync("resource", (_, _) => ValueTask.FromResult(original), CancellationToken.None);
        clock.Advance(TimeSpan.MaxValue);
        int refreshes = 0;

        // Act
        string value = await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Same(original, previous);
            refreshes++;
            return ValueTask.FromResult(new McpCacheEntry<string>("replacement", McpCacheLifetime.Infinite));
        }, CancellationToken.None, needsRefresh: _ => needsRefresh);

        // Assert
        Assert.Equal(needsRefresh ? "replacement" : "original", value);
        Assert.Equal(needsRefresh ? 1 : 0, refreshes);

        // Act
        cache.Clear();
        string reloaded = await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Null(previous);
            refreshes++;
            return ValueTask.FromResult(new McpCacheEntry<string>("reloaded", McpCacheLifetime.Infinite));
        }, CancellationToken.None);

        // Assert
        Assert.Equal("reloaded", reloaded);
        Assert.Equal(needsRefresh ? 2 : 1, refreshes);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(0)]
    [InlineData(1000)]
    public void LifetimeIsFresh_UsesCurrentTimeAndExactExpiration(long ttlMilliseconds)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        clock.Advance(TimeSpan.FromSeconds(5));
        var lifetime = new McpCacheLifetime(clock.GetTimestamp(), TimeSpan.FromMilliseconds(ttlMilliseconds));

        // Act & Assert
        Assert.Equal(ttlMilliseconds > 0, lifetime.IsFresh(clock));
        if (ttlMilliseconds > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(ttlMilliseconds - 1));
            Assert.True(lifetime.IsFresh(clock));
            clock.Advance(TimeSpan.FromMilliseconds(1));
            Assert.False(lifetime.IsFresh(clock));
        }
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(0)]
    [InlineData(1000)]
    public async Task GetOrRefreshAsync_UsesExactExpirationWithoutRemovingEntryAsync(long ttlMilliseconds)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var entry = new McpCacheEntry<string>("content", new(clock.GetTimestamp(), TimeSpan.FromMilliseconds(ttlMilliseconds)));
        await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Null(previous);
            return ValueTask.FromResult(entry);
        }, CancellationToken.None);
        int refreshes = 0;
        ValueTask<McpCacheEntry<string>> RefreshAsync(McpCacheEntry<string>? previous, CancellationToken token)
        {
            Assert.Same(entry, previous);
            Assert.False(previous!.Lifetime.IsFresh(clock));
            refreshes++;
            return ValueTask.FromResult(entry);
        }

        // Act & Assert
        if (ttlMilliseconds > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(ttlMilliseconds - 1));
            Assert.Equal("content", await cache.GetOrRefreshAsync("resource", RefreshAsync, CancellationToken.None));
            Assert.Equal(0, refreshes);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        Assert.Equal("content", await cache.GetOrRefreshAsync("resource", RefreshAsync, CancellationToken.None));
        Assert.Equal(1, refreshes);
        Assert.True(cache.Contains("resource", value => value == "content"));
    }

    [Fact]
    public async Task GetOrRefreshAsync_ReplacesValueAndLifetimeTogetherAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var first = new McpCacheEntry<string>("first", new(clock.GetTimestamp(), TimeSpan.FromSeconds(1)));
        await cache.GetOrRefreshAsync("resource", (_, _) => ValueTask.FromResult(first), CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(1));
        var replacement = new McpCacheEntry<string>("second", new(clock.GetTimestamp(), TimeSpan.FromSeconds(2)));

        // Act
        await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Same(first, previous);
            Assert.False(previous!.Lifetime.IsFresh(clock));
            return ValueTask.FromResult(replacement);
        }, CancellationToken.None);

        // Assert
        Assert.True(cache.Contains("resource", value => value == "second"));
        Assert.False(cache.Contains("RESOURCE", _ => true));
        clock.Advance(TimeSpan.FromMilliseconds(1999));
        Assert.Equal("second", await cache.GetOrRefreshAsync("resource",
            (_, _) => throw new InvalidOperationException("Unexpected refresh."), CancellationToken.None));
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Same(replacement, previous);
            Assert.False(previous!.Lifetime.IsFresh(clock));
            return ValueTask.FromResult(replacement);
        }, CancellationToken.None);
    }

    [Fact]
    public async Task Clear_RemovesAllEntriesAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        await cache.GetOrRefreshAsync("first",
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("one", new(0, TimeSpan.FromSeconds(1)))), CancellationToken.None);
        await cache.GetOrRefreshAsync("second",
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("two", new(0, TimeSpan.FromSeconds(1)))), CancellationToken.None);

        // Act
        cache.Clear();

        // Assert
        Assert.False(cache.Contains("first", _ => true));
        Assert.False(cache.Contains("second", _ => true));
        await cache.GetOrRefreshAsync("first", (previous, _) =>
        {
            Assert.Null(previous);
            return ValueTask.FromResult(new McpCacheEntry<string>("replacement", new(0, TimeSpan.FromSeconds(1))));
        }, CancellationToken.None);
    }

    [Theory]
    [InlineData(-1, 8)]
    [InlineData(0, 8)]
    [InlineData(1000, 1)]
    public async Task GetOrRefreshAsync_ConcurrentCalls_ReuseOnlyFreshResultsAsync(long ttlMilliseconds, int expectedRefreshes)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.OrdinalIgnoreCase);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int refreshes = 0;
        async ValueTask<McpCacheEntry<string>> RefreshAsync(McpCacheEntry<string>? previous, CancellationToken token)
        {
            int refresh = Interlocked.Increment(ref refreshes);
            Assert.Equal(refresh == 1, previous is null);
            Assert.False(previous?.Lifetime.IsFresh(clock) ?? false);
            await release.Task.WaitAsync(token);
            return new("content", new(clock.GetTimestamp(), TimeSpan.FromMilliseconds(ttlMilliseconds)));
        }

        // Act
        Task<string>[] pending = Enumerable.Range(0, 8)
            .Select(i => cache.GetOrRefreshAsync(i % 2 == 0 ? "resource" : "RESOURCE", RefreshAsync, CancellationToken.None).AsTask())
            .ToArray();

        // Assert
        Assert.Equal(1, refreshes);

        // Act
        release.SetResult();
        string[] results = await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.All(results, result => Assert.Equal("content", result));
        Assert.Equal(expectedRefreshes, refreshes);
        Assert.True(cache.Contains("RESOURCE", value => value == "content"));
    }

    [Fact]
    public async Task GetOrRefreshAsync_ExpiredEntry_CanBeReturnedWithoutRenewingLifetimeAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var entry = new McpCacheEntry<string>("content", new(clock.GetTimestamp(), TimeSpan.FromSeconds(1)));
        await cache.GetOrRefreshAsync("resource", (_, _) => ValueTask.FromResult(entry), CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(1));
        int refreshes = 0;
        ValueTask<McpCacheEntry<string>> RefreshAsync(McpCacheEntry<string>? previous, CancellationToken token)
        {
            Assert.Same(entry, previous);
            Assert.False(previous!.Lifetime.IsFresh(clock));
            refreshes++;
            return ValueTask.FromResult(entry);
        }

        // Act
        string first = await cache.GetOrRefreshAsync("resource", RefreshAsync, CancellationToken.None);
        string second = await cache.GetOrRefreshAsync("resource", RefreshAsync, CancellationToken.None);

        // Assert
        Assert.Equal("content", first);
        Assert.Equal(first, second);
        Assert.Equal(2, refreshes);
        Assert.True(cache.Contains("resource", value => value == "content"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrRefreshAsync_CanceledToken_DoesNotInvokeCallbackOrReturnCachedValueAsync(bool cached)
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        if (cached)
        {
            await cache.GetOrRefreshAsync("resource",
                (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("content", new(0, TimeSpan.FromSeconds(1)))), CancellationToken.None);
        }

        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        var error = await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await cache.GetOrRefreshAsync("resource", (_, _) => throw new InvalidOperationException("Unexpected refresh."), cts.Token));
        Assert.Equal(cts.Token, error.CancellationToken);
        Assert.Equal(cached, cache.Contains("resource", _ => true));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrRefreshAsync_FailedOrCanceledRefresh_PreservesEntryAndReleasesWaiterAsync(bool canceled)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var original = new McpCacheEntry<string>("old", new(0, TimeSpan.Zero));
        await cache.GetOrRefreshAsync("resource", (_, _) => ValueTask.FromResult(original), CancellationToken.None);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        var error = new InvalidOperationException("Refresh failed.");
        using var cts = new CancellationTokenSource();
        var replacement = new McpCacheEntry<string>("new", new(0, TimeSpan.FromSeconds(1)));
        ValueTask<McpCacheEntry<string>> RefreshAsync(McpCacheEntry<string>? previous, CancellationToken token)
        {
            Assert.Same(original, previous);
            Assert.False(previous!.Lifetime.IsFresh(clock));
            Assert.True(cache.Contains("resource", value => value == "old"));
            return ValueTask.FromResult(replacement);
        }

        Task<string> active = cache.GetOrRefreshAsync("resource", (_, _) => new(release.Task), cts.Token).AsTask();
        Task<string> waiting = cache.GetOrRefreshAsync("resource", RefreshAsync, CancellationToken.None).AsTask();

        // Act & Assert
        if (canceled)
        {
            await cts.CancelAsync();
            release.SetResult(new("canceled", new(0, TimeSpan.FromSeconds(1))));
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => active.WaitAsync(TimeSpan.FromSeconds(10)));
        }
        else
        {
            release.SetException(error);
            Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => active.WaitAsync(TimeSpan.FromSeconds(10))));
        }

        Assert.Equal("new", await waiting.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.True(cache.Contains("resource", value => value == "new"));
    }

    [Fact]
    public async Task GetOrRefreshAsync_DifferentKeys_DoNotWaitForEachOtherAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<string> active = cache.GetOrRefreshAsync("first", (_, _) => new(release.Task), CancellationToken.None).AsTask();

        // Act
        string other = await cache.GetOrRefreshAsync("second",
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("other", new(0, TimeSpan.FromSeconds(1)))),
            CancellationToken.None).AsTask().WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal("other", other);
        Assert.False(active.IsCompleted);

        // Act
        release.SetResult(new("first", new(0, TimeSpan.FromSeconds(1))));

        // Assert
        Assert.Equal("first", await active.WaitAsync(TimeSpan.FromSeconds(10)));
    }

    [Fact]
    public async Task GetOrRefreshAsync_CanceledWaiter_DoesNotLetLaterReadSkipActiveRefreshAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cts = new CancellationTokenSource();
        Task<string> active = cache.GetOrRefreshAsync("resource", (_, _) => new(release.Task), CancellationToken.None).AsTask();
        Task<string> canceled = cache.GetOrRefreshAsync("resource",
            (_, _) => throw new InvalidOperationException("Unexpected refresh."), cts.Token).AsTask();

        // Act
        await cts.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => canceled.WaitAsync(TimeSpan.FromSeconds(10)));
        Task<string> waiting = cache.GetOrRefreshAsync("resource",
            (_, _) => throw new InvalidOperationException("Unexpected refresh."), CancellationToken.None).AsTask();

        // Assert
        Assert.False(active.IsCompleted);
        Assert.False(waiting.IsCompleted);

        // Act
        release.SetResult(new("content", new(0, TimeSpan.FromSeconds(1))));

        // Assert
        Assert.Equal("content", await active.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.Equal("content", await waiting.WaitAsync(TimeSpan.FromSeconds(10)));
    }

    [Fact]
    public async Task GetOrRefreshAsync_RefreshCondition_UpdatesFreshEntryWithoutExtendingLifetimeAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var original = new McpCacheEntry<string>("original", new(0, TimeSpan.FromSeconds(1)));
        await cache.GetOrRefreshAsync("resource", (_, _) => ValueTask.FromResult(original), CancellationToken.None);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        var replacement = new McpCacheEntry<string>("replacement", original.Lifetime);

        // Act
        string value = await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Same(original, previous);
            Assert.True(previous!.Lifetime.IsFresh(clock));
            return ValueTask.FromResult(replacement);
        }, CancellationToken.None, needsRefresh: content => content == "original");

        // Assert
        Assert.Equal("replacement", value);
        Assert.False(cache.Contains("resource", content => content == "original"));
        Assert.True(cache.Contains("resource", content => content == "replacement"));
        Assert.Equal(value, await cache.GetOrRefreshAsync("resource",
            (_, _) => throw new InvalidOperationException("Unexpected refresh."),
            CancellationToken.None, needsRefresh: content => content == "original"));

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Same(replacement, previous);
            Assert.False(previous!.Lifetime.IsFresh(clock));
            return ValueTask.FromResult(replacement);
        }, CancellationToken.None);

        // Assert
        Assert.True(cache.Contains("resource", content => content == "replacement"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrRefreshAsync_RefreshCondition_IsCheckedAfterWaitingAsync(bool needsRefresh)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<string> active = cache.GetOrRefreshAsync("resource", (_, _) => new(release.Task), CancellationToken.None).AsTask();
        int checks = 0;
        int refreshes = 0;
        bool pendingRefresh = !needsRefresh;
        Task<string> waiting = cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.NotNull(previous);
            Assert.True(previous.Lifetime.IsFresh(clock));
            refreshes++;
            return ValueTask.FromResult(new McpCacheEntry<string>("updated", previous.Lifetime));
        }, CancellationToken.None, needsRefresh: value =>
        {
            Assert.Equal("original", value);
            checks++;
            return pendingRefresh;
        }).AsTask();

        // Assert
        Assert.Equal(0, checks);
        Assert.False(cache.Contains("resource", _ => throw new InvalidOperationException("No value is cached yet.")));

        // Act
        pendingRefresh = needsRefresh;
        release.SetResult(new("original", new(0, TimeSpan.FromSeconds(1))));

        // Assert
        Assert.Equal("original", await active.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.Equal(needsRefresh ? "updated" : "original", await waiting.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.Equal(1, checks);
        Assert.Equal(needsRefresh ? 1 : 0, refreshes);
    }

    [Fact]
    public async Task Clear_ActiveRefresh_KeepsReadsInTheSameQueueAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<string> active = cache.GetOrRefreshAsync("resource", (_, _) => new(release.Task), CancellationToken.None).AsTask();

        // Act
        cache.Clear();
        Task<string> waiting = cache.GetOrRefreshAsync("resource",
            (_, _) => throw new InvalidOperationException("Unexpected overlapping refresh."), CancellationToken.None).AsTask();

        // Assert
        Assert.False(waiting.IsCompleted);

        // Act
        release.SetResult(new("content", new(0, TimeSpan.FromSeconds(1))));

        // Assert
        Assert.Equal("content", await active.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.Equal("content", await waiting.WaitAsync(TimeSpan.FromSeconds(10)));
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
