// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillsTests
{
    [Theory]
    [InlineData(null, 2000)]
    [InlineData(-1L, 2000)]
    [InlineData(0L, 2000)]
    [InlineData(1000L, 2000)]
    [InlineData(5000L, 2000)]
    [InlineData(5000L, 0)]
    [InlineData(5000L, -1000)]
    public async Task GetSkillsAsync_TtlResolver_OverridesServerTtlAsync(long? serverMilliseconds, int resolvedMilliseconds)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<TimeSpan?> inputs = [];
        int lists = 0;
        var client = CreateTtlClient((_, _) =>
        {
            lists++;
            return Task.FromResult(TtlListResult(serverMilliseconds, Entry()));
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl =>
            {
                inputs.Add(ttl);
                return TimeSpan.FromMilliseconds(resolvedMilliseconds);
            },
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);

        // Act
        IList<AgentSkill> first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        if (resolvedMilliseconds > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(resolvedMilliseconds - 1));
            IList<AgentSkill> cached = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

            // Assert
            Assert.Same(first, cached);
            Assert.Single(inputs);
            Assert.Equal(1, lists);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        // Act
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Equal(2, lists);
        TimeSpan? expected = serverMilliseconds is { } milliseconds ? TimeSpan.FromMilliseconds(milliseconds) : null;
        Assert.Equal(new[] { expected, expected }, inputs);
    }

    [Theory]
    [InlineData("instructions", null, 2000)]
    [InlineData("instructions", -1L, 2000)]
    [InlineData("instructions", 0L, 2000)]
    [InlineData("instructions", 1000L, 2000)]
    [InlineData("instructions", 5000L, 2000)]
    [InlineData("instructions", 5000L, 0)]
    [InlineData("instructions", 5000L, -1000)]
    [InlineData("text", null, 2000)]
    [InlineData("text", 5000L, 0)]
    [InlineData("binary", 0L, 2000)]
    [InlineData("binary", 5000L, -1000)]
    public async Task ReadResource_TtlResolver_OverridesServerTtlAsync(string kind, long? serverMilliseconds, int resolvedMilliseconds)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        const long PageMilliseconds = 60000;
        List<TimeSpan?> inputs = [];
        int reads = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(PageMilliseconds, Entry()));
            }

            reads++;
            string uri = request.Params!["uri"]!.GetValue<string>();
            JsonObject result = ResourceReadResult(uri, serverMilliseconds, kind == "instructions" ? SkillContent : "Checklist.");
            if (kind == "binary")
            {
                result["contents"] = new JsonArray(new JsonObject
                {
                    ["uri"] = uri,
                    ["blob"] = Convert.ToBase64String([1, 2, 3, 4]),
                    ["mimeType"] = "image/png",
                });
            }

            return Task.FromResult(result);
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl =>
            {
                inputs.Add(ttl);
                return ttl == TimeSpan.FromMilliseconds(PageMilliseconds) ? ttl.Value : TimeSpan.FromMilliseconds(resolvedMilliseconds);
            },
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        AgentSkill skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        async Task ReadAsync()
        {
            if (kind == "binary")
            {
                AgentSkillResource resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
                DataContent content = Assert.IsType<DataContent>(await resource.ReadAsync());
                Assert.Equal(new byte[] { 1, 2, 3, 4 }, content.Data.ToArray());
            }
            else
            {
                await ReadSkillContentAsync(skill, instructions: kind == "instructions");
            }
        }

        // Act
        await ReadAsync();
        if (resolvedMilliseconds > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(resolvedMilliseconds - 1));
            await ReadAsync();

            // Assert
            Assert.Equal(2, inputs.Count);
            Assert.Equal(1, reads);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        // Act
        await ReadAsync();

        // Assert
        Assert.Equal(2, reads);
        TimeSpan? expected = serverMilliseconds is { } milliseconds ? TimeSpan.FromMilliseconds(milliseconds) : null;
        Assert.Equal(new[] { TimeSpan.FromMilliseconds(PageMilliseconds), expected, expected }, inputs);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_TtlResolver_PreservesEarliestPageExpirationAsync(bool emptyFirstPage)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<TimeSpan?> inputs = [];
        int pages = 0;
        var client = CreateTtlClient((request, _) =>
        {
            pages++;
            string? cursor = request.Params?["cursor"]?.GetValue<string>();
            if (cursor is not null)
            {
                clock.Advance(TimeSpan.FromMilliseconds(200));
            }

            JsonObject result = cursor switch
            {
                null => emptyFirstPage ? TtlListResult(null) : TtlListResult(null, Entry()),
                "second" => TtlListResult(0),
                _ => TtlListResult(5000),
            };
            result["nextCursor"] = cursor switch
            {
                null => "second",
                "second" => "third",
                _ => null,
            };
            return Task.FromResult(result);
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl =>
            {
                inputs.Add(ttl);
                return TimeSpan.FromMilliseconds(ttl is null ? 1000 : ttl == TimeSpan.Zero ? 900 : 800);
            },
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(599));
        IList<AgentSkill> fresh = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Same(first, fresh);
        Assert.Equal(3, pages);
        Assert.Equal(new TimeSpan?[] { null, TimeSpan.Zero, TimeSpan.FromSeconds(5) }, inputs);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        IList<AgentSkill> expired = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, expired);
        Assert.Equal(6, pages);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task TtlResolver_ExecutionTime_ConsumesLifetimeAsync(bool resource)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method == "skills/list"
                ? TtlListResult(resource ? 60000 : null, Entry())
                : ResourceReadResult(SkillUri, null, SkillContent));
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl =>
            {
                if (ttl is { } duration)
                {
                    return duration;
                }

                clock.Advance(TimeSpan.FromMilliseconds(300));
                return TimeSpan.FromSeconds(1);
            },
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        AgentSkill skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        async Task AccessAsync()
        {
            if (resource)
            {
                await skill.GetContentAsync();
            }
            else
            {
                await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
            }
        }

        if (resource)
        {
            await AccessAsync();
        }

        int initialCalls = methods.Count;

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(699));
        await AccessAsync();

        // Assert
        Assert.Equal(initialCalls, methods.Count);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await AccessAsync();

        // Assert
        Assert.Equal(initialCalls + 1, methods.Count);
    }

    [Fact]
    public async Task GetSkillsAsync_TtlResolver_IsCapturedAndReevaluatedOnFetchAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int calls = 0;
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = _ => TimeSpan.FromSeconds(++calls),
        };
        var client = CreateTtlClient((_, _) => Task.FromResult(TtlListResult(null, Entry())));
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        options.TtlResolver = _ => throw new InvalidOperationException("The source must retain its original resolver.");
        IList<AgentSkill> first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        clock.Advance(TimeSpan.FromMilliseconds(1999));
        IList<AgentSkill> fresh = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.NotSame(first, refreshed);
        Assert.Same(refreshed, fresh);
        Assert.Equal(2, calls);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal(3, calls);
    }

    [Fact]
    public async Task GetSkillsAsync_TtlResolverFailure_PropagatesAndRetriesAllPagesAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var failure = new InvalidOperationException("TTL resolution failed.");
        bool fail = false;
        List<string?> cursors = [];
        var client = CreateTtlClient((request, _) =>
        {
            string? cursor = request.Params?["cursor"]?.GetValue<string>();
            cursors.Add(cursor);
            JsonObject result = TtlListResult(cursor is null ? 1000 : 2000, Entry());
            if (cursor is null)
            {
                result["nextCursor"] = "next";
            }

            return Task.FromResult(result);
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl => fail && ttl == TimeSpan.FromSeconds(2) ? throw failure : ttl.GetValueOrDefault(),
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        clock.Advance(TimeSpan.FromSeconds(1));
        fail = true;

        // Act
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(
            () => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        fail = false;
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Same(failure, actual);
        Assert.NotSame(original, refreshed);
        Assert.Equal(2, original.Count);
        Assert.Equal(2, refreshed.Count);
        Assert.Equal(new string?[] { null, "next", null, "next", null, "next" }, cursors);
    }

    [Fact]
    public async Task ReadResource_TtlResolverFailureAndMismatch_PreserveCacheAndRefreshReplacementAsync()
    {
        // Arrange
        const string UpdatedContent = SkillContent + "\nUpdated.";
        var clock = new ManualTimeProvider();
        var failure = new InvalidOperationException("TTL resolution failed.");
        bool fail = false;
        bool changed = false;
        int resolutions = 0;
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(60000, Entry()),
                "skills/get" => GetSkillResult(Entry(content: UpdatedContent)),
                _ => ResourceReadResult(SkillUri, null, changed ? UpdatedContent : SkillContent),
            });
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl =>
            {
                resolutions++;
                return fail ? throw failure : ttl ?? TimeSpan.FromSeconds(1);
            },
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(SkillContent, await original.GetContentAsync());
        clock.Advance(TimeSpan.FromSeconds(1));
        fail = true;

        // Act
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        fail = false;
        changed = true;
        string fallback = await original.GetContentAsync();
        string repeatedFallback = await original.GetContentAsync();

        // Assert
        Assert.Same(failure, actual);
        Assert.Equal(SkillContent, fallback);
        Assert.Equal(SkillContent, repeatedFallback);
        Assert.Equal(3, resolutions);
        Assert.Equal(3, methods.Count(method => method == "resources/read"));

        // Act
        AgentSkill replacement = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        string updated = await replacement.GetContentAsync();
        clock.Advance(TimeSpan.FromMilliseconds(999));
        await replacement.GetContentAsync();

        // Assert
        Assert.NotSame(original, replacement);
        Assert.Equal(UpdatedContent, updated);
        Assert.Equal(5, resolutions);
        Assert.Single(methods, method => method == "skills/list");
        Assert.Single(methods, method => method == "skills/get");
        Assert.Equal(4, methods.Count(method => method == "resources/read"));

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await replacement.GetContentAsync();

        // Assert
        Assert.Equal(6, resolutions);
        Assert.Equal(5, methods.Count(method => method == "resources/read"));
    }

    [Theory]
    [InlineData(null, 2000)]
    [InlineData(-1L, 2000)]
    [InlineData(0L, 2000)]
    [InlineData(1000L, 2000)]
    [InlineData(5000L, 2000)]
    [InlineData(5000L, 0)]
    [InlineData(5000L, -1000)]
    public async Task GetSkillsAsync_TtlResolver_OverridesRefreshedMetadataTtlAsync(long? serverMilliseconds, int resolvedMilliseconds)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<TimeSpan?> inputs = [];
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            JsonObject result = request.Method switch
            {
                "skills/list" => TtlListResult(60000, Entry()),
                "skills/get" => GetSkillResult(Entry()),
                _ => ResourceReadResult(SkillUri, 60000, SkillContent + "\nChanged."),
            };
            if (request.Method == "skills/get")
            {
                if (serverMilliseconds is { } milliseconds)
                {
                    result["ttlMs"] = milliseconds;
                }
                else
                {
                    result.Remove("ttlMs");
                }
            }

            return Task.FromResult(result);
        });
        var options = new AgentMcpSkillsSourceOptions
        {
            TtlResolver = ttl =>
            {
                inputs.Add(ttl);
                return ttl == TimeSpan.FromMinutes(1) ? ttl.Value : TimeSpan.FromMilliseconds(resolvedMilliseconds);
            },
        };
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());

        // Act
        AgentSkill replacement = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        if (resolvedMilliseconds > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(resolvedMilliseconds - 1));
            AgentSkill fresh = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

            // Assert
            Assert.Same(replacement, fresh);
            Assert.Equal(2, inputs.Count);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        // Act
        AgentSkill refreshed = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.NotSame(original, replacement);
        Assert.NotSame(replacement, refreshed);
        TimeSpan? expected = serverMilliseconds is { } value ? TimeSpan.FromMilliseconds(value) : null;
        Assert.Equal(new[] { TimeSpan.FromMinutes(1), expected, expected }, inputs);
        Assert.Equal(["skills/list", "resources/read", "skills/get", "skills/get"], methods);
    }

    [Fact]
    public async Task GetSkillsAsync_TtlResolver_MaximumDuration_DoesNotOverflowAsync()
    {
        // Arrange
        var clock = new ManualTimeProvider();
        var options = new AgentMcpSkillsSourceOptions { TtlResolver = _ => TimeSpan.MaxValue };
        var client = CreateTtlClient((_, _) => Task.FromResult(TtlListResult(null, Entry())));
        using var source = new AgentMcpSkillsSource(client.Object, options, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> first = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Act
        clock.Advance(TimeSpan.FromDays(365));
        IList<AgentSkill> second = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Same(first, second);
    }
}
