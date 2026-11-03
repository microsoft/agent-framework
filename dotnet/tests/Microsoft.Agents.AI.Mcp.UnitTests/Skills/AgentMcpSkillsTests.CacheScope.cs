// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillsTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_PartitionLimit_DefaultsTo100AndNullAllowsUnlimitedAsync(bool unlimited)
    {
        // Arrange
        string key = "";
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            CacheIsolationKeySelector = (_, _) => new(key),
        };
        if (unlimited)
        {
            options.MaxCachedPartitions = null;
        }

        Assert.Equal(unlimited ? null : 100, options.MaxCachedPartitions);
        Assert.Equal(unlimited ? null : 100, options.ToMemoryCacheOptions().SizeLimit);
        using var source = new AgentMcpSkillsSource(client.Object, options, null, new ManualTimeProvider());

        // Act & Assert
        for (int i = 0; i < 100; i++)
        {
            key = $"user-{i}";
            var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
            Assert.Same(skills, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        }

        Assert.Equal(100, lists);
        key = "user-100";
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        Assert.Same(first, second);
        Assert.Equal(101, lists);
        if (unlimited)
        {
            for (int i = 0; i < 100; i++)
            {
                key = $"user-{i}";
                await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
            }

            Assert.Equal(101, lists);
        }
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(19)]
    [InlineData(20)]
    [InlineData(100)]
    public async Task GetSkillsAsync_FullPartitionCache_EvictsLeastRecentlyUsedAndCachesNewKeyAsync(int limit)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        string key = "";
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new(key),
            MaxCachedPartitions = limit,
        }, null, clock);
        var partitions = new List<IList<AgentSkill>>();
        for (int i = 0; i < limit; i++)
        {
            key = $"user-{i}";
            partitions.Add(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        key = $"user-{limit - 1}";
        Assert.Same(partitions[limit - 1], await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        clock.Advance(TimeSpan.FromMilliseconds(1));

        // Act
        key = "new-user";
        var added = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Same(added, reused);
        Assert.Equal(limit + 1, lists);
        if (limit > 1)
        {
            key = $"user-{limit - 1}";
            Assert.Same(partitions[limit - 1], await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            Assert.Equal(limit + 1, lists);
        }

        key = "user-0";
        Assert.NotSame(partitions[0], await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(limit + 2, lists);
    }

    [Fact]
    public async Task GetSkillsAsync_ZeroPartitionLimit_DoesNotCachePartitionsAsync()
    {
        // Arrange
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new("A"),
            MaxCachedPartitions = 0,
        });

        // Act
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, second);
        Assert.Equal(2, lists);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(0)]
    [InlineData(100)]
    public async Task GetSkillsAsync_PartitionLimitChangedAfterConstruction_UsesOriginalLimitAsync(int? updatedLimit)
    {
        // Arrange
        string key = "A";
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            CacheIsolationKeySelector = (_, _) => new(key),
            MaxCachedPartitions = 1,
        };
        using var source = new AgentMcpSkillsSource(client.Object, options);
        await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        options.MaxCachedPartitions = updatedLimit;

        // Act
        key = "B";
        var added = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Same(added, reused);
        Assert.Equal(2, lists);
    }

    [Theory]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.MaxCachedPartitions), -1)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.PartitionSlidingExpiration), 0)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.PartitionSlidingExpiration), -1)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.PartitionAbsoluteExpiration), 0)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.PartitionAbsoluteExpiration), -1)]
    public void Constructor_InvalidPartitionRetention_Throws(string option, int value)
    {
        // Arrange
        var client = CreateSkillsClient();
        var options = new AgentMcpSkillsSourceOptions
        {
            MaxCachedPartitions = option == nameof(AgentMcpSkillsSourceOptions.MaxCachedPartitions) ? value : null,
            PartitionSlidingExpiration = option == nameof(AgentMcpSkillsSourceOptions.PartitionSlidingExpiration) ? TimeSpan.FromSeconds(value) : null,
            PartitionAbsoluteExpiration = option == nameof(AgentMcpSkillsSourceOptions.PartitionAbsoluteExpiration) ? TimeSpan.FromSeconds(value) : null,
        };

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new AgentMcpSkillsSource(client.Object, options));
    }

    [Fact]
    public async Task GetSkillsAsync_PartitionSlidingExpiration_ExtendsOnDiscoveryButNotResourceReadsAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int lists = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                lists++;
                return Task.FromResult(TtlListResult(60000, Entry()));
            }

            return Task.FromResult(ResourceReadResult(SkillUri, 60000, SkillContent));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new("A"),
            PartitionSlidingExpiration = TimeSpan.FromSeconds(10),
        }, null, clock);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act & Assert
        clock.Advance(TimeSpan.FromSeconds(9));
        Assert.Same(first, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        clock.Advance(TimeSpan.FromSeconds(9));
        Assert.Equal(SkillContent, await first[0].GetContentAsync());
        clock.Advance(TimeSpan.FromSeconds(1));
        var replacement = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        Assert.NotSame(first, replacement);
        Assert.NotSame(first[0], replacement[0]);
        Assert.Same(replacement, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(SkillContent, await first[0].GetContentAsync());
        Assert.Equal(2, lists);
        client.Verify(c => c.DisposeAsync(), Times.Never);
    }

    [Fact]
    public async Task GetSkillsAsync_PartitionAbsoluteExpiration_ExpiresDespiteDiscoveryAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new("A"),
            PartitionSlidingExpiration = TimeSpan.FromSeconds(10),
            PartitionAbsoluteExpiration = TimeSpan.FromSeconds(25),
        }, null, clock);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act & Assert
        clock.Advance(TimeSpan.FromSeconds(9));
        Assert.Same(first, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        clock.Advance(TimeSpan.FromSeconds(9));
        Assert.Same(first, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        clock.Advance(TimeSpan.FromSeconds(7));
        Assert.NotSame(first, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(2, lists);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_PartitionRetention_DoesNotChangeResponseTtlAsync(bool partitioned)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(1000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = partitioned ? (_, _) => new("A") : null,
            PartitionSlidingExpiration = TimeSpan.FromSeconds(10),
            PartitionAbsoluteExpiration = TimeSpan.FromSeconds(20),
        }, null, clock);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal(2, lists);
    }

    [Fact]
    public async Task GetSkillsAsync_PartitionRetention_DoesNotEvictDefaultPartitionAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            MaxCachedPartitions = 1,
            PartitionSlidingExpiration = TimeSpan.FromSeconds(1),
            PartitionAbsoluteExpiration = TimeSpan.FromSeconds(1),
        }, null, clock);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromSeconds(2));
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Same(first, reused);
        Assert.Equal(1, lists);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_PartitionEviction_PreservesInFlightDiscoveryAsync(bool capacity)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        string key = "A";
        int lists = 0;
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                return Interlocked.Increment(ref lists) == 1
                    ? release.Task
                    : Task.FromResult(TtlListResult(60000, Entry()));
            }

            return Task.FromResult(ResourceReadResult(SkillUri, 60000, SkillContent));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new(key),
            MaxCachedPartitions = capacity ? 1 : null,
            PartitionAbsoluteExpiration = capacity ? null : TimeSpan.FromSeconds(1),
        }, null, clock);
        Task<IList<AgentSkill>> first = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        key = capacity ? "B" : "A";
        try
        {
            var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()).WaitAsync(TimeSpan.FromSeconds(10));

            // Assert
            Assert.False(first.IsCompleted);
            Assert.Single(second);
            Assert.Equal(SkillContent, await second[0].GetContentAsync());
            Assert.Equal(2, lists);
        }
        finally
        {
            release.TrySetResult(TtlListResult(60000, Entry()));
        }

        var retained = await first.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(SkillContent, await retained[0].GetContentAsync());
        client.Verify(c => c.DisposeAsync(), Times.Never);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetSkillsAsync_PrivateScopeWithoutPartitionKey_FailsAndRetriesWholeListingAsync(bool firstPagePrivate)
    {
        // Arrange
        bool returnPrivate = true;
        int calls = 0;
        var client = CreateTtlClient((request, _) =>
        {
            calls++;
            bool firstPage = request.Params?["cursor"] is null;
            var result = TtlListResult(60000, Entry());
            result["cacheScope"] = returnPrivate && (firstPagePrivate || !firstPage) ? "private" : "public";
            if (firstPage && !firstPagePrivate)
            {
                result["nextCursor"] = "last";
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object);

        // Act & Assert
        for (int attempt = 0; attempt < 2; attempt++)
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            Assert.Contains("skills/list", error.Message);
            Assert.Contains("private", error.Message);
            Assert.Contains(nameof(AgentMcpSkillsSourceOptions.CacheIsolationKeySelector), error.Message);
        }

        Assert.Equal(firstPagePrivate ? 2 : 4, calls);
        returnPrivate = false;
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        Assert.NotEmpty(skills);
        Assert.Same(skills, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(firstPagePrivate ? 3 : 6, calls);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, false)]
    [InlineData(true, true)]
    [InlineData(false, true)]
    public async Task GetSkillsAsync_PublicListingWithPrivateResourceWithoutPartitionKey_ThrowsWithoutCachingAsync(bool instructions, bool cachedPublic)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        bool returnPrivate = !cachedPublic;
        int reads = 0;
        int lists = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                lists++;
                var listing = TtlListResult(60000, Entry());
                listing["cacheScope"] = "public";
                return Task.FromResult(listing);
            }

            reads++;
            string uri = request.Params!["uri"]!.GetValue<string>();
            var result = ResourceReadResult(uri, 1000, uri == SkillUri ? SkillContent : "Checklist.");
            result["cacheScope"] = returnPrivate ? "private" : "public";
            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, null, null, clock);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        if (cachedPublic)
        {
            await ReadSkillContentAsync(skill, instructions);
            clock.Advance(TimeSpan.FromSeconds(1));
            returnPrivate = true;
        }

        // Act & Assert
        for (int attempt = 0; attempt < 2; attempt++)
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() => ReadSkillContentAsync(skill, instructions));
            Assert.Contains("resources/read", error.Message);
            Assert.Contains(nameof(AgentMcpSkillsSourceOptions.CacheIsolationKeySelector), error.Message);
            Assert.Same(skill, Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));
        }

        returnPrivate = false;
        await ReadSkillContentAsync(skill, instructions);
        await ReadSkillContentAsync(skill, instructions);
        Assert.Equal(cachedPublic ? 4 : 3, reads);
        Assert.Equal(1, lists);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_PrivateMetadataScope_RequiresPartitionKeyAsync(bool partitioned)
    {
        // Arrange
        bool returnPrivate = true;
        int gets = 0;
        var client = CreateTtlClient((request, _) =>
        {
            JsonObject result;
            switch (request.Method)
            {
                case "skills/list":
                    result = TtlListResult(60000, Entry());
                    result["cacheScope"] = "public";
                    break;
                case "skills/get":
                    gets++;
                    result = GetSkillResult(Entry());
                    result["cacheScope"] = returnPrivate ? "private" : "public";
                    break;
                default:
                    result = ResourceReadResult(SkillUri, 1000, SkillContent + "\nChanged.");
                    break;
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, partitioned ? new()
        {
            CacheIsolationKeySelector = (_, _) => new("authorization-context"),
        } : null);
        var original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());

        // Act & Assert
        if (!partitioned)
        {
            for (int attempt = 0; attempt < 2; attempt++)
            {
                var error = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
                Assert.Contains("skills/get", error.Message);
                Assert.Contains(nameof(AgentMcpSkillsSourceOptions.CacheIsolationKeySelector), error.Message);
            }

            returnPrivate = false;
        }

        var refreshed = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.NotSame(original, refreshed);
        Assert.Same(refreshed, Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));
        Assert.Equal(partitioned ? 1 : 3, gets);
    }

    [Fact]
    public async Task GetSkillsAsync_ChangingSelector_DoesNotChangeRetainedCachePartitionAsync()
    {
        // Arrange
        var options = new AgentMcpSkillsSourceOptions();
        var client = CreateTtlClient((request, _) =>
        {
            var result = request.Method == "skills/list"
                ? TtlListResult(60000, Entry())
                : ResourceReadResult(SkillUri, 60000, SkillContent);
            result["cacheScope"] = request.Method == "skills/list" ? "public" : "private";
            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, options);
        var unkeyed = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        options.CacheIsolationKeySelector = (_, _) => new("authorization-context");
        var keyed = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await unkeyed.GetContentAsync());
        Assert.Equal(SkillContent, await keyed.GetContentAsync());
        options.CacheIsolationKeySelector = null;
        Assert.Same(unkeyed, Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await unkeyed.GetContentAsync());
        Assert.Equal(SkillContent, await keyed.GetContentAsync());
    }

    [Fact]
    public async Task GetSkillsAsync_SharedClient_FetchesAndCachesContextSpecificContentAsync()
    {
        // Arrange
        var authorizationKey = new AsyncLocal<string?> { Value = "A" };
        int lists = 0;
        int reads = 0;
        var client = CreateTtlClient((request, _) =>
        {
            string content = SkillContent + "\n" + authorizationKey.Value;
            if (request.Method == "skills/list")
            {
                lists++;
                var result = TtlListResult(60000, Entry(content: content));
                result["cacheScope"] = "private";
                return Task.FromResult(result);
            }

            reads++;
            return Task.FromResult(ResourceReadResult(SkillUri, 60000, content));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new(authorizationKey.Value!),
        });

        // Act
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        string firstContent = await first[0].GetContentAsync();
        authorizationKey.Value = "B";
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        string secondContent = await second[0].GetContentAsync();
        authorizationKey.Value = "A";
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal(SkillContent + "\nA", firstContent);
        Assert.Equal(SkillContent + "\nB", secondContent);
        Assert.Equal(firstContent, await reused[0].GetContentAsync());
        Assert.Same(first, reused);
        Assert.Equal(2, lists);
        Assert.Equal(2, reads);
    }

    [Fact]
    public async Task GetSkillsAsync_OptionsChangedAfterConstruction_NewPartitionUsesUpdatedOptionsAsync()
    {
        // Arrange
        var client = CreateTtlClient((_, _) => Task.FromResult(TtlListResult(60000, Entry())));
        var options = new AgentMcpSkillsSourceOptions { CacheIsolationKeySelector = (_, _) => new("A") };
        using var source = new AgentMcpSkillsSource(client.Object, options);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        options.CacheIsolationKeySelector = (_, _) => new("B");
        options.TtlResolver = _ => TimeSpan.Zero;

        // Act
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        options.CacheIsolationKeySelector = (_, _) => new("A");
        var original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, second);
        Assert.NotSame(second, reused);
        Assert.Same(first, original);
    }

    [Fact]
    public async Task GetSkillsAsync_DisposedDuringKeySelection_DoesNotCreateNewPartitionAsync()
    {
        // Arrange
        Action? duringSelection = null;
        var client = CreateTtlClient((_, _) => Task.FromResult(TtlListResult(60000, Entry())));
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) =>
            {
                duringSelection?.Invoke();
                return new("A");
            },
        });
        duringSelection = source.Dispose;

        // Act & Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData("public", "private")]
    [InlineData("private", "public")]
    [InlineData("public", "public")]
    [InlineData("private", "private")]
    [InlineData(null, null)]
    public async Task GetSkillsAsync_PartitionKeys_SeparateSkillsAndAllResourceCachesAsync(string? listScope, string? resourceScope)
    {
        // Arrange
        string key = "authorization-A";
        int lists = 0;
        int reads = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                lists++;
                JsonObject listing = TtlListResult(60000, Entry());
                listing["cacheScope"] = listScope;
                return Task.FromResult(listing);
            }

            reads++;
            string uri = request.Params!["uri"]!.GetValue<string>();
            JsonObject result = ResourceReadResult(uri, 60000, uri == SkillUri ? SkillContent : "Checklist.");
            result["cacheScope"] = resourceScope;
            if (uri.EndsWith("icon.bin", StringComparison.Ordinal))
            {
                result["contents"] = new JsonArray(new JsonObject
                {
                    ["uri"] = uri,
                    ["blob"] = Convert.ToBase64String([1, 2, 3, 4]),
                });
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new(key) });

        // Act
        IList<AgentSkill> first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        await ReadSkillContentAsync(first[0], instructions: true);
        await ReadSkillContentAsync(first[0], instructions: false);
        var firstBinary = Assert.IsType<AgentMcpSkillResource>(await first[0].GetResourceAsync("assets/icon.bin"));
        Assert.Equal(new byte[] { 1, 2, 3, 4 }, Assert.IsType<DataContent>(await firstBinary.ReadAsync()).Data.ToArray());
        key = "authorization-B";
        IList<AgentSkill> second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        await ReadSkillContentAsync(second[0], instructions: true);
        await ReadSkillContentAsync(second[0], instructions: false);
        var secondBinary = Assert.IsType<AgentMcpSkillResource>(await second[0].GetResourceAsync("assets/icon.bin"));
        Assert.Equal(new byte[] { 1, 2, 3, 4 }, Assert.IsType<DataContent>(await secondBinary.ReadAsync()).Data.ToArray());
        key = "authorization-A";
        IList<AgentSkill> reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        await ReadSkillContentAsync(reused[0], instructions: true);
        await ReadSkillContentAsync(reused[0], instructions: false);
        await reused[0].GetResourceAsync("assets/icon.bin");

        // Assert
        Assert.Same(first, reused);
        Assert.NotSame(first, second);
        Assert.NotSame(first[0], second[0]);
        Assert.Equal(2, lists);
        Assert.Equal(6, reads);
    }

    [Fact]
    public async Task GetSkillsAsync_PartitionKeys_CompareOrdinallyAsync()
    {
        // Arrange
        string key = "context";
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new(key) });

        // Act
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        key = "CONTEXT";
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        key = "context";
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, second);
        Assert.Same(first, reused);
        Assert.Equal(2, lists);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" \t")]
    public async Task GetSkillsAsync_InvalidPartitionKey_ThrowsWithoutRequestsAsync(string? key)
    {
        // Arrange
        var client = CreateSkillsClient();
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new(key!) });

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task GetSkillsAsync_AsyncPartitionKeySelector_AwaitsKeyAndReusesPartitionAsync()
    {
        // Arrange
        var context = TestAgentSkillsSourceContextFactory.Create();
        using var cts = new CancellationTokenSource();
        var release = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        int selections = 0;
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            Interlocked.Increment(ref lists);
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = async (actualContext, cancellationToken) =>
            {
                Assert.Same(context, actualContext);
                Assert.Equal(cts.Token, cancellationToken);
                Interlocked.Increment(ref selections);
                return await release.Task.WaitAsync(cancellationToken);
            },
        });

        // Act
        var first = source.GetSkillsAsync(context, cts.Token);
        var second = source.GetSkillsAsync(context, cts.Token);

        // Assert
        Assert.False(first.IsCompleted);
        Assert.False(second.IsCompleted);
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Never);

        // Act
        release.SetResult("A");
        var results = await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(10));
        var reused = await source.GetSkillsAsync(context, cts.Token);

        // Assert
        Assert.Single(reused);
        Assert.Same(results[0], results[1]);
        Assert.Same(results[0], reused);
        Assert.Equal(3, selections);
        Assert.Equal(1, lists);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_CanceledDuringAsyncKeySelection_ThrowsWithoutRequestsAsync(bool selectorObservesCancellation)
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        var release = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = CreateSkillsClient();
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, cancellationToken) =>
            {
                Assert.Equal(cts.Token, cancellationToken);
                return new(selectorObservesCancellation ? release.Task.WaitAsync(cancellationToken) : release.Task);
            },
        });

        // Act
        var discovery = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), cts.Token);
        Assert.False(discovery.IsCompleted);
        await cts.CancelAsync();
        release.SetResult("A");

        // Assert
        var error = await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => discovery.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.Equal(cts.Token, error.CancellationToken);
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task GetSkillsAsync_DisposedDuringAsyncKeySelection_ThrowsWithoutRequestsAsync()
    {
        // Arrange
        var release = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = CreateSkillsClient();
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new(release.Task),
        });

        // Act
        var discovery = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        Assert.False(discovery.IsCompleted);
        source.Dispose();
        release.SetResult("A");

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => discovery.WaitAsync(TimeSpan.FromSeconds(10)));
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_PartitionKeySelectorError_PropagatesWithoutRequestsAsync(bool asynchronous)
    {
        // Arrange
        var error = new InvalidOperationException("Authorization context unavailable.");
        var client = CreateSkillsClient();
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => asynchronous ? new(Task.FromException<string>(error)) : throw error,
        });

        // Act
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Same(error, actual);
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_PartitionKeySelector_SkippedWithoutSupportOrWhenCanceledAsync(bool canceled)
    {
        // Arrange
        var client = CreateSkillsClient();
        if (!canceled)
        {
            client.Object.ServerCapabilities.Extensions = null;
        }

        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => throw new InvalidOperationException("Must not run."),
        });
        using var cts = new CancellationTokenSource();

        // Act & Assert
        if (canceled)
        {
            await cts.CancelAsync();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), cts.Token));
        }
        else
        {
            Assert.Empty(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        }
    }

    [Fact]
    public async Task GetSkillsAsync_CachePartitions_ExpireIndependentlyAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        string key = "A";
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(1000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new(key) }, null, clock);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        clock.Advance(TimeSpan.FromMilliseconds(500));
        key = "B";
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(500));
        key = "A";
        var refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        key = "B";
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Same(second, reused);
        Assert.Equal(3, lists);
    }

    [Fact]
    public async Task GetSkillsAsync_CachePartitions_KeepMismatchFallbackAndMetadataRefreshSeparateAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        string key = "A";
        bool changed = false;
        int gets = 0;
        int reads = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(60000, Entry()));
            }

            if (request.Method == "skills/get")
            {
                gets++;
                return Task.FromResult(GetSkillResult(Entry(), 1000));
            }

            reads++;
            return Task.FromResult(ResourceReadResult(SkillUri, 1000, changed ? SkillContent + "\nChanged." : SkillContent));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new(key) }, null, clock);
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        await first[0].GetContentAsync();
        key = "B";
        var second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        clock.Advance(TimeSpan.FromSeconds(1));
        changed = true;
        key = "A";

        // Act
        Assert.Equal(SkillContent, await first[0].GetContentAsync());
        var refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        key = "B";
        var reused = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Same(second, reused);
        Assert.Equal(1, gets);
        Assert.Equal(2, reads);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        key = "A";
        Assert.Equal(SkillContent, await first[0].GetContentAsync());
        await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        key = "B";
        Assert.Same(second, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await second[0].GetContentAsync());

        // Assert
        Assert.Equal(2, gets);
        Assert.Equal(3, reads);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(2)]
    public async Task GetSkillsAsync_ConcurrentPartitionCreation_SharesPartitionPerKeyAsync(int? limit)
    {
        // Arrange
        var contextA = TestAgentSkillsSourceContextFactory.Create();
        var contextB = TestAgentSkillsSourceContextFactory.Create();
        var start = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            Interlocked.Increment(ref lists);
            return Task.FromResult(TtlListResult(60000, Entry()));
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (context, _) => new(ReferenceEquals(context, contextA) ? "A" : "B"),
            MaxCachedPartitions = limit,
        });
        Task<IList<AgentSkill>>[] requests = Enumerable.Range(0, 32).Select(index => Task.Run(async () =>
        {
            await start.Task;
            return await source.GetSkillsAsync(index % 2 == 0 ? contextA : contextB);
        })).ToArray();

        // Act
        start.SetResult();
        IList<AgentSkill>[] results = await Task.WhenAll(requests).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(2, lists);
        Assert.NotSame(results[0], results[1]);
        for (int i = 0; i < results.Length; i++)
        {
            Assert.Same(results[i % 2], results[i]);
        }
    }

    [Fact]
    public async Task GetSkillsAsync_ConcurrentCachePartitions_DoNotBlockEachOtherAsync()
    {
        // Arrange
        var contextA = TestAgentSkillsSourceContextFactory.Create();
        var contextB = TestAgentSkillsSourceContextFactory.Create();
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
            Interlocked.Increment(ref lists) == 1 ? release.Task : Task.FromResult(TtlListResult(60000, Entry())));
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (context, _) => new(ReferenceEquals(context, contextA) ? "A" : "B"),
        });

        // Act
        Task<IList<AgentSkill>> first = source.GetSkillsAsync(contextA);
        Task<IList<AgentSkill>> sameKey = source.GetSkillsAsync(contextA);
        try
        {
            var otherKey = await source.GetSkillsAsync(contextB).WaitAsync(TimeSpan.FromSeconds(10));

            // Assert
            Assert.Single(otherKey);
            Assert.False(first.IsCompleted);
            Assert.False(sameKey.IsCompleted);
            Assert.Equal(2, lists);
        }
        finally
        {
            release.TrySetResult(TtlListResult(60000, Entry()));
        }

        Assert.Same(await first, await sameKey);
        Assert.Equal(2, lists);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_CachePartitionDisposal_PreservesRetainedSkillsAndClientAsync(bool inFlight)
    {
        // Arrange
        string key = "A";
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        var client = CreateTtlClient((request, _) => request.Method == "skills/list"
            ? key == "B" && inFlight ? release.Task : Task.FromResult(TtlListResult(60000, Entry()))
            : Task.FromResult(ResourceReadResult(SkillUri, 60000, SkillContent)));
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new(key) });
        var first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        key = "B";
        var second = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        source.Dispose();
        source.Dispose();
        release.TrySetResult(TtlListResult(60000, Entry()));
        var retained = await second;

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        key = "A";
        Assert.Equal(SkillContent, await first[0].GetContentAsync());
        key = "B";
        Assert.Equal(SkillContent, await retained[0].GetContentAsync());
        client.Verify(c => c.DisposeAsync(), Times.Never);
    }

    [Theory]
    [InlineData("public", "private", 3)]
    [InlineData("private", "public", 2)]
    [InlineData(null, "private", 3)]
    [InlineData("private", null, 2)]
    public async Task GetSkillsAsync_ConflictingPageScopes_FailsAndRetriesWholeListingAsync(string? firstScope, string? lastScope, int callsPerAttempt)
    {
        // Arrange
        int calls = 0;
        var client = CreateTtlClient((request, _) =>
        {
            calls++;
            string? cursor = request.Params?["cursor"]?.GetValue<string>();
            var result = TtlListResult(60000);
            string? scope = cursor is null ? firstScope : lastScope;
            if (scope is not null)
            {
                result["cacheScope"] = scope;
            }
            if (cursor != "last")
            {
                result["nextCursor"] = cursor is null ? "missing-scope" : "last";
                if (cursor is not null)
                {
                    result.Remove("cacheScope");
                }
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, new() { CacheIsolationKeySelector = (_, _) => new("authorization-context") });

        // Act & Assert
        for (int attempt = 0; attempt < 2; attempt++)
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            Assert.Contains("cacheScope", error.Message);
        }

        Assert.Equal(2 * callsPerAttempt, calls);
    }

    [Theory]
    [InlineData("public")]
    public async Task GetSkillsAsync_PublicAndOmittedPageScopes_AcceptsListingAsync(string scope)
    {
        // Arrange
        int calls = 0;
        var client = CreateTtlClient((_, _) =>
        {
            var result = TtlListResult(60000);
            if (++calls != 2)
            {
                result["cacheScope"] = scope;
            }

            if (calls < 3)
            {
                result["nextCursor"] = calls.ToString(System.Globalization.CultureInfo.InvariantCulture);
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
        Assert.Same(skills, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(3, calls);
    }

    [Theory]
    [InlineData("skills/list", false)]
    [InlineData("skills/list", true)]
    [InlineData("skills/get", false)]
    [InlineData("skills/get", true)]
    [InlineData("resources/read", false)]
    [InlineData("resources/read", true)]
    public async Task GetSkillsAsync_UnspecifiedScope_DefaultsToPublicAndLogsDiagnosticsWithoutPartitionKeyAsync(string method, bool omitted)
    {
        // Arrange
        const string PartitionKey = "do-not-log-this-key";
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        var loggerFactory = new Mock<ILoggerFactory>();
        loggerFactory.Setup(f => f.CreateLogger(It.IsAny<string>())).Returns(logger.Object);
        var client = CreateTtlClient((request, _) =>
        {
            JsonObject result = request.Method switch
            {
                "skills/list" => TtlListResult(60000, Entry()),
                "skills/get" => GetSkillResult(Entry()),
                _ => ResourceReadResult(SkillUri, 60000, SkillContent),
            };
            if (request.Method == method)
            {
                if (omitted)
                {
                    result.Remove("cacheScope");
                }
                else
                {
                    result["cacheScope"] = null;
                }
            }
            else
            {
                result["cacheScope"] = "private";
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, new()
        {
            CacheIsolationKeySelector = (_, _) => new(PartitionKey),
        }, loggerFactory.Object);

        // Act
        var skill = Assert.IsType<AgentMcpSkill>(Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));
        if (method == "skills/get")
        {
            client.Setup(c => c.SendRequestAsync(It.Is<JsonRpcRequest>(r => r.Method == "resources/read"), It.IsAny<CancellationToken>()))
                .Returns((JsonRpcRequest request, CancellationToken _) => Task.FromResult(new JsonRpcResponse
                {
                    Id = request.Id,
                    Result = ResourceReadResult(SkillUri, 1000, SkillContent + "\nChanged."),
                }));
            await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        }
        else if (method == "resources/read")
        {
            Assert.Equal(SkillContent, await skill.GetContentAsync());
        }

        // Assert
        logger.Verify(l => l.Log(
            LogLevel.Debug,
            It.IsAny<EventId>(),
            It.Is<It.IsAnyType>((state, _) => state.ToString() ==
                $"The {method} response has a missing or null cacheScope; treating it as public."),
            It.IsAny<Exception?>(),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()), Times.Once());
        Assert.DoesNotContain(logger.Invocations, invocation => invocation.Arguments.Any(argument => argument?.ToString()?.Contains(PartitionKey, StringComparison.Ordinal) == true));
    }
}
