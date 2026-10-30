// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests skill-list caching, refresh coordination, and catalog disposal.
/// </summary>
public sealed class McpSkillsCatalogTests
{
    [Fact]
    public void Constructor_NullClient_ThrowsArgumentNullException()
    {
        // Arrange
        var clock = new ManualTimeProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>("client", () => new McpSkillsCatalog(null!, timeProvider: clock));
    }

    [Fact]
    public void QueueSkillRefresh_NullSkill_ThrowsArgumentNullException()
    {
        // Arrange
        using var catalog = new McpSkillsCatalog(new Mock<McpClient>().Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("skill", () => catalog.QueueSkillRefresh(null!));
    }

    [Fact]
    public async Task GetSkillsAsync_PositiveTtl_ReusesListUntilExactExpirationAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateListResult(1000));
        }

        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);

        // Act
        var first = await catalog.GetSkillsAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        var fresh = await catalog.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.IsType<AgentMcpSkill>(Assert.Single(first));
        Assert.Same(first, fresh);
        Assert.Same(Assert.Single(first), Assert.Single(fresh));
        Assert.False(first.IsReadOnly);
        Assert.Equal(1, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var refreshed = await catalog.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.NotSame(Assert.Single(first), Assert.Single(refreshed));
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task GetSkillsAsync_ModifiedReturnedList_SharesChangesWithCachedListAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        using var catalog = new McpSkillsCatalog(CreateClient((_, _) =>
        {
            calls++;
            return Task.FromResult(CreateListResult(1000));
        }), timeProvider: clock);
        IList<AgentSkill> first = await catalog.GetSkillsAsync(CancellationToken.None);
        Assert.Single(first);

        // Act
        first.Clear();
        IList<AgentSkill> second = await catalog.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Same(first, second);
        Assert.Empty(second);
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
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token)
        {
            calls++;
            long[] ttls = [5000, 5000, 5000];
            ttls[expiredPage] = 1000;
            int page = request.Params?["cursor"] is { } cursor
                ? int.Parse(cursor.GetValue<string>(), System.Globalization.CultureInfo.InvariantCulture)
                : 0;
            JsonObject result = CreateListResult(ttls[page]);
            if (page < ttls.Length - 1)
            {
                result["nextCursor"] = (page + 1).ToString(System.Globalization.CultureInfo.InvariantCulture);
            }

            return Task.FromResult(result);
        }

        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);
        var first = await catalog.GetSkillsAsync(CancellationToken.None);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var refreshed = await catalog.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal(6, calls);
    }

    [Theory]
    [InlineData(1000L, 1)]
    [InlineData(0L, 8)]
    public async Task GetSkillsAsync_ConcurrentCalls_ReuseOnlyFreshResultsAsync(long ttl, int expectedCalls)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token) =>
            ++calls == 1 ? release.Task : Task.FromResult(CreateListResult(ttl));
        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);

        // Act
        Task<IList<AgentSkill>>[] pending = Enumerable.Range(0, 8)
            .Select(_ => catalog.GetSkillsAsync(CancellationToken.None)).ToArray();
        Assert.Equal(1, calls);
        release.SetResult(CreateListResult(ttl));
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
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        var error = new InvalidOperationException("Discovery failed.");
        int calls = 0;
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token) =>
            ++calls == 1 ? release.Task : Task.FromResult(CreateListResult(1000));
        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);
        var active = catalog.GetSkillsAsync(CancellationToken.None);
        var waiting = catalog.GetSkillsAsync(CancellationToken.None);

        // Act
        release.SetException(error);

        // Assert
        Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => active.WaitAsync(TimeSpan.FromSeconds(10))));
        var skills = await waiting.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Single(skills);
        Assert.Equal(skills, await catalog.GetSkillsAsync(CancellationToken.None));
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task GetSkillsAsync_CanceledAfterDiscovery_DoesNotCacheResultAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        using var cts = new CancellationTokenSource();
        int calls = 0;
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token)
        {
            if (++calls == 1)
            {
                Assert.Equal(cts.Token, token);
                cts.Cancel();
            }

            return Task.FromResult(CreateListResult(1000));
        }

        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => catalog.GetSkillsAsync(cts.Token));
        var skills = await catalog.GetSkillsAsync(CancellationToken.None);
        Assert.Single(skills);
        Assert.Equal(2, calls);
        Assert.Equal(skills, await catalog.GetSkillsAsync(CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_CanceledToken_DoesNotDiscoverOrReturnCachedSkillsAsync(bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateListResult(1000));
        }

        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);

        if (cached)
        {
            await catalog.GetSkillsAsync(CancellationToken.None);
        }

        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => catalog.GetSkillsAsync(cts.Token));
        Assert.Equal(cached ? 1 : 0, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_DisposedCatalog_ThrowsWithoutInvokingDiscoveryAsync(bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        Task<JsonObject> DiscoverAsync(JsonRpcRequest request, CancellationToken token)
        {
            calls++;
            return Task.FromResult(CreateListResult(1000));
        }

        using var catalog = new McpSkillsCatalog(CreateClient(DiscoverAsync), timeProvider: clock);

        if (cached)
        {
            await catalog.GetSkillsAsync(CancellationToken.None);
        }

        // Act
        catalog.Dispose();
        catalog.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => catalog.GetSkillsAsync(CancellationToken.None));
        Assert.Equal(cached ? 1 : 0, calls);
    }

    [Fact]
    public async Task Dispose_RetainedSkill_DoesNotKeepOtherSkillsAliveAsync()
    {
        // Arrange
        using var catalog = new McpSkillsCatalog(CreateClient((_, _) =>
            Task.FromResult(CreateListResult(3600000, "test-skill", "other-skill"))));
        var (retained, other) = await PopulateCatalogAsync(catalog);

        // Act
        catalog.Dispose();
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();

        // Assert
        Assert.False(other.TryGetTarget(out _));
        GC.KeepAlive(retained);

        [MethodImpl(MethodImplOptions.NoInlining)]
        static async Task<(AgentMcpSkill Retained, WeakReference<AgentMcpSkill> Other)> PopulateCatalogAsync(McpSkillsCatalog catalog)
        {
            IList<AgentSkill> skills = await catalog.GetSkillsAsync(CancellationToken.None);
            var retained = Assert.IsType<AgentMcpSkill>(skills[0]);
            var other = Assert.IsType<AgentMcpSkill>(skills[1]);
            catalog.QueueSkillRefresh(other);
            return (retained, new(other));
        }
    }

    /// <summary>
    /// Creates a skill-list response with complete manifests.
    /// </summary>
    private static JsonObject CreateListResult(long ttl, params string[] names)
    {
        JsonArray skills = [];
        foreach (string name in names.Length == 0 ? ["test-skill"] : names)
        {
            string uri = $"skill://{name}/SKILL.md";
            skills.Add(new JsonObject
            {
                ["uri"] = uri,
                ["frontmatter"] = new JsonObject { ["name"] = name, ["description"] = "A test skill." },
                ["resources"] = new JsonArray(new JsonObject
                {
                    ["uri"] = uri,
                    ["digest"] = "sha256:" + new string('0', 64),
                    ["size"] = 0,
                }),
            });
        }

        return new JsonObject { ["resultType"] = "complete", ["skills"] = skills, ["ttlMs"] = ttl };
    }

    /// <summary>
    /// Creates a client that forwards list requests to the test handler.
    /// </summary>
    private static McpClient CreateClient(Func<JsonRpcRequest, CancellationToken, Task<JsonObject>> handler)
    {
        var client = new Mock<McpClient>(MockBehavior.Strict);
        client.Setup(c => c.SendRequestAsync(It.Is<JsonRpcRequest>(request => request.Method == "skills/list"), It.IsAny<CancellationToken>()))
            .Returns((JsonRpcRequest request, CancellationToken token) => RespondAsync(request, token));
        return client.Object;

        async Task<JsonRpcResponse> RespondAsync(JsonRpcRequest request, CancellationToken token) =>
            new() { Id = request.Id, Result = await handler(request, token) };
    }

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
