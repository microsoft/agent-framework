// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using ModelContextProtocol.Client;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests skill-list caching, refresh coordination, and loader disposal.
/// </summary>
public sealed class McpSkillsLoaderTests
{
    [Fact]
    public void Constructor_NullFetchSkills_ThrowsArgumentNullException()
    {
        // Arrange
        var clock = new ManualTimeProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>("fetchSkills", () => new McpSkillsLoader(clock, null!, UnexpectedRefreshAsync));
    }

    [Fact]
    public void Constructor_NullFetchSkill_ThrowsArgumentNullException()
    {
        // Arrange
        var clock = new ManualTimeProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>("fetchSkill", () => new McpSkillsLoader(
            clock, _ => Task.FromResult(CreateSnapshot(clock, 1000)), null!));
    }

    [Fact]
    public async Task GetSkillsAsync_PositiveTtl_ReusesListUntilExactExpirationAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        McpCacheEntry<IList<AgentSkill>>? discovered = null;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token)
        {
            calls++;
            discovered = CreateSnapshot(clock, 1000);
            return Task.FromResult(discovered);
        }

        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);

        // Act
        var first = await loader.GetSkillsAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        var fresh = await loader.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.NotNull(discovered);
        Assert.Same(discovered.Value, first);
        Assert.Same(discovered.Value[0], Assert.Single(first));
        Assert.Same(first, fresh);
        Assert.Same(Assert.Single(first), Assert.Single(fresh));
        Assert.False(first.IsReadOnly);
        Assert.Equal(1, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var refreshed = await loader.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Same(discovered.Value, refreshed);
        Assert.NotSame(Assert.Single(first), Assert.Single(refreshed));
        Assert.Same(discovered.Value[0], Assert.Single(refreshed));
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task GetSkillsAsync_ModifiedReturnedList_SharesChangesWithCachedListAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var snapshot = CreateSnapshot(clock, 1000);
        int calls = 0;
        using var loader = new McpSkillsLoader(clock, _ =>
        {
            calls++;
            return Task.FromResult(snapshot);
        }, UnexpectedRefreshAsync);
        IList<AgentSkill> first = await loader.GetSkillsAsync(CancellationToken.None);
        Assert.Single(first);

        // Act
        first.Clear();
        IList<AgentSkill> second = await loader.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Same(first, second);
        Assert.Empty(second);
        Assert.Same(snapshot.Value, second);
        Assert.Empty(snapshot.Value);
        Assert.Equal(1, calls);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task GetSkillsAsync_AnyExpiredPage_RefreshesEntireCatalogAsync(int expiredPage)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token)
        {
            calls++;
            long[] ttls = [5000, 5000, 5000];
            ttls[expiredPage] = 1000;
            return Task.FromResult(CreateSnapshot(clock, ttls));
        }

        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);
        var first = await loader.GetSkillsAsync(CancellationToken.None);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var refreshed = await loader.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(1000L, 1)]
    [InlineData(0L, 8)]
    public async Task GetSkillsAsync_ConcurrentCalls_ReuseOnlyFreshResultsAsync(long ttl, int expectedCalls)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var release = new TaskCompletionSource<McpCacheEntry<IList<AgentSkill>>>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token) =>
            ++calls == 1 ? release.Task : Task.FromResult(CreateSnapshot(clock, ttl));
        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);

        // Act
        Task<IList<AgentSkill>>[] pending = Enumerable.Range(0, 8)
            .Select(_ => loader.GetSkillsAsync(CancellationToken.None)).ToArray();
        Assert.Equal(1, calls);
        release.SetResult(CreateSnapshot(clock, ttl));
        var results = await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.All(results, result => Assert.Single(result));
        Assert.Equal(expectedCalls, calls);
        if (ttl > 0)
        {
            Assert.All(results, result => Assert.Same(results[0], result));
            Assert.All(results, result => Assert.Same(Assert.Single(results[0]), Assert.Single(result)));
        }
        else
        {
            Assert.All(results.Skip(1), result => Assert.NotSame(Assert.Single(results[0]), Assert.Single(result)));
        }
    }

    [Fact]
    public async Task GetSkillsAsync_FailedDiscovery_PreservesErrorAndReleasesWaiterAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var release = new TaskCompletionSource<McpCacheEntry<IList<AgentSkill>>>(TaskCreationOptions.RunContinuationsAsynchronously);
        var error = new InvalidOperationException("Discovery failed.");
        int calls = 0;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token) =>
            ++calls == 1 ? release.Task : Task.FromResult(CreateSnapshot(clock, 1000));
        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);
        var active = loader.GetSkillsAsync(CancellationToken.None);
        var waiting = loader.GetSkillsAsync(CancellationToken.None);

        // Act
        release.SetException(error);

        // Assert
        Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => active.WaitAsync(TimeSpan.FromSeconds(10))));
        var skills = await waiting.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Single(skills);
        Assert.Equal(skills, await loader.GetSkillsAsync(CancellationToken.None));
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task GetSkillsAsync_CanceledAfterDiscovery_DoesNotCacheResultAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        using var cts = new CancellationTokenSource();
        int calls = 0;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token)
        {
            if (++calls == 1)
            {
                Assert.Equal(cts.Token, token);
                cts.Cancel();
            }

            return Task.FromResult(CreateSnapshot(clock, 1000));
        }

        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => loader.GetSkillsAsync(cts.Token));
        var skills = await loader.GetSkillsAsync(CancellationToken.None);
        Assert.Single(skills);
        Assert.Equal(2, calls);
        Assert.Equal(skills, await loader.GetSkillsAsync(CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_CanceledToken_DoesNotDiscoverOrReturnCachedSkillsAsync(bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateSnapshot(clock, 1000));
        }

        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);

        if (cached)
        {
            await loader.GetSkillsAsync(CancellationToken.None);
        }

        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => loader.GetSkillsAsync(cts.Token));
        Assert.Equal(cached ? 1 : 0, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_DisposedLoader_ThrowsWithoutInvokingDiscoveryAsync(bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<McpCacheEntry<IList<AgentSkill>>> DiscoverAsync(CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateSnapshot(clock, 1000));
        }

        using var loader = new McpSkillsLoader(clock, DiscoverAsync, UnexpectedRefreshAsync);

        if (cached)
        {
            await loader.GetSkillsAsync(CancellationToken.None);
        }

        // Act
        loader.Dispose();
        loader.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => loader.GetSkillsAsync(CancellationToken.None));
        Assert.Equal(cached ? 1 : 0, calls);
    }

    [Fact]
    public void Dispose_RetainedSkill_DoesNotKeepOtherSkillsAlive()
    {
        // Arrange
        McpCacheEntry<IList<AgentSkill>>? snapshot = null;
        using var loader = new McpSkillsLoader(TimeProvider.System, _ => Task.FromResult(snapshot!), UnexpectedRefreshAsync);
        var retained = new AgentMcpSkill(
            new AgentSkillFrontmatter("test-skill", "A test skill."),
            "skill://test-skill/SKILL.md", [], new Mock<McpClient>().Object, loader);
        WeakReference<AgentMcpSkill> other = PopulateCatalog(loader, retained, out snapshot);
        snapshot = null;

        // Act
        loader.Dispose();
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();

        // Assert
        Assert.False(other.TryGetTarget(out _));
        GC.KeepAlive(retained);

        [MethodImpl(MethodImplOptions.NoInlining)]
        static WeakReference<AgentMcpSkill> PopulateCatalog(
            McpSkillsLoader loader,
            AgentMcpSkill retained,
            out McpCacheEntry<IList<AgentSkill>> snapshot)
        {
            var other = new AgentMcpSkill(
                new AgentSkillFrontmatter("other-skill", "Another skill."),
                "skill://other-skill/SKILL.md", [], new Mock<McpClient>().Object, loader);
            snapshot = new([retained, other], new(TimeProvider.System.GetTimestamp(), TimeSpan.FromHours(1)));
            Assert.True(loader.GetSkillsAsync(CancellationToken.None).IsCompletedSuccessfully);
            loader.QueueSkillRefresh(other);
            return new(other);
        }
    }

    /// <summary>
    /// Creates a cached skill list using the shortest supplied TTL.
    /// </summary>
    private static McpCacheEntry<IList<AgentSkill>> CreateSnapshot(ManualTimeProvider clock, params long[] ttls)
    {
        return new([new AgentInlineSkill("test-skill", "A test skill.", "Test instructions.")],
            new(clock.GetTimestamp(), TimeSpan.FromMilliseconds(ttls.Min())));
    }

    /// <summary>
    /// Fails on an unexpected individual skill refresh.
    /// </summary>
    private static Task<AgentMcpSkill?> UnexpectedRefreshAsync(string uri, CancellationToken cancellationToken) =>
        throw new InvalidOperationException("No individual skill refresh was expected.");

    /// <summary>
    /// Provides a clock that tests can advance without waiting.
    /// </summary>
    private sealed class ManualTimeProvider : TimeProvider
    {
        private long _timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => Interlocked.Read(ref this._timestamp);

        public void Advance(TimeSpan duration) => Interlocked.Add(ref this._timestamp, duration.Ticks);
    }
}
