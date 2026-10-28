// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillsTests
{
    [Fact]
    public async Task GetSkillsAsync_VerificationFailure_RefreshesManifestOnNextRequestAsync()
    {
        // Arrange
        const string UpdatedContent = SkillContent + "\nUpdated.";
        int gets = 0;
        int reads = 0;
        await using var server = CreateServer(
            (_, _) => ValueTask.FromResult<JsonNode?>(TtlListResult(60000, Entry())),
            (uri, _) =>
            {
                reads++;
                return ValueTask.FromResult(Text(uri, UpdatedContent));
            },
            (request, _) =>
            {
                Assert.Equal(SkillUri, request.Params!["uri"]!.GetValue<string>());
                Assert.NotNull(request.Params["_meta"]);
                gets++;
                return ValueTask.FromResult<JsonNode?>(GetSkillResult(Entry(content: UpdatedContent)));
            });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        Assert.Equal(0, gets);

        // Act
        AgentSkill replacement = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.NotSame(original, replacement);
        Assert.Equal(1, gets);
        Assert.Equal(1, reads);
        Assert.Equal(UpdatedContent, await replacement.GetContentAsync());
        Assert.Equal(2, reads);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        Assert.Equal(3, reads);
        Assert.Equal(1, gets);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetSkillsAsync_ManifestRefresh_KeepsResourceSetBoundToEachSkillVersionAsync(bool targetedRefresh)
    {
        // Arrange
        const string GuideUri = "skill://unit-converter/references/checklist.md";
        const string AddedUri = "skill://unit-converter/references/updated.md";
        const string AddedContent = "Updated reference.";
        const string UpdatedContent = SkillContent + "\nUpdated.";
        var clock = new ManualTimeProvider();
        int lists = 0;
        int gets = 0;
        List<string> reads = [];
        var client = CreateTtlClient((request, _) =>
        {
            JsonObject updatedEntry = Entry(content: UpdatedContent);
            updatedEntry["resources"]![1] = Resource(AddedUri, AddedContent);
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(1000, ++lists == 1 ? Entry() : updatedEntry));
            }

            if (request.Method == "skills/get")
            {
                Assert.Equal(SkillUri, request.Params!["uri"]!.GetValue<string>());
                gets++;
                return Task.FromResult(GetSkillResult(updatedEntry));
            }

            Assert.Equal("resources/read", request.Method);
            string uri = request.Params!["uri"]!.GetValue<string>();
            reads.Add(uri);
            return Task.FromResult(ResourceReadResult(uri, 10000, uri switch
            {
                SkillUri => UpdatedContent,
                GuideUri => "Checklist.",
                AddedUri => AddedContent,
                _ => throw new InvalidOperationException(uri),
            }));
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> originalList = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        AgentSkill original = Assert.Single(originalList);
        var retained = Assert.IsType<AgentMcpSkillResource>(await original.GetResourceAsync("references/checklist.md"));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        if (!targetedRefresh)
        {
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        // Act
        IList<AgentSkill> refreshedList = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        AgentSkill replacement = Assert.Single(refreshedList);

        // Assert
        Assert.NotSame(originalList, refreshedList);
        Assert.Same(original, Assert.Single(originalList));
        Assert.NotSame(original, replacement);
        Assert.Equal(targetedRefresh ? 1 : 2, lists);
        Assert.Equal(targetedRefresh ? 1 : 0, gets);
        Assert.Null(await original.GetResourceAsync("references/updated.md"));
        Assert.Null(await replacement.GetResourceAsync("references/checklist.md"));
        Assert.Equal([GuideUri, SkillUri], reads);

        // Act
        string loaded = await replacement.GetContentAsync();
        var added = Assert.IsType<AgentMcpSkillResource>(await replacement.GetResourceAsync("references/updated.md"));

        // Assert
        Assert.Equal(UpdatedContent, loaded);
        Assert.Equal(AddedContent, await added.ReadAsync());
        Assert.Equal("Checklist.", await retained.ReadAsync());
        Assert.Equal("Checklist.", await (await original.GetResourceAsync("references/checklist.md"))!.ReadAsync());
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        Assert.Equal([GuideUri, SkillUri, SkillUri, AddedUri, SkillUri], reads);
        Assert.Same(refreshedList, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
    }

    [Fact]
    public async Task GetSkillsAsync_ExpiredResource_RefetchesWithoutSkillsGetOnConnectedServerAsync()
    {
        // Arrange
        int lists = 0;
        int gets = 0;
        int reads = 0;
        await using var server = CreateServer(
            (_, _) =>
            {
                lists++;
                return ValueTask.FromResult<JsonNode?>(TtlListResult(60000, Entry()));
            },
            (uri, _) =>
            {
                reads++;
                ReadResourceResult result = Text(uri, SkillContent);
                result.TimeToLive = TimeSpan.Zero;
                return ValueTask.FromResult(result);
            },
            (_, _) =>
            {
                gets++;
                throw new InvalidOperationException("A resource read must not refresh the skill manifest.");
            });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        Assert.Equal(SkillContent, await original.GetContentAsync());
        Assert.Equal(SkillContent, await original.GetContentAsync());
        AgentSkill current = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Same(original, current);
        Assert.Equal(1, lists);
        Assert.Equal(0, gets);
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetSkillsAsync_ExpiredResource_RefetchesWithoutChangingCatalogAsync(bool instructions)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(10000, Entry(), Entry("skill://other/unit-converter/")),
                "resources/read" => ResourceReadResult(
                    request.Params!["uri"]!.GetValue<string>(), 1000, instructions ? SkillContent : "Checklist."),
                _ => throw new InvalidOperationException("Resource expiration must not request a new manifest."),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        AgentSkill skill = original[0];
        await ReadSkillContentAsync(skill, instructions);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(999));
        await ReadSkillContentAsync(skill, instructions);

        // Assert
        Assert.Same(original, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(["skills/list", "resources/read"], methods);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await ReadSkillContentAsync(skill, instructions);
        await ReadSkillContentAsync(skill, instructions);
        IList<AgentSkill> current = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);

        // Assert
        Assert.Equal(["skills/list", "resources/read", "resources/read"], methods);
        Assert.Same(original, current);
        Assert.Same(skill, current[0]);
    }

    [Theory]
    [InlineData(true, false, false)]
    [InlineData(false, false, false)]
    [InlineData(true, true, false)]
    [InlineData(false, true, false)]
    [InlineData(true, false, true)]
    [InlineData(false, false, true)]
    [InlineData(true, true, true)]
    [InlineData(false, true, true)]
    public async Task GetSkillsAsync_VerificationFailure_QueuesOwningSkillRefreshAsync(bool instructions, bool cached, bool sizeMismatch)
    {
        // Arrange
        const string GuideUri = "skill://unit-converter/references/checklist.md";
        string originalContent = instructions ? SkillContent : "Checklist.";
        string updatedContent = sizeMismatch ? originalContent + "\nUpdated." : instructions ? SkillContent.Replace("Instructions.", "Changed text.") : "Different.";
        var clock = new ManualTimeProvider();
        bool changed = false;
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            if (request.Method == "skills/get")
            {
                Assert.Equal(SkillUri, request.Params!["uri"]!.GetValue<string>());
                JsonObject entry = Entry();
                entry["resources"]![instructions ? 0 : 1] = Resource(instructions ? SkillUri : GuideUri, updatedContent);
                return Task.FromResult(GetSkillResult(entry));
            }

            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(10000, Entry(), Entry("skill://other/unit-converter/")),
                "resources/read" => ResourceReadResult(
                    request.Params!["uri"]!.GetValue<string>(), 1000, changed ? updatedContent : originalContent),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        if (cached)
        {
            await ReadSkillContentAsync(original[0], instructions);
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        changed = true;

        // Act & Assert
        if (cached)
        {
            await ReadSkillContentAsync(original[0], instructions);
            await ReadSkillContentAsync(original[0], instructions);
        }
        else
        {
            var failure = await Assert.ThrowsAsync<InvalidOperationException>(() => ReadSkillContentAsync(original[0], instructions));
            Assert.Contains(sizeMismatch ? "byte size" : "SHA-256 digest", failure.Message);
            await Assert.ThrowsAsync<InvalidOperationException>(() => ReadSkillContentAsync(original[0], instructions));
        }

        Assert.DoesNotContain("skills/get", methods);

        // Act
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);

        // Assert
        Assert.NotSame(original, refreshed);
        Assert.NotSame(original[0], refreshed[0]);
        Assert.Same(original[1], refreshed[1]);
        Assert.Single(methods, method => method == "skills/list");
        Assert.Single(methods, method => method == "skills/get");
        Assert.Equal(2, methods.FindAll(method => method == "resources/read").Count);
        if (instructions)
        {
            Assert.Equal(updatedContent, await refreshed[0].GetContentAsync());
        }
        else
        {
            Assert.Equal(updatedContent, await (await refreshed[0].GetResourceAsync("references/checklist.md"))!.ReadAsync());
        }

        if (cached)
        {
            await ReadSkillContentAsync(original[0], instructions);
        }
        else
        {
            await Assert.ThrowsAsync<InvalidOperationException>(() => ReadSkillContentAsync(original[0], instructions));
        }

        Assert.Equal(cached ? 3 : 4, methods.FindAll(method => method == "resources/read").Count);
        Assert.Same(refreshed, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
    }

    [Theory]
    [InlineData("name")]
    [InlineData("description")]
    [InlineData("invalid")]
    public async Task GetSkillsAsync_FrontmatterVerificationFailure_DoesNotQueueRefreshAsync(string field)
    {
        // Arrange
        string content = field switch
        {
            "name" => SkillContent.Replace("name: unit-converter", "name: other-skill"),
            "description" => SkillContent.Replace("Convert units.", "Different description."),
            _ => "Instructions without frontmatter.",
        };
        int gets = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/get")
            {
                gets++;
                return Task.FromResult(GetSkillResult(Entry()));
            }

            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(10000, Entry(content: content)),
                "resources/read" => ResourceReadResult(SkillUri, 1000, content),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        IList<AgentSkill> skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        AgentSkill original = Assert.Single(skills);

        // Act & Assert
        var failure = await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        Assert.Contains("frontmatter", failure.Message);
        Assert.Equal(0, gets);

        // Act
        IList<AgentSkill> current = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);

        // Assert
        Assert.Same(skills, current);
        Assert.Same(original, Assert.Single(current));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        Assert.Same(skills, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(0, gets);
    }

    [Theory]
    [InlineData(-32602)]
    [InlineData(-32002)]
    public async Task GetSkillsAsync_VerificationFailure_SkillMissing_RemovesOnlyThatSkillAsync(int errorCode)
    {
        // Arrange
        int gets = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/get")
            {
                gets++;
                throw new McpProtocolException("Skill not found.", (McpErrorCode)errorCode);
            }

            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(10000, Entry(), Entry("skill://other/unit-converter/")),
                "resources/read" => ResourceReadResult(SkillUri, 1000, SkillContent + "\nChanged."),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[0].GetContentAsync());

        // Act
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);

        // Assert
        Assert.Same(original[1], Assert.Single(refreshed));
        Assert.Equal(2, original.Count);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[0].GetContentAsync());
        Assert.Same(refreshed, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(1, gets);
    }

    [Fact]
    public async Task GetSkillsAsync_RefreshedManifestUnchanged_StillRejectsMismatchingContentAsync()
    {
        // Arrange
        int gets = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/get")
            {
                gets++;
                return Task.FromResult(GetSkillResult(Entry()));
            }

            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(10000, Entry()),
                "resources/read" => ResourceReadResult(SkillUri, 1000, SkillContent + "\nChanged."),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());

        // Act
        AgentSkill replacement = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));

        // Assert
        Assert.NotSame(original, replacement);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await replacement.GetContentAsync());
        Assert.Equal(1, gets);
        await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        Assert.Equal(2, gets);
    }

    [Theory]
    [InlineData("request", typeof(McpException), false)]
    [InlineData("protocol", typeof(McpProtocolException), false)]
    [InlineData("operation", typeof(InvalidOperationException), false)]
    [InlineData("canceled", typeof(OperationCanceledException), false)]
    [InlineData("request", typeof(McpException), true)]
    [InlineData("protocol", typeof(McpProtocolException), true)]
    [InlineData("operation", typeof(InvalidOperationException), true)]
    [InlineData("canceled", typeof(OperationCanceledException), true)]
    public async Task GetSkillsAsync_ResourceRequestFailure_DoesNotQueueRefreshAsync(string failure, Type exceptionType, bool cached)
    {
        // Arrange
        Exception error = failure switch
        {
            "request" => new McpException("Read unavailable."),
            "protocol" => new McpProtocolException("Unknown resource.", McpErrorCode.InvalidParams),
            "operation" => new InvalidOperationException("Client failed."),
            _ => new OperationCanceledException(),
        };
        var clock = new ManualTimeProvider();
        int reads = 0;
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return request.Method switch
            {
                "skills/list" => Task.FromResult(TtlListResult(10000, Entry())),
                "resources/read" => cached && ++reads == 1 ? Task.FromResult(ResourceReadResult(SkillUri, 1000, SkillContent)) : throw error,
                _ => throw new InvalidOperationException("Request errors must not queue manifest refreshes."),
            };
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        if (cached)
        {
            await original[0].GetContentAsync();
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        // Act & Assert
        Assert.Same(error, await Assert.ThrowsAsync(exceptionType, async () => await original[0].GetContentAsync()));
        Assert.Same(original, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(cached ? ["skills/list", "resources/read", "resources/read"] : ["skills/list", "resources/read"], methods);
    }

    [Theory]
    [InlineData("missing", false)]
    [InlineData("multiple", false)]
    [InlineData("base64", false)]
    [InlineData("binary-instructions", false)]
    [InlineData("limit", false)]
    [InlineData("missing", true)]
    [InlineData("multiple", true)]
    [InlineData("base64", true)]
    [InlineData("binary-instructions", true)]
    [InlineData("limit", true)]
    public async Task GetSkillsAsync_InvalidResourceResponse_DoesNotQueueRefreshAsync(string failure, bool cached)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int reads = 0;
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(10000, Entry()));
            }

            Assert.Equal("resources/read", request.Method);
            JsonObject result = ResourceReadResult(SkillUri, 1000, SkillContent);
            if (cached && ++reads == 1)
            {
                return Task.FromResult(result);
            }

            result["contents"] = failure switch
            {
                "missing" => new JsonArray(),
                "multiple" => new JsonArray(
                    new JsonObject { ["uri"] = SkillUri, ["text"] = SkillContent },
                    new JsonObject { ["uri"] = SkillUri, ["text"] = SkillContent }),
                "base64" => new JsonArray(new JsonObject { ["uri"] = SkillUri, ["blob"] = "%invalid%" }),
                "binary-instructions" => new JsonArray(new JsonObject { ["uri"] = SkillUri, ["blob"] = Convert.ToBase64String(Encoding.UTF8.GetBytes(SkillContent)) }),
                _ => new JsonArray(new JsonObject { ["uri"] = SkillUri, ["text"] = SkillContent + "x" }),
            };
            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, loggerFactory: null,
            options: new AgentMcpSkillsSourceOptions { ListedResourceMaxSizeBytes = Encoding.UTF8.GetByteCount(SkillContent) },
            timeProvider: clock);
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        if (cached)
        {
            await original[0].GetContentAsync();
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[0].GetContentAsync());
        Assert.Same(original, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(cached ? ["skills/list", "resources/read", "resources/read"] : ["skills/list", "resources/read"], methods);
    }

    [Fact]
    public async Task GetSkillsAsync_CanceledReadResponse_DoesNotQueueVerificationRefreshAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        List<string> methods = [];
        var client = CreateTtlClient((request, token) =>
        {
            methods.Add(request.Method);
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(10000, Entry()));
            }

            Assert.Equal("resources/read", request.Method);
            Assert.Equal(cts.Token, token);
            cts.Cancel();
            return Task.FromResult(ResourceReadResult(SkillUri, 1000, "Changed."));
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await original[0].GetContentAsync(cts.Token));
        Assert.Same(original, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(["skills/list", "resources/read"], methods);
    }

    [Theory]
    [InlineData("request", typeof(McpException))]
    [InlineData("internal", typeof(McpProtocolException))]
    [InlineData("missing", typeof(JsonException))]
    [InlineData("null", typeof(JsonException))]
    [InlineData("type", typeof(InvalidOperationException))]
    [InlineData("uri", typeof(InvalidOperationException))]
    [InlineData("frontmatter", typeof(InvalidOperationException))]
    [InlineData("digest", typeof(InvalidOperationException))]
    [InlineData("size", typeof(InvalidOperationException))]
    [InlineData("incomplete", typeof(InvalidOperationException))]
    [InlineData("dynamic", typeof(JsonException))]
    public async Task GetSkillsAsync_VerificationRefreshFailure_RetainsPendingWorkAsync(string failure, Type exceptionType)
    {
        // Arrange
        const string UpdatedContent = SkillContent + "\nUpdated.";
        int gets = 0;
        int reads = 0;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(10000, Entry()));
            }

            if (request.Method == "resources/read")
            {
                reads++;
                return Task.FromResult(ResourceReadResult(SkillUri, 1000, UpdatedContent));
            }

            Assert.Equal("skills/get", request.Method);
            JsonObject result = GetSkillResult(Entry(content: UpdatedContent));
            if (++gets == 1)
            {
                switch (failure)
                {
                    case "request": throw new McpException("Refresh unavailable.");
                    case "internal": throw new McpProtocolException("Server failed.", McpErrorCode.InternalError);
                    case "missing": result.Remove("skill"); break;
                    case "null": result["skill"] = null; break;
                    case "type": result["resultType"] = "input_required"; break;
                    case "uri": result["skill"] = Entry("skill://other/unit-converter/"); break;
                    case "frontmatter": result["skill"]!["frontmatter"]!["name"] = "invalid_name"; break;
                    case "digest": result["skill"]!["resources"]![0]!["digest"] = "invalid"; break;
                    case "size": result["skill"]!["resources"]![0]!["size"] = 2_000_000; break;
                    case "incomplete": result["skill"]!["resources"] = new JsonArray(); break;
                    case "dynamic": result["skill"]!["resources"] = "dynamic"; break;
                    default: throw new ArgumentOutOfRangeException(nameof(failure));
                }
            }

            return Task.FromResult(result);
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[0].GetContentAsync());

        // Act & Assert
        await Assert.ThrowsAsync(exceptionType, () => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[0].GetContentAsync());
        Assert.Equal(2, reads);
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        Assert.NotSame(original, refreshed);
        Assert.NotSame(original[0], Assert.Single(refreshed));
        Assert.Single(original);
        Assert.Equal(UpdatedContent, await refreshed[0].GetContentAsync());
        Assert.Equal(3, reads);
        Assert.Equal(2, gets);
        Assert.Same(refreshed, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_VerificationRefreshBatchFailure_DoesNotPublishPartialUpdatesAsync(bool remove)
    {
        // Arrange
        const string UpdatedContent = SkillContent + "\nUpdated.";
        int gets = 0;
        bool fail = true;
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(10000, Entry(), Entry("skill://other/unit-converter/")));
            }

            string uri = request.Params!["uri"]!.GetValue<string>();
            if (request.Method == "resources/read")
            {
                return Task.FromResult(ResourceReadResult(uri, 1000, UpdatedContent));
            }

            Assert.Equal("skills/get", request.Method);
            if (++gets == 2 && fail)
            {
                throw new McpException("Second refresh failed.");
            }

            if (fail && remove)
            {
                throw new McpProtocolException("Skill removed.", McpErrorCode.InvalidParams);
            }

            return Task.FromResult(GetSkillResult(Entry(uri[..^"SKILL.md".Length], content: UpdatedContent)));
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        AgentSkill[] held = [.. original];
        foreach (AgentSkill skill in original)
        {
            await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        }

        // Act & Assert
        await Assert.ThrowsAsync<McpException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        Assert.Equal(held, original);
        fail = false;
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        Assert.Equal(4, gets);
        Assert.Equal(2, refreshed.Count);
        Assert.NotSame(original[0], refreshed[0]);
        Assert.NotSame(original[1], refreshed[1]);
        Assert.Equal(held, original);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_CanceledVerificationRefresh_RetriesPendingSkillAsync(bool afterResponse)
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int gets = 0;
        var client = CreateTtlClient(async (request, token) =>
        {
            switch (request.Method)
            {
                case "skills/list": return TtlListResult(10000, Entry());
                case "resources/read": return ResourceReadResult(SkillUri, 1000, SkillContent + "\nChanged.");
                case "skills/get":
                    if (++gets == 1)
                    {
                        started.SetResult();
                        if (afterResponse)
                        {
                            cts.Cancel();
                        }
                        else
                        {
                            await Task.Delay(Timeout.InfiniteTimeSpan, token);
                        }
                    }

                    return GetSkillResult(Entry());
                default: throw new InvalidOperationException(request.Method);
            }
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());

        // Act
        Task<IList<AgentSkill>> active = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), cts.Token);
        await started.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Task<IList<AgentSkill>> waiting = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        await cts.CancelAsync();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => active.WaitAsync(TimeSpan.FromSeconds(10)));
        IList<AgentSkill> refreshed = await waiting.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.NotSame(original, Assert.Single(refreshed));
        Assert.Equal(2, gets);
        Assert.Same(refreshed, await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
    }

    [Fact]
    public async Task GetSkillsAsync_ConcurrentVerificationRefreshes_SharePublishedCatalogAsync()
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int gets = 0;
        var client = CreateTtlClient((request, _) => request.Method switch
        {
            "skills/list" => Task.FromResult(TtlListResult(10000, Entry())),
            "resources/read" => Task.FromResult(ResourceReadResult(SkillUri, 1000, SkillContent + "\nChanged.")),
            "skills/get" => ++gets == 1 ? release.Task : throw new InvalidOperationException("Duplicate refresh."),
            _ => throw new InvalidOperationException(request.Method),
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());

        // Act
        Task<IList<AgentSkill>>[] pending = Enumerable.Range(0, 8).Select(_ => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None)).ToArray();
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        release.SetResult(GetSkillResult(Entry()));
        IList<AgentSkill>[] results = await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(1, gets);
        Assert.All(results, result => Assert.Same(results[0], result));
        Assert.NotSame(original, Assert.Single(results[0]));
    }

    [Fact]
    public async Task GetSkillsAsync_VerificationFailureDuringRefresh_RemainsPendingForOtherSkillAsync()
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        List<string> gets = [];
        var client = CreateTtlClient((request, _) =>
        {
            if (request.Method == "skills/list")
            {
                return Task.FromResult(TtlListResult(10000, Entry(), Entry("skill://other/unit-converter/")));
            }

            string uri = request.Params!["uri"]!.GetValue<string>();
            if (request.Method == "resources/read")
            {
                return Task.FromResult(ResourceReadResult(uri, 1000, SkillContent + "\nChanged."));
            }

            Assert.Equal("skills/get", request.Method);
            gets.Add(uri);
            return gets.Count == 1 ? release.Task : Task.FromResult(GetSkillResult(Entry("skill://other/unit-converter/")));
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: new ManualTimeProvider());
        IList<AgentSkill> original = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[0].GetContentAsync());

        // Act
        Task<IList<AgentSkill>> firstRefresh = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original[1].GetContentAsync());
        release.SetResult(GetSkillResult(Entry()));
        await firstRefresh.WaitAsync(TimeSpan.FromSeconds(10));
        IList<AgentSkill> refreshed = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);

        // Assert
        Assert.Equal([SkillUri, "skill://other/unit-converter/SKILL.md"], gets);
        Assert.NotSame(original[0], refreshed[0]);
        Assert.NotSame(original[1], refreshed[1]);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_ExpiredListing_TakesPrecedenceOverQueuedVerificationRefreshAsync(bool targetedFirst)
    {
        // Arrange
        const string UpdatedContent = SkillContent + "\nUpdated.";
        var clock = new ManualTimeProvider();
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(1000, Entry()),
                "skills/get" => GetSkillResult(Entry(content: UpdatedContent)),
                "resources/read" => ResourceReadResult(SkillUri, 1000, UpdatedContent),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        clock.Advance(TimeSpan.FromMilliseconds(999));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        if (targetedFirst)
        {
            await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None);
        }

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        AgentSkill refreshed = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));

        // Assert
        Assert.NotSame(original, refreshed);
        string[] expected = targetedFirst
            ? ["skills/list", "resources/read", "skills/get", "skills/list"]
            : ["skills/list", "resources/read", "skills/list"];
        Assert.Equal(expected, methods);
    }

    [Theory]
    [InlineData(null, true)]
    [InlineData(0L, true)]
    [InlineData(-1L, true)]
    [InlineData(long.MinValue, true)]
    [InlineData(long.MaxValue, false)]
    public async Task GetSkillsAsync_ResourceTtlHints_RefetchOnlyExpiredContentAsync(long? ttl, bool stale)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(long.MaxValue, Entry()),
                "resources/read" => ResourceReadResult(SkillUri, ttl, SkillContent),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        await ReadSkillContentAsync(original, instructions: true);

        // Act
        clock.Advance(TimeSpan.FromDays(365));
        await ReadSkillContentAsync(original, instructions: true);
        AgentSkill current = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));

        // Assert
        Assert.Same(original, current);
        string[] expectedMethods = stale ? ["skills/list", "resources/read", "resources/read"] : ["skills/list", "resources/read"];
        Assert.Equal(expectedMethods, methods);
    }

    [Fact]
    public async Task GetSkillsAsync_ListingRefresh_KeepsHeldManifestAndReturnedResourcesAsync()
    {
        // Arrange
        const string GuideUri = "skill://unit-converter/references/checklist.md";
        const string UpdatedContent = "Updated checklist.";
        var clock = new ManualTimeProvider();
        int lists = 0;
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            if (request.Method == "skills/list")
            {
                JsonObject entry = Entry();
                if (++lists > 1)
                {
                    entry["resources"]![1] = Resource(GuideUri, UpdatedContent);
                }

                return Task.FromResult(TtlListResult(1000, entry));
            }

            Assert.Equal("resources/read", request.Method);
            return Task.FromResult(ResourceReadResult(GuideUri, 1000, lists == 1 ? "Checklist." : UpdatedContent));
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        AgentSkill original = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        var retained = Assert.IsType<AgentMcpSkillResource>(await original.GetResourceAsync("references/checklist.md"));

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        AgentSkill replacement = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        var fallback = Assert.IsType<AgentMcpSkillResource>(await original.GetResourceAsync("references/checklist.md"));
        var updated = Assert.IsType<AgentMcpSkillResource>(await replacement.GetResourceAsync("references/checklist.md"));

        // Assert
        Assert.NotSame(original, replacement);
        Assert.Equal("Checklist.", await retained.ReadAsync());
        Assert.Equal("Checklist.", await fallback.ReadAsync());
        Assert.Equal(UpdatedContent, await updated.ReadAsync());
        Assert.Equal(["skills/list", "resources/read", "skills/list", "resources/read", "resources/read"], methods);
        Assert.Same(replacement, Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None)));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task GetSkillsAsync_DisposedLoader_RetainedSkillRefetchesExpiredContentAsync(bool instructions)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        List<string> methods = [];
        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(10000, Entry()),
                "resources/read" => ResourceReadResult(
                    request.Params!["uri"]!.GetValue<string>(), 1000, instructions ? SkillContent : "Checklist."),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        using var source = new AgentMcpSkillsSource(client.Object, options: null, loggerFactory: null, timeProvider: clock);
        AgentSkill skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), CancellationToken.None));
        await ReadSkillContentAsync(skill, instructions);
        source.Dispose();

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        await ReadSkillContentAsync(skill, instructions);

        // Assert
        Assert.Equal(["skills/list", "resources/read", "resources/read"], methods);
    }

    /// <summary>
    /// Creates a skills/get response for the supplied skill.
    /// </summary>
    private static JsonObject GetSkillResult(JsonObject entry) => new()
    {
        ["resultType"] = "complete",
        ["skill"] = entry,
        ["ttlMs"] = 10000,
        ["cacheScope"] = "private",
    };

    /// <summary>
    /// Creates a text resource response with an optional TTL.
    /// </summary>
    private static JsonObject ResourceReadResult(string uri, long? ttl, string text)
    {
        JsonObject result = new()
        {
            ["resultType"] = "complete",
            ["contents"] = new JsonArray(new JsonObject { ["uri"] = uri, ["text"] = text }),
            ["cacheScope"] = "private",
        };
        if (ttl is not null)
        {
            result["ttlMs"] = ttl.Value;
        }

        return result;
    }

    /// <summary>
    /// Checks the expected content of <c>SKILL.md</c> or a supporting resource.
    /// </summary>
    private static async Task ReadSkillContentAsync(AgentSkill skill, bool instructions)
    {
        if (instructions)
        {
            Assert.Equal(SkillContent, await skill.GetContentAsync());
        }
        else
        {
            var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
            Assert.Equal("Checklist.", await resource.ReadAsync());
        }
    }
}
