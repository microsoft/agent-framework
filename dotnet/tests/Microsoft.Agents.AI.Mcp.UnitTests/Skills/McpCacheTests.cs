// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests cache expiration, queued refreshes, entry replacement, and entry limits.
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
    public async Task GetOrRefreshAsync_InfiniteLifetime_RefreshesOnlyWhenRequestedAsync(bool needsRefresh)
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
        Assert.Equal(cached ? 1 : 0, cache.Count);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrRefreshAsync_FailedOrCanceledFirstRead_RemovesEmptyStateAsync(bool canceled)
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cts = new CancellationTokenSource();
        Task<string> pending = cache.GetOrRefreshAsync("resource", (_, token) => new(release.Task.WaitAsync(token)), cts.Token).AsTask();

        // Act & Assert
        if (canceled)
        {
            await cts.CancelAsync();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending.WaitAsync(TimeSpan.FromSeconds(10)));
        }
        else
        {
            var error = new InvalidOperationException("Read failed.");
            release.SetException(error);
            Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => pending.WaitAsync(TimeSpan.FromSeconds(10))));
        }

        Assert.Equal(0, cache.Count);

        // Act
        string value = await cache.GetOrRefreshAsync("other",
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("content", McpCacheLifetime.Infinite)), CancellationToken.None);

        // Assert
        Assert.Equal("content", value);
    }

    [Fact]
    public async Task GetOrRefreshAsync_ReaderJoiningDuringFailure_KeepsStateUntilItsReadFinishesAsync()
    {
        // Arrange
        string lateKey = new("resource".ToCharArray());
        var lookupStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var releaseLookup = new ManualResetEventSlim();
        int pauseLookup = 1;
        var comparer = EqualityComparer<string>.Create((left, right) =>
        {
            if (ReferenceEquals(right, lateKey) && Interlocked.Exchange(ref pauseLookup, 0) == 1)
            {
                lookupStarted.SetResult();
                Assert.True(releaseLookup.Wait(TimeSpan.FromSeconds(10)));
            }

            return StringComparer.Ordinal.Equals(left, right);
        }, StringComparer.Ordinal.GetHashCode);
        var cache = new McpCache<string, string>(new ManualTimeProvider(), comparer);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<string> first = cache.GetOrRefreshAsync("resource", (_, _) => new(release.Task), CancellationToken.None).AsTask();
        Task<string> late = Task.Run(async () => await cache.GetOrRefreshAsync(lateKey,
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("replacement", McpCacheLifetime.Infinite)), CancellationToken.None));

        try
        {
            await lookupStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));

            // Act
            var error = new InvalidOperationException("Read failed.");
            release.SetException(error);

            // Assert
            Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => first.WaitAsync(TimeSpan.FromSeconds(10))));
            Assert.Equal(1, cache.Count);
            Assert.False(late.IsCompleted);

            // Act
            releaseLookup.Set();

            // Assert
            Assert.Equal("replacement", await late.WaitAsync(TimeSpan.FromSeconds(10)));
            Assert.Equal(1, cache.Count);
        }
        finally
        {
            releaseLookup.Set();
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(8)]
    public async Task GetOrRefreshAsync_FailedQueuedReads_RemoveStateAfterLastReadAsync(int canceledWaiters)
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);
        var release = new TaskCompletionSource<McpCacheEntry<string>>(TaskCreationOptions.RunContinuationsAsynchronously);
        var error = new InvalidOperationException("Read failed.");
        Task<string> first = cache.GetOrRefreshAsync("resource", (_, _) => new(release.Task), CancellationToken.None).AsTask();
        using var cts = new CancellationTokenSource();
        Task<string>[] canceled = Enumerable.Range(0, canceledWaiters).Select(_ => cache.GetOrRefreshAsync("resource",
            (_, _) => throw new InvalidOperationException("Unexpected refresh."), cts.Token).AsTask()).ToArray();
        Task<string> last = cache.GetOrRefreshAsync("resource", (_, _) => throw error, CancellationToken.None).AsTask();

        // Act
        await cts.CancelAsync();
        foreach (Task<string> task in canceled)
        {
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task.WaitAsync(TimeSpan.FromSeconds(10)));
        }

        // Assert
        Assert.Equal(1, cache.Count);
        Assert.False(last.IsCompleted);

        // Act
        release.SetException(error);

        // Assert
        Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => first.WaitAsync(TimeSpan.FromSeconds(10))));
        Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => last.WaitAsync(TimeSpan.FromSeconds(10))));
        Assert.Equal(0, cache.Count);
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
    public async Task GetOrRefreshAsync_EntryCountLimit_RejectsNewKeysButAllowsRefreshesAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal, new() { MaxEntryCount = 2 });
        await cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("one", size: 0, TimeSpan.Zero), CancellationToken.None);
        await cache.GetOrRefreshAsync("second", (_, _) => EntryAsync("two", size: 0, TimeSpan.Zero), CancellationToken.None);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrRefreshAsync("third", (_, _) => EntryAsync("three", size: 0, TimeSpan.Zero), CancellationToken.None).AsTask());
        string refreshed = await cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("updated", size: 0, TimeSpan.Zero), CancellationToken.None);

        // Assert
        Assert.Contains("limit of 2 entries", exception.Message);
        Assert.Equal("updated", refreshed);
        Assert.False(cache.Contains("third", _ => true));
        Assert.Equal(2, cache.Count);
    }

    [Fact]
    public async Task GetOrRefreshAsync_TotalSizeLimit_AcceptsBoundaryAndRejectsLargerAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal, new() { MaxTotalSize = 10 });
        await cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("one", size: 6, TimeSpan.Zero), CancellationToken.None);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrRefreshAsync("second", (_, _) => EntryAsync("too large", size: 5, TimeSpan.Zero), CancellationToken.None).AsTask());
        string second = await cache.GetOrRefreshAsync("second", (_, _) => EntryAsync("two", size: 4, TimeSpan.Zero), CancellationToken.None);

        // Assert
        Assert.Contains("total size limit of 10", exception.Message);
        Assert.Equal("two", second);
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrRefreshAsync("third", (_, _) => EntryAsync("three", size: 1, TimeSpan.Zero), CancellationToken.None).AsTask());
    }

    [Fact]
    public async Task GetOrRefreshAsync_TotalSizeLimit_RefreshReplacesPreviousSizeAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal, new() { MaxTotalSize = 10 });
        await cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("one", size: 3, TimeSpan.Zero), CancellationToken.None);
        await cache.GetOrRefreshAsync("second", (_, _) => EntryAsync("two", size: 7, TimeSpan.Zero), CancellationToken.None);

        // Act
        string grown = await cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("grown", size: 3, TimeSpan.Zero), CancellationToken.None);
        string shrunk = await cache.GetOrRefreshAsync("second", (_, _) => EntryAsync("shrunk", size: 2, TimeSpan.Zero), CancellationToken.None);
        string third = await cache.GetOrRefreshAsync("third", (_, _) => EntryAsync("three", size: 5, TimeSpan.Zero), CancellationToken.None);

        // Assert
        Assert.Equal("grown", grown);
        Assert.Equal("shrunk", shrunk);
        Assert.Equal("three", third);
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("too large", size: 4, TimeSpan.Zero), CancellationToken.None).AsTask());
    }

    [Fact]
    public async Task GetOrRefreshAsync_RejectedRefresh_KeepsPreviousEntryAndTotalsAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal, new() { MaxTotalSize = 10 });
        await cache.GetOrRefreshAsync("resource", (_, _) => EntryAsync("original", size: 4, TimeSpan.FromSeconds(1)), CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(1));

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrRefreshAsync("resource", (_, _) => EntryAsync("too large", size: 11, TimeSpan.FromSeconds(1)), CancellationToken.None).AsTask());
        string other = await cache.GetOrRefreshAsync("other", (_, _) => EntryAsync("other", size: 6, TimeSpan.Zero), CancellationToken.None);

        // Assert
        Assert.Equal("other", other);
        Assert.True(cache.Contains("resource", value => value == "original"));
        await cache.GetOrRefreshAsync("resource", (previous, _) =>
        {
            Assert.Equal("original", previous?.Value);
            return ValueTask.FromResult(previous!);
        }, CancellationToken.None);
    }

    [Fact]
    public async Task GetOrRefreshAsync_ExpiredEntries_CountTowardLimitsAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var cache = new McpCache<string, string>(clock, StringComparer.Ordinal, new() { MaxEntryCount = 1, MaxTotalSize = 10 });
        await cache.GetOrRefreshAsync("first", (_, _) => EntryAsync("one", size: 10, TimeSpan.FromSeconds(1)), CancellationToken.None);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));

        // Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrRefreshAsync("second", (_, _) => EntryAsync("two", size: 0, TimeSpan.Zero), CancellationToken.None).AsTask());
    }

    [Fact]
    public async Task GetOrRefreshAsync_ParallelReadsOfDifferentKeys_ShareLimitsAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal, new() { MaxEntryCount = 3, MaxTotalSize = 30 });
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int started = 0;
        var allStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Task<string>[] reads = Enumerable.Range(0, 8).Select(i => cache.GetOrRefreshAsync($"resource-{i}", async (_, _) =>
        {
            if (Interlocked.Increment(ref started) == 8)
            {
                allStarted.SetResult();
            }

            await release.Task.ConfigureAwait(false);
            return new McpCacheEntry<string>($"content-{i}", 10, McpCacheLifetime.Infinite);
        }, CancellationToken.None).AsTask()).ToArray();

        // Act
        await allStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
        release.SetResult();
        await Task.WhenAll(reads.Select(read => read.ContinueWith(_ => { }, TaskScheduler.Default))).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(3, reads.Count(read => read.Status == TaskStatus.RanToCompletion));
        Assert.All(reads.Where(read => read.IsFaulted), read => Assert.IsType<InvalidOperationException>(read.Exception!.InnerException));
        Assert.Equal(3, Enumerable.Range(0, 8).Count(i => cache.Contains($"resource-{i}", _ => true)));
    }

    [Fact]
    public async Task GetOrRefreshAsync_NoLimits_AcceptsAnyCountAndSizeAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal);

        // Act
        for (int i = 0; i < 100; i++)
        {
            await cache.GetOrRefreshAsync($"resource-{i}", (_, _) => EntryAsync("content", size: long.MaxValue, TimeSpan.FromSeconds(1)), CancellationToken.None);
        }

        // Assert
        Assert.Equal(100, Enumerable.Range(0, 100).Count(i => cache.Contains($"resource-{i}", _ => true)));
    }

    [Fact]
    public async Task GetOrRefreshAsync_TotalSizeLimit_RejectsEntryWithoutSizeAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal, new() { MaxTotalSize = 10 });

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => cache.GetOrRefreshAsync("resource",
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("content", McpCacheLifetime.Infinite)), CancellationToken.None).AsTask());

        // Assert
        Assert.Contains("requires a size", exception.Message);
        Assert.False(cache.Contains("resource", _ => true));
    }

    [Fact]
    public async Task GetOrRefreshAsync_EntryCountLimit_AcceptsEntriesWithoutSizeAsync()
    {
        // Arrange
        var cache = new McpCache<string, string>(new ManualTimeProvider(), StringComparer.Ordinal, new() { MaxEntryCount = 1 });

        // Act
        string value = await cache.GetOrRefreshAsync("resource",
            (_, _) => ValueTask.FromResult(new McpCacheEntry<string>("content", McpCacheLifetime.Infinite)), CancellationToken.None);

        // Assert
        Assert.Equal("content", value);
        Assert.Null(new McpCacheEntry<string>("content", McpCacheLifetime.Infinite).Size);
    }

    [Fact]
    public void Constructor_NonPositiveLimits_Throws()
    {
        // Arrange
        var clock = new ManualTimeProvider();

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>("MaxEntryCount", () =>
            new McpCache<string, string>(clock, StringComparer.Ordinal, new() { MaxEntryCount = 0 }));
        Assert.Throws<ArgumentOutOfRangeException>("MaxTotalSize", () =>
            new McpCache<string, string>(clock, StringComparer.Ordinal, new() { MaxTotalSize = -1 }));
    }

    [Fact]
    public void McpCacheEntry_NegativeSize_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>("size", () => new McpCacheEntry<string>("content", -1, McpCacheLifetime.Infinite));
    }

    private static ValueTask<McpCacheEntry<string>> EntryAsync(string value, long size, TimeSpan ttl) =>
        ValueTask.FromResult(new McpCacheEntry<string>(value, size, new(0, ttl)));

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
