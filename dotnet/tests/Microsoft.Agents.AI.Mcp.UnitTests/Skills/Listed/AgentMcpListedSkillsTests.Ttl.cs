// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpListedSkillsTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_PositiveTtl_ReusesCatalogUntilExactExpirationAsync(bool empty)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            calls++;
            long ttl = calls == 1 ? 1000 : 2000;
            return Task.FromResult(empty ? TtlListResult(ttl) : TtlListResult(ttl, Entry()));
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);

        // Act
        var first = await loader.DiscoverAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        var fresh = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Same(first, fresh);
        Assert.False(first.IsReadOnly);
        Assert.Equal(empty ? 0 : 1, fresh.Count);
        Assert.Equal(1, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var refreshed = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.False(refreshed.IsReadOnly);
        Assert.Equal(2, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1999));
        var stillFresh = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Same(refreshed, stillFresh);
        Assert.Equal(2, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var expired = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(refreshed, expired);
        Assert.Equal(3, calls);
        client.Verify(c => c.SendRequestAsync(It.Is<JsonRpcRequest>(request => request.Method == "skills/list"), It.IsAny<CancellationToken>()), Times.Exactly(3));
        client.VerifyNoOtherCalls();
    }

    [Theory]
    [InlineData(null)]
    [InlineData("null")]
    [InlineData("0")]
    [InlineData("-1")]
    [InlineData("-9223372036854775808")]
    public async Task DiscoverAsync_MissingNullOrNonpositiveTtl_RefetchesOnEveryAccessAsync(string? ttl)
    {
        // Arrange
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            calls++;
            JsonObject result = TtlListResult(null, Entry());
            if (ttl is not null)
            {
                result["ttlMs"] = JsonNode.Parse(ttl);
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object);

        // Act
        var first = await loader.DiscoverAsync(CancellationToken.None);
        var second = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, second);
        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_ExtremelyLargeTtl_DoesNotOverflowFreshnessCalculationAsync(bool paginated)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((request, _) =>
        {
            calls++;
            JsonObject result = TtlListResult(long.MaxValue, Entry());
            if (paginated && request.Params?["cursor"] is null)
            {
                result["nextCursor"] = "next";
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);

        // Act
        var first = await loader.DiscoverAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromDays(365));
        var second = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Same(first, second);
        Assert.Equal(paginated ? 2 : 1, calls);
    }

    [Theory]
    [InlineData(1000L, 5000L, 5000L, 600L)]
    [InlineData(5000L, 1000L, 5000L, 800L)]
    [InlineData(5000L, 5000L, 1000L, 1000L)]
    [InlineData(1000L, 900L, 800L, 600L)]
    public async Task DiscoverAsync_PaginatedTtl_ExpiresWhenAnyPageExpiresAsync(long firstTtl, long secondTtl, long thirdTtl, long remaining)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<string?> cursors = [];
        var client = CreateTtlClient((request, _) =>
        {
            string? cursor = request.Params?["cursor"]?.GetValue<string>();
            cursors.Add(cursor);
            JsonObject result;
            if (cursor is null)
            {
                result = TtlListResult(firstTtl, Entry("skill://first/unit-converter/"));
                result["nextCursor"] = "second";
            }
            else if (cursor == "second")
            {
                clock.Advance(TimeSpan.FromMilliseconds(200));
                result = TtlListResult(secondTtl, Entry("skill://second/unit-converter/"));
                result["nextCursor"] = "third";
            }
            else
            {
                clock.Advance(TimeSpan.FromMilliseconds(200));
                result = TtlListResult(thirdTtl, Entry("skill://third/unit-converter/"));
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);

        // Act
        var first = await loader.DiscoverAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromMilliseconds(remaining - 1));
        var fresh = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Same(first, fresh);
        Assert.Equal(3, first.Count);
        Assert.Equal(3, cursors.Count);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var refreshed = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal([null, "second", "third", null, "second", "third"], cursors);
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData(null, true)]
    [InlineData(0L, false)]
    [InlineData(0L, true)]
    [InlineData(-1L, false)]
    [InlineData(-1L, true)]
    public async Task DiscoverAsync_StaleEmptyPage_PreventsCachingWholeCatalogAsync(long? ttl, bool emptyFirstPage)
    {
        // Arrange
        int calls = 0;
        var client = CreateTtlClient((request, _) =>
        {
            calls++;
            bool firstPage = request.Params?["cursor"] is null;
            JsonObject result = firstPage == emptyFirstPage ? TtlListResult(ttl) : TtlListResult(1000, Entry());
            if (firstPage)
            {
                result["nextCursor"] = "next";
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object);

        // Act
        await loader.DiscoverAsync(CancellationToken.None);
        await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Equal(4, calls);
    }

    [Fact]
    public async Task DiscoverAsync_PageExpiresDuringPagination_DoesNotRestartItsClockAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((request, _) =>
        {
            calls++;
            JsonObject result = TtlListResult(1000);
            if (request.Params?["cursor"] is null)
            {
                result["nextCursor"] = "next";
            }
            else
            {
                clock.Advance(TimeSpan.FromSeconds(2));
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);

        // Act
        await loader.DiscoverAsync(CancellationToken.None);
        await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Equal(4, calls);
    }

    [Fact]
    public async Task DiscoverAsync_SlowRequest_TtlStartsAtResponseReceiptAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            calls++;
            clock.Advance(TimeSpan.FromSeconds(2));
            return Task.FromResult(TtlListResult(1000));
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);

        // Act
        var first = await loader.DiscoverAsync(CancellationToken.None);
        var second = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Same(first, second);
        Assert.Equal(1, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_ConcurrentCalls_ShareSuccessfulFreshDiscoveryAsync(bool refresh)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            calls++;
            return refresh && calls == 1 ? Task.FromResult(TtlListResult(1000, Entry())) : release.Task;
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);
        if (refresh)
        {
            await loader.DiscoverAsync(CancellationToken.None);
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        // Act
        Task<IList<AgentSkill>>[] pending = Enumerable.Range(0, 8)
            .Select(_ => loader.DiscoverAsync(CancellationToken.None)).ToArray();
        release.SetResult(TtlListResult(1000, Entry()));
        var results = await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.All(results, result => Assert.Same(results[0], result));
        Assert.Equal(refresh ? 2 : 1, calls);
    }

    [Fact]
    public async Task DiscoverAsync_ConcurrentCalls_ZeroTtlDoesNotShareStaleCatalogAsync()
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
            ++calls == 1 ? release.Task : Task.FromResult(TtlListResult(0, Entry())));
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: new ManualTimeProvider());

        // Act
        Task<IList<AgentSkill>>[] pending = Enumerable.Range(0, 8)
            .Select(_ => loader.DiscoverAsync(CancellationToken.None)).ToArray();

        // Assert
        Assert.Equal(1, calls);

        // Act
        release.SetResult(TtlListResult(0, Entry()));
        var results = await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(pending.Length, calls);
        for (int i = 1; i < results.Length; i++)
        {
            Assert.NotSame(results[0], results[i]);
        }
    }

    [Fact]
    public async Task DiscoverAsync_CanceledWaiter_DoesNotCancelSharedDiscoveryAsync()
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        var client = CreateTtlClient((_, token) =>
        {
            calls++;
            return release.Task.WaitAsync(token);
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: new ManualTimeProvider());
        using var cts = new CancellationTokenSource();

        // Act
        var initiating = loader.DiscoverAsync(CancellationToken.None);
        var waiting = loader.DiscoverAsync(cts.Token);
        await cts.CancelAsync();
        try
        {
            // Assert
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => waiting.WaitAsync(TimeSpan.FromSeconds(10)));
        }
        finally
        {
            release.SetResult(TtlListResult(1000, Entry()));
        }

        var first = await initiating.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Same(first, await loader.DiscoverAsync(CancellationToken.None));
        Assert.Equal(1, calls);
    }

    [Fact]
    public async Task DiscoverAsync_CanceledInitiator_WaiterRetriesDiscoveryAsync()
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        var client = CreateTtlClient((_, token) =>
            ++calls == 1 ? release.Task.WaitAsync(token) : Task.FromResult(TtlListResult(1000, Entry())));
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: new ManualTimeProvider());
        using var cts = new CancellationTokenSource();

        // Act
        var initiating = loader.DiscoverAsync(cts.Token);
        var waiting = loader.DiscoverAsync(CancellationToken.None);
        await cts.CancelAsync();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => initiating.WaitAsync(TimeSpan.FromSeconds(10)));
        var skills = await waiting.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Single(skills);
        Assert.Same(skills, await loader.DiscoverAsync(CancellationToken.None));
        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_CanceledToken_DoesNotDiscoverOrReturnFreshCacheAsync(bool cached)
    {
        // Arrange
        var client = CreateTtlClient((_, _) => Task.FromResult(TtlListResult(1000, Entry())));
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: new ManualTimeProvider());
        if (cached)
        {
            await loader.DiscoverAsync(CancellationToken.None);
        }

        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => loader.DiscoverAsync(cts.Token));
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Exactly(cached ? 1 : 0));
    }

    [Theory]
    [InlineData("request", typeof(McpException))]
    [InlineData("page", typeof(JsonException))]
    [InlineData("entry", typeof(InvalidOperationException))]
    [InlineData("manifest", typeof(InvalidOperationException))]
    public async Task DiscoverAsync_FailedRefresh_PropagatesAndRetriesWithoutServingStaleCatalogAsync(string failure, Type exceptionType)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            if (++calls == 2)
            {
                JsonObject invalidManifest = Entry();
                invalidManifest["resources"]![0]!["digest"] = "invalid";
                return failure switch
                {
                    "request" => Task.FromException<JsonObject>(new McpException("Discovery unavailable.")),
                    "page" => Task.FromResult(new JsonObject { ["ttlMs"] = 1000 }),
                    "entry" => Task.FromResult(TtlListResult(1000, Entry(), Entry("skill://invalid-name/"))),
                    "manifest" => Task.FromResult(TtlListResult(1000, Entry(), invalidManifest)),
                    _ => throw new ArgumentOutOfRangeException(nameof(failure)),
                };
            }

            return Task.FromResult(TtlListResult(1000, Entry()));
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);
        var first = await loader.DiscoverAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(1));

        // Act & Assert
        await Assert.ThrowsAsync(exceptionType, () => loader.DiscoverAsync(CancellationToken.None));
        var refreshed = await loader.DiscoverAsync(CancellationToken.None);
        Assert.NotSame(first, refreshed);
        Assert.Equal(3, calls);
        Assert.Same(refreshed, await loader.DiscoverAsync(CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_CanceledRefreshAfterResponse_DoesNotCacheReplacementAsync(bool laterPage)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        using var cts = new CancellationTokenSource();
        int calls = 0;
        List<string?> cursors = [];
        var client = CreateTtlClient((request, _) =>
        {
            string? cursor = request.Params?["cursor"]?.GetValue<string>();
            cursors.Add(cursor);
            if (++calls == (laterPage ? 4 : 2))
            {
                cts.Cancel();
            }

            JsonObject result = TtlListResult(1000, Entry());
            if (laterPage && cursor is null)
            {
                result["nextCursor"] = "next";
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);
        var first = await loader.DiscoverAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(1));

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => loader.DiscoverAsync(cts.Token));
        var refreshed = await loader.DiscoverAsync(CancellationToken.None);
        Assert.NotSame(first, refreshed);
        Assert.Equal(laterPage ? 6 : 3, calls);
        Assert.Equal(laterPage ? [null, "next", null, "next", null, "next"] : new string?[] { null, null, null }, cursors);
        Assert.Same(refreshed, await loader.DiscoverAsync(CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_TtlRefresh_ReplacesCatalogAsync(bool empty)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            if (++calls == 1)
            {
                return Task.FromResult(TtlListResult(1000, Entry(), Entry("skill://removed/unit-converter/")));
            }

            JsonObject updated = Entry();
            updated["frontmatter"]!["description"] = "Updated description.";
            JsonObject added = Entry("skill://added/unit-converter/");
            added["frontmatter"]!["description"] = "Added skill.";
            return Task.FromResult(empty ? TtlListResult(1000) : TtlListResult(1000, updated, added));
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);
        var first = await loader.DiscoverAsync(CancellationToken.None);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var refreshed = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal(2, first.Count);
        Assert.All(first, skill => Assert.Equal("Convert units.", skill.Frontmatter.Description));
        if (empty)
        {
            Assert.Empty(refreshed);
        }
        else
        {
            Assert.Equal(["Updated description.", "Added skill."], refreshed.Select(skill => skill.Frontmatter.Description));
            Assert.All(refreshed, skill => Assert.DoesNotContain(skill, first));
        }

        Assert.Same(refreshed, await loader.DiscoverAsync(CancellationToken.None));
        Assert.Equal(2, calls);
    }

    [Fact]
    public async Task DiscoverAsync_InvalidLaterRefreshPage_DoesNotCachePartialCatalogAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<string?> cursors = [];
        var client = CreateTtlClient((request, _) =>
        {
            string? cursor = request.Params?["cursor"]?.GetValue<string>();
            cursors.Add(cursor);
            JsonObject result = cursor is null ? TtlListResult(1000, Entry()) : TtlListResult(1000);
            if (cursor is null)
            {
                result["nextCursor"] = "next";
            }
            else if (cursors.Count == 4)
            {
                result.Remove("skills");
            }

            return Task.FromResult(result);
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);
        var first = await loader.DiscoverAsync(CancellationToken.None);
        clock.Advance(TimeSpan.FromSeconds(1));

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => loader.DiscoverAsync(CancellationToken.None));
        var refreshed = await loader.DiscoverAsync(CancellationToken.None);
        Assert.Single(refreshed);
        Assert.NotSame(first, refreshed);
        Assert.Equal([null, "next", null, "next", null, "next"], cursors);
        Assert.Same(refreshed, await loader.DiscoverAsync(CancellationToken.None));
    }

    [Fact]
    public async Task DiscoverAsync_TtlRefresh_PreservesPreviouslyReturnedManifestAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            JsonObject entry = Entry();
            if (++calls > 1)
            {
                entry["resources"]![1]!["uri"] = "skill://unit-converter/references/updated.md";
            }

            return Task.FromResult(TtlListResult(1000, entry));
        });
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: clock);
        var first = Assert.Single(await loader.DiscoverAsync(CancellationToken.None));

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var updated = Assert.Single(await loader.DiscoverAsync(CancellationToken.None));

        // Assert
        Assert.NotSame(first, updated);
        Assert.Null(await first.GetResourceAsync("references/updated.md"));
        Assert.Null(await updated.GetResourceAsync("references/checklist.md"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DiscoverAsync_DisposedLoader_ThrowsWithoutDisposingClientAsync(bool cached)
    {
        // Arrange
        var client = CreateTtlClient((_, _) => Task.FromResult(TtlListResult(1000, Entry())));
        using var loader = new McpListedSkillsLoader(client.Object, timeProvider: new ManualTimeProvider());
        if (cached)
        {
            await loader.DiscoverAsync(CancellationToken.None);
        }

        // Act
        loader.Dispose();
        loader.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => loader.DiscoverAsync(CancellationToken.None));
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Exactly(cached ? 1 : 0));
        client.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task GetSkillsAsync_DisposedSource_DisposesLoaderButNotClientAsync()
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            return ValueTask.FromResult<JsonNode?>(TtlListResult(60000, Entry()));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        source.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        using var anotherSource = new AgentMcpSkillsSource(client);
        Assert.Single(await anotherSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(true, 60000L, 1)]
    [InlineData(true, 0L, 2)]
    [InlineData(false, 0L, 1)]
    public async Task UseMcpSkills_DisableCaching_LetsSourceApplyTtlAsync(bool disableCaching, long ttl, int expectedCalls)
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            return ValueTask.FromResult<JsonNode?>(TtlListResult(ttl, Entry()));
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, SkillContent));
        });
        await using var client = await server.CreateClientAsync();
        var builder = new AgentSkillsProviderBuilder().UseMcpSkills(client);
        if (disableCaching)
        {
            builder.DisableCaching();
        }

        using var provider = builder.Build();
        var context = new AIContextProvider.InvokingContext(TestAgentSkillsSourceContextFactory.Create().Agent, session: null, new AIContext());

        // Act
        var first = await provider.InvokingAsync(context, CancellationToken.None);
        var second = await provider.InvokingAsync(context, CancellationToken.None);

        // Assert
        Assert.Contains("unit-converter", first.Instructions);
        Assert.Contains("unit-converter", second.Instructions);
        Assert.Equal(expectedCalls, calls);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData(60000L, 1)]
    [InlineData(0L, 2)]
    [InlineData(null, 2)]
    public async Task AgentSkillsProvider_MixedSources_CachesDecoratedSourceAndHonorsMcpTtlAsync(long? ttl, int expectedCalls)
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            return ValueTask.FromResult<JsonNode?>(TtlListResult(ttl, Entry()));
        });
        await using var client = await server.CreateClientAsync();
        var otherSource = new Mock<AgentSkillsSource>();
        otherSource.Setup(source => source.GetSkillsAsync(It.IsAny<AgentSkillsSourceContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync([new AgentInlineSkill("local-skill", "A local skill.", "Local instructions.")]);
        var source = new AggregatingAgentSkillsSource(
        [
            new CachingAgentSkillsSource(otherSource.Object),
            new AgentMcpSkillsSource(client),
        ]);
        using var provider = new AgentSkillsProvider(source, ownsSource: true);
        var context = new AIContextProvider.InvokingContext(TestAgentSkillsSourceContextFactory.Create().Agent, session: null, new AIContext());

        // Act
        var first = await provider.InvokingAsync(context, CancellationToken.None);
        var second = await provider.InvokingAsync(context, CancellationToken.None);

        // Assert
        Assert.Contains("local-skill", first.Instructions);
        Assert.Contains("unit-converter", first.Instructions);
        Assert.Contains("local-skill", second.Instructions);
        Assert.Contains("unit-converter", second.Instructions);
        Assert.Equal(expectedCalls, calls);
        otherSource.Verify(source => source.GetSkillsAsync(It.IsAny<AgentSkillsSourceContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    private static JsonObject TtlListResult(long? ttl, params JsonNode?[] entries)
    {
        JsonObject result = ListResult(entries);
        if (ttl is not null)
        {
            result["ttlMs"] = ttl.Value;
        }

        return result;
    }

    private static Mock<McpClient> CreateTtlClient(Func<JsonRpcRequest, CancellationToken, Task<JsonObject>> handler)
    {
        var client = new Mock<McpClient>();
        client.Setup(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()))
            .Returns((JsonRpcRequest request, CancellationToken token) => RespondAsync(request, token));
        return client;

        async Task<JsonRpcResponse> RespondAsync(JsonRpcRequest request, CancellationToken token) =>
            new() { Id = request.Id, Result = await handler(request, token) };
    }

    private sealed class ManualTimeProvider : TimeProvider
    {
        private long _timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => Interlocked.Read(ref this._timestamp);

        public void Advance(TimeSpan duration) => Interlocked.Add(ref this._timestamp, duration.Ticks);
    }
}
