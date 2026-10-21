// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed class McpListedSkillsCacheTests
{
    [Fact]
    public void Constructor_NullDiscoverSkills_ThrowsArgumentNullException()
    {
        // Arrange
        var clock = new ManualTimeProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>("discoverSkills", () => new McpListedSkillsCache(clock, null!));
    }

    [Fact]
    public async Task GetOrCreateAsync_PositiveTtl_ReturnsOriginalListUntilExactExpirationAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        McpListedSkillsSnapshot? discovered = null;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token)
        {
            calls++;
            discovered = CreateSnapshot(clock, 1000);
            return Task.FromResult(discovered);
        }

        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);

        // Act
        var first = await cache.GetOrCreateAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        var fresh = await cache.GetOrCreateAsync(CancellationToken.None);

        // Assert
        Assert.NotNull(discovered);
        Assert.Same(discovered.Skills, first);
        Assert.Same(first, fresh);
        Assert.False(first.IsReadOnly);
        Assert.Equal(1, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var refreshed = await cache.GetOrCreateAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Same(discovered.Skills, refreshed);
        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task GetOrCreateAsync_AnyExpiredPage_RefreshesEntireCatalogAsync(int expiredPage)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token)
        {
            calls++;
            long[] ttls = [5000, 5000, 5000];
            ttls[expiredPage] = 1000;
            return Task.FromResult(CreateSnapshot(clock, ttls));
        }

        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);
        var first = await cache.GetOrCreateAsync(CancellationToken.None);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var refreshed = await cache.GetOrCreateAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(1000L, 1)]
    [InlineData(0L, 8)]
    public async Task GetOrCreateAsync_ConcurrentCalls_ReuseOnlyFreshResultsAsync(long ttl, int expectedCalls)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var release = new TaskCompletionSource<McpListedSkillsSnapshot>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token) =>
            ++calls == 1 ? release.Task : Task.FromResult(CreateSnapshot(clock, ttl));
        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);

        // Act
        Task<IList<AgentSkill>>[] pending = Enumerable.Range(0, 8)
            .Select(_ => cache.GetOrCreateAsync(CancellationToken.None)).ToArray();
        Assert.Equal(1, calls);
        release.SetResult(CreateSnapshot(clock, ttl));
        var results = await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.All(results, result => Assert.Single(result));
        Assert.Equal(expectedCalls, calls);
        if (ttl > 0)
        {
            Assert.All(results, result => Assert.Same(results[0], result));
        }
        else
        {
            Assert.All(results.Skip(1), result => Assert.NotSame(results[0], result));
        }
    }

    [Fact]
    public async Task GetOrCreateAsync_FailedDiscovery_PreservesErrorAndReleasesWaiterAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var release = new TaskCompletionSource<McpListedSkillsSnapshot>(TaskCreationOptions.RunContinuationsAsynchronously);
        var error = new InvalidOperationException("Discovery failed.");
        int calls = 0;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token) =>
            ++calls == 1 ? release.Task : Task.FromResult(CreateSnapshot(clock, 1000));
        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);
        var active = cache.GetOrCreateAsync(CancellationToken.None);
        var waiting = cache.GetOrCreateAsync(CancellationToken.None);

        // Act
        release.SetException(error);

        // Assert
        Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => active.WaitAsync(TimeSpan.FromSeconds(10))));
        var skills = await waiting.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Single(skills);
        Assert.Same(skills, await cache.GetOrCreateAsync(CancellationToken.None));
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task GetOrCreateAsync_CanceledAfterDiscovery_DoesNotCacheResultAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        using var cts = new CancellationTokenSource();
        int calls = 0;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token)
        {
            if (++calls == 1)
            {
                Assert.Equal(cts.Token, token);
                cts.Cancel();
            }

            return Task.FromResult(CreateSnapshot(clock, 1000));
        }

        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => cache.GetOrCreateAsync(cts.Token));
        var skills = await cache.GetOrCreateAsync(CancellationToken.None);
        Assert.Single(skills);
        Assert.Equal(2, calls);
        Assert.Same(skills, await cache.GetOrCreateAsync(CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrCreateAsync_CanceledToken_DoesNotDiscoverOrReturnCachedSkillsAsync(bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateSnapshot(clock, 1000));
        }

        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);

        if (cached)
        {
            await cache.GetOrCreateAsync(CancellationToken.None);
        }

        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => cache.GetOrCreateAsync(cts.Token));
        Assert.Equal(cached ? 1 : 0, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetOrCreateAsync_DisposedCache_ThrowsWithoutInvokingDiscoveryAsync(bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<McpListedSkillsSnapshot> DiscoverAsync(CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateSnapshot(clock, 1000));
        }

        using var cache = new McpListedSkillsCache(clock, DiscoverAsync);

        if (cached)
        {
            await cache.GetOrCreateAsync(CancellationToken.None);
        }

        // Act
        cache.Dispose();
        cache.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => cache.GetOrCreateAsync(CancellationToken.None));
        Assert.Equal(cached ? 1 : 0, calls);
    }

    private static McpListedSkillsSnapshot CreateSnapshot(ManualTimeProvider clock, params long[] ttls) =>
        new([new AgentInlineSkill("test-skill", "A test skill.", "Test instructions.")],
            ttls.Select(ttl => new McpListedSkillsPageLifetime(clock.GetTimestamp(), TimeSpan.FromMilliseconds(ttl))).ToList());

    private sealed class ManualTimeProvider : TimeProvider
    {
        private long _timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => Interlocked.Read(ref this._timestamp);

        public void Advance(TimeSpan duration) => Interlocked.Add(ref this._timestamp, duration.Ticks);
    }
}
