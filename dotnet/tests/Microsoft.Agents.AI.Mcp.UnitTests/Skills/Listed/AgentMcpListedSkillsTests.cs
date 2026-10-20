// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests discovery and content access for skills returned by <c>skills/list</c>.
/// </summary>
public sealed partial class AgentMcpListedSkillsTests
{
    private const string SkillUri = "skill://unit-converter/SKILL.md";
    private const string SkillContent = "---\nname: unit-converter\ndescription: Convert units.\n---\nInstructions.";

    [Fact]
    public async Task GetSkillsAsync_ListRequest_ProjectsFrontmatterAndIncludesRequestMetadataAsync()
    {
        // Arrange
        List<JsonNode?> requests = [];
        await using var server = CreateServer((request, _) =>
        {
            requests.Add(request.Params?.DeepClone());
            return ValueTask.FromResult<JsonNode?>(ListResult(Entry()));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        var skill = Assert.IsType<AgentMcpListedSkill>(Assert.Single(skills));
        Assert.Equal("unit-converter", skill.Frontmatter.Name);
        Assert.Equal("Convert units.", skill.Frontmatter.Description);
        Assert.Null(skill.Frontmatter.License);
        var request = Assert.Single(requests)!;
        Assert.Null(request["cursor"]);
        Assert.Equal(client.NegotiatedProtocolVersion, request["_meta"]![MetaKeys.ProtocolVersion]!.GetValue<string>());
        Assert.NotNull(request["_meta"]![MetaKeys.ClientCapabilities]);
        Assert.NotNull(request["_meta"]![MetaKeys.ClientInfo]);
    }

    [Theory]
    [InlineData("")]
    [InlineData("opaque cursor:+/=\u00e9")]
    public async Task GetSkillsAsync_PaginatedList_FollowsOpaqueCursorsAndEmptyPagesAsync(string firstCursor)
    {
        // Arrange
        List<JsonNode?> requests = [];
        List<string> reads = [];
        await using var server = CreateServer((request, _) =>
        {
            requests.Add(request.Params?.DeepClone());
            JsonObject result = requests.Count switch
            {
                1 => ListResult(Entry("skill://first/unit-converter/")),
                2 => ListResult(),
                _ => ListResult(Entry("skill://second/unit-converter/")),
            };
            if (requests.Count < 3)
            {
                result["nextCursor"] = requests.Count == 1 ? firstCursor : "last-page";
            }

            return ValueTask.FromResult<JsonNode?>(result);
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal(3, requests.Count);
        Assert.Null(requests[0]!["cursor"]);
        Assert.Equal(firstCursor, requests[1]!["cursor"]!.GetValue<string>());
        Assert.Equal("last-page", requests[2]!["cursor"]!.GetValue<string>());
        foreach (JsonNode? request in requests)
        {
            Assert.Equal(client.NegotiatedProtocolVersion, request!["_meta"]![MetaKeys.ProtocolVersion]!.GetValue<string>());
            Assert.NotNull(request["_meta"]![MetaKeys.ClientCapabilities]);
            Assert.NotNull(request["_meta"]![MetaKeys.ClientInfo]);
        }

        Assert.Equal(2, skills.Count);
        Assert.Empty(reads);
        Assert.NotNull(await skills[0].GetResourceAsync("references/checklist.md"));
        Assert.NotNull(await skills[1].GetResourceAsync("references/checklist.md"));
        Assert.Equal(
            ["skill://first/unit-converter/references/checklist.md", "skill://second/unit-converter/references/checklist.md"],
            reads);
    }

    [Theory]
    [InlineData(null, 10, false)]
    [InlineData(null, 10, true)]
    [InlineData(2, 2, false)]
    [InlineData(2, 2, true)]
    [InlineData(11, 11, false)]
    [InlineData(11, 11, true)]
    public async Task GetSkillsAsync_PageLimit_IncludesEmptyPagesAndDoesNotSendExtraRequestAsync(int? limit, int expectedPages, bool exceedsLimit)
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            JsonObject result = ListResult();
            calls++;
            if (exceedsLimit || calls < expectedPages)
            {
                result["nextCursor"] = $"page-{calls}";
            }

            return ValueTask.FromResult<JsonNode?>(result);
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client, new() { ListedMaxPageCount = limit });

        // Act & Assert
        if (exceedsLimit)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            Assert.Contains($"page count ({expectedPages})", exception.Message);
        }
        else
        {
            Assert.Empty(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        }

        Assert.Equal(expectedPages, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_RepeatedCursor_ThrowsAsync(bool cycle)
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            JsonObject result = ListResult(Entry());
            result["nextCursor"] = cycle && calls == 2 ? "b" : "a";
            return ValueTask.FromResult<JsonNode?>(result);
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Contains("repeated pagination cursor", exception.Message);
        Assert.Equal(cycle ? 3 : 2, calls);
    }

    [Fact]
    public async Task GetSkillsAsync_CursorsDifferingOnlyByCase_AreDistinctAsync()
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            JsonObject result = ListResult();
            calls++;
            result["nextCursor"] = calls switch { 1 => "A", 2 => "a", _ => null };
            return ValueTask.FromResult<JsonNode?>(result);
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
        Assert.Equal(3, calls);
    }

    [Theory]
    [InlineData("{}", typeof(JsonException))]
    [InlineData("""{"resultType":"unknown","skills":[]}""", typeof(InvalidOperationException))]
    [InlineData("""{"resultType":"complete","skills":[null]}""", typeof(InvalidOperationException))]
    [InlineData("""{"resultType":"complete","skills":[],"nextCursor":42}""", typeof(JsonException))]
    public async Task GetSkillsAsync_InvalidLaterPage_ThrowsInsteadOfReturningPartialCatalogAsync(string invalidPage, Type exceptionType)
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        await using var server = CreateServer((_, _) =>
        {
            if (++calls > 1)
            {
                return ValueTask.FromResult(JsonNode.Parse(invalidPage));
            }

            JsonObject result = ListResult(Entry());
            result["nextCursor"] = "next";
            return ValueTask.FromResult<JsonNode?>(result);
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync(exceptionType, () => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(2, calls);
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetSkillsAsync_LaterPageError_PropagatesWithoutReadingIndexAsync()
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        await using var server = CreateServer((_, _) =>
        {
            if (++calls > 1)
            {
                throw new McpProtocolException("Cannot list next page.", McpErrorCode.InternalError);
            }

            JsonObject result = ListResult(Entry());
            result["nextCursor"] = "next";
            return ValueTask.FromResult<JsonNode?>(result);
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<McpProtocolException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(2, calls);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData(null, 99, false)]
    [InlineData(null, 100, false)]
    [InlineData(null, 101, true)]
    [InlineData(2, 2, false)]
    [InlineData(2, 3, true)]
    [InlineData(101, 101, false)]
    public async Task GetSkillsAsync_SkillLimit_CountsEntriesAcrossPagesIncludingDuplicatesAsync(int? limit, int count, bool exceedsLimit)
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            JsonObject result = ListResult();
            var entries = Assert.IsType<JsonArray>(result["skills"]);
            for (int i = 0; i < (calls == 1 ? 1 : count - 1); i++)
            {
                entries.Add(Entry());
            }

            if (calls == 1)
            {
                result["nextCursor"] = "next";
            }

            return ValueTask.FromResult<JsonNode?>(result);
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client, new() { ListedMaxSkillCount = limit });

        // Act & Assert
        if (exceedsLimit)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            Assert.Contains($"skill count ({limit ?? 100})", exception.Message);
        }
        else
        {
            Assert.Equal(count, (await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())).Count);
        }

        Assert.Equal(2, calls);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    public async Task DiscoverAsync_LargeUnknownFields_AreAcceptedAcrossPagesAsync(int pageCount)
    {
        // Arrange
        string padding = new('x', 10 * 1024 * 1024 / pageCount);
        var client = new Mock<McpClient>();
        var responses = client.SetupSequence(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()));
        for (int page = 0; page < pageCount; page++)
        {
            JsonObject result = ListResult(Entry());
            result["unknown"] = padding;
            if (page < pageCount - 1)
            {
                result["nextCursor"] = $"page-{page + 1}";
            }

            responses.ReturnsAsync(new JsonRpcResponse { Id = new RequestId(page + 1), Result = result });
        }

        using var loader = new McpListedSkillsLoader(client.Object);

        // Act
        var skills = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Equal(pageCount, skills.Count);
        client.Verify(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()), Times.Exactly(pageCount));
    }

    [Fact]
    public async Task DiscoverAsync_SkillLimit_RejectsExcessEntriesBeforeTypedDeserializationAsync()
    {
        // Arrange
        var client = new Mock<McpClient>();
        client.Setup(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new JsonRpcResponse { Id = new RequestId(1), Result = ListResult(Entry(), new JsonObject()) });
        using var loader = new McpListedSkillsLoader(client.Object, options: new() { ListedMaxSkillCount = 1 });

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => loader.DiscoverAsync(CancellationToken.None));

        // Assert
        Assert.Contains("skill count (1)", exception.Message);
    }

    [Fact]
    public async Task DiscoverAsync_LargeResourceManifest_HasNoSeparateResourceCountLimitAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        var resources = Assert.IsType<JsonArray>(entry["resources"]);
        for (int i = 0; i < 101; i++)
        {
            resources.Add(Resource($"skill://unit-converter/file-{i}.txt"));
        }

        var client = new Mock<McpClient>();
        client.Setup(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new JsonRpcResponse { Id = new RequestId(1), Result = ListResult(entry) });
        using var loader = new McpListedSkillsLoader(client.Object);

        // Act
        var skills = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
    }

    [Theory]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.ListedMaxPageCount), 0)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.ListedMaxPageCount), -1)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.ListedMaxSkillCount), 0)]
    [InlineData(nameof(AgentMcpSkillsSourceOptions.ListedMaxSkillCount), -1)]
    public void Constructor_InvalidDiscoveryLimit_Throws(string option, int limit)
    {
        // Arrange
        var client = new Mock<McpClient>();
        var options = new AgentMcpSkillsSourceOptions
        {
            ListedMaxPageCount = option == nameof(AgentMcpSkillsSourceOptions.ListedMaxPageCount) ? limit : null,
            ListedMaxSkillCount = option == nameof(AgentMcpSkillsSourceOptions.ListedMaxSkillCount) ? limit : null,
        };

        // Act
        var exception = Assert.Throws<ArgumentOutOfRangeException>(() => new AgentMcpSkillsSource(client.Object, options));

        // Assert
        Assert.Equal(option, exception.ParamName);
    }

    [Fact]
    public async Task GetSkillsAsync_Refresh_KeepsPreviouslyReturnedManifestAsync()
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        JsonObject updatedEntry = Entry();
        updatedEntry["resources"]![1]!["uri"] = "skill://unit-converter/references/updated.md";
        await using var server = CreateServer((_, _) =>
            ValueTask.FromResult<JsonNode?>(ListResult(++calls == 1 ? Entry() : updatedEntry)),
            (uri, _) =>
            {
                reads.Add(uri);
                return ValueTask.FromResult(Text(uri, "Checklist."));
            });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var first = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var updated = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var originalResource = await first.GetResourceAsync("references/checklist.md");
        var unavailableUpdatedResource = await first.GetResourceAsync("references/updated.md");
        var updatedResource = await updated.GetResourceAsync("references/updated.md");
        var unavailableOriginalResource = await updated.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(originalResource);
        Assert.Null(unavailableUpdatedResource);
        Assert.NotNull(updatedResource);
        Assert.Null(unavailableOriginalResource);
        Assert.Equal(2, calls);
        Assert.Equal(["skill://unit-converter/references/checklist.md", "skill://unit-converter/references/updated.md"], reads);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("""{"skills":[]}""")]
    [InlineData("""{"resultType":null,"skills":[]}""")]
    [InlineData("""{"resultType":"complete"}""")]
    [InlineData("""{"resultType":"complete","skills":null}""")]
    public async Task GetSkillsAsync_InvalidListResult_ThrowsAsync(string result)
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult(JsonNode.Parse(result)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Fact]
    public async Task DiscoverAsync_MissingResult_ThrowsAsync()
    {
        // Arrange
        var client = new Mock<McpClient>();
        client.Setup(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new JsonRpcResponse { Id = new RequestId(1), Result = null });
        using var loader = new McpListedSkillsLoader(client.Object);

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => loader.DiscoverAsync(CancellationToken.None));

        // Assert
        Assert.Equal("The server returned no skills/list result.", exception.Message);
    }

    [Theory]
    [InlineData("")]
    [InlineData("unknown")]
    [InlineData("Complete")]
    public async Task GetSkillsAsync_InvalidResultType_ReportsActualValueAsync(string resultType)
    {
        // Arrange
        JsonObject listResult = ListResult();
        listResult["resultType"] = resultType;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(listResult));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(
            $"A skills/list result must have resultType 'complete'. Received resultType '{resultType}'.",
            exception.Message);
    }

    [Fact]
    public async Task GetSkillsAsync_InvalidInputRequiredResult_PropagatesSdkErrorAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) =>
            ValueTask.FromResult(JsonNode.Parse("""{"resultType":"input_required"}""")));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<McpException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_SingleListRequest_DoesNotReadResourcesAsync(bool empty)
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            return ValueTask.FromResult<JsonNode?>(empty ? ListResult() : ListResult(Entry()));
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal(empty ? 0 : 1, skills.Count);
        Assert.Equal(1, calls);
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetSkillsAsync_ListError_DoesNotReadIndexAsync()
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            throw new McpProtocolException("Cannot list skills.", McpErrorCode.InternalError);
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Index must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<McpProtocolException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(1, calls);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_ListCancellation_PropagatesAsync(bool laterPage)
    {
        // Arrange
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int calls = 0;
        await using var server = CreateServer(async (_, token) =>
        {
            if (++calls == 1 && laterPage)
            {
                JsonObject result = ListResult(Entry());
                result["nextCursor"] = "next";
                return result;
            }

            started.SetResult();
            await release.Task.WaitAsync(token);
            return ListResult(Entry());
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        using var cts = new CancellationTokenSource();

        // Act
        Task<IList<AgentSkill>> operation = source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), cts.Token);
        try
        {
            await started.Task.WaitAsync(TimeSpan.FromSeconds(10));
            await cts.CancelAsync();

            // Assert
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => operation.WaitAsync(TimeSpan.FromSeconds(10)));
            Assert.Equal(laterPage ? 2 : 1, calls);
        }
        finally
        {
            release.TrySetResult();
        }
    }

    [Fact]
    public async Task GetSkillsAsync_AlreadyCancelled_SendsNoRequestAsync()
    {
        // Arrange
        int calls = 0;
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            return ValueTask.FromResult<JsonNode?>(ListResult());
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create(), cts.Token));
        Assert.Equal(0, calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_NoDeclaration_ReadsIndexInsteadOfListAsync(bool smallResourceLimit)
    {
        // Arrange
        int calls = 0;
        List<string> reads = [];
        await using var server = CreateServer((_, _) =>
        {
            calls++;
            return ValueTask.FromResult<JsonNode?>(ListResult(Entry()));
        }, (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri,
                """{"skills":[{"name":"older-skill","description":"Older server.","type":"skill-md","url":"skill://older-skill/SKILL.md"}]}"""));
        });
        await using var client = await server.CreateClientAsync();
        client.ServerCapabilities.Extensions = null;
        using var source = new AgentMcpSkillsSource(client, smallResourceLimit
            ? new() { ListedResourceMaxSizeBytes = 1 }
            : null);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal("older-skill", Assert.Single(skills).Frontmatter.Name);
        Assert.Equal("skill://index.json", Assert.Single(reads));
        Assert.Equal(0, calls);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("null")]
    public async Task GetSkillsAsync_DeclaredButMissingList_DoesNotReadIndexAsync(string declaration)
    {
        // Arrange
        List<string> reads = [];
        await using var server = new InMemoryMcpServer(builder => builder.WithReadResourceHandler((request, _) =>
        {
            reads.Add(request.Params!.Uri);
            return ValueTask.FromResult(Text(request.Params.Uri, "{}"));
        }));
        await using var client = await server.CreateClientAsync();
        client.ServerCapabilities.Extensions = new Dictionary<string, object>
        {
            ["io.modelcontextprotocol/skills"] = JsonSerializer.Deserialize<JsonElement>(declaration),
        };
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<McpProtocolException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Equal(McpErrorCode.MethodNotFound, exception.ErrorCode);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_EmptyOrUnsupportedDynamicList_DoesNotReconcileArchivesAsync(bool dynamic)
    {
        // Arrange
        string directory = Path.Combine(Path.GetTempPath(), "af-mcp-list-tests-" + Guid.NewGuid().ToString("N"));
        string staleDirectory = Path.Combine(directory, "stale-skill");
        Directory.CreateDirectory(staleDirectory);
        string marker = Path.Combine(staleDirectory, "SKILL.md");
        await File.WriteAllTextAsync(marker, "Preserve this file.");
        try
        {
            JsonObject entry = Entry();
            entry["resources"] = "dynamic";
            List<string> reads = [];
            await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(dynamic ? ListResult(entry) : ListResult()),
                (uri, _) =>
                {
                    reads.Add(uri);
                    return ValueTask.FromResult(Text(uri, "{}"));
                });
            await using var client = await server.CreateClientAsync();
            using var source = new AgentMcpSkillsSource(client, new() { ArchiveSkillsDirectory = directory });

            // Act
            if (dynamic)
            {
                await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            }
            else
            {
                var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
                Assert.Empty(skills);
            }

            // Assert
            Assert.Empty(reads);
            Assert.Equal("Preserve this file.", await File.ReadAllTextAsync(marker));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Theory]
    [InlineData("uri", "null", typeof(JsonException))]
    [InlineData("uri", "\"skill://other/SKILL.md\"", typeof(InvalidOperationException))]
    [InlineData("uri", "\"relative/SKILL.md\"", typeof(InvalidOperationException))]
    [InlineData("frontmatter", "null", typeof(JsonException))]
    [InlineData("frontmatter", "[]", typeof(JsonException))]
    [InlineData("frontmatter", "\"metadata\"", typeof(JsonException))]
    [InlineData("frontmatter", "{}", typeof(JsonException))]
    [InlineData("frontmatter", """{"name":"unit-converter"}""", typeof(JsonException))]
    [InlineData("frontmatter", """{"description":"Convert units."}""", typeof(JsonException))]
    [InlineData("frontmatter", """{"name":null,"description":"Convert units."}""", typeof(JsonException))]
    [InlineData("frontmatter", """{"name":42,"description":"Convert units."}""", typeof(JsonException))]
    [InlineData("frontmatter", """{"name":"INVALID","description":"Description."}""", typeof(InvalidOperationException))]
    [InlineData("frontmatter", """{"name":"unit-converter","description":null}""", typeof(JsonException))]
    [InlineData("frontmatter", """{"name":"unit-converter","description":false}""", typeof(JsonException))]
    [InlineData("resources", "null", typeof(JsonException))]
    [InlineData("resources", "false", typeof(JsonException))]
    [InlineData("resources", "\"other\"", typeof(JsonException))]
    [InlineData("resources", "\"dynamic\"", typeof(JsonException))]
    [InlineData("resources", "{}", typeof(JsonException))]
    [InlineData("resources", "[null]", typeof(InvalidOperationException))]
    [InlineData("resources", "[42]", typeof(JsonException))]
    [InlineData("resources", "[[]]", typeof(JsonException))]
    [InlineData("resources", "[{}]", typeof(JsonException))]
    [InlineData("resources", """[{"uri":null}]""", typeof(JsonException))]
    [InlineData("resources", """[{"uri":42}]""", typeof(JsonException))]
    [InlineData("resources", """[{"uri":true}]""", typeof(JsonException))]
    public async Task GetSkillsAsync_InvalidEntry_ThrowsAsync(string field, string value, Type exceptionType)
    {
        // Arrange
        JsonObject entry = Entry();
        entry[field] = JsonNode.Parse(value);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync(exceptionType, () => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData("name", 0, "Skill name is required.")]
    [InlineData("name", 65, "Skill name must be 64 characters or fewer.")]
    [InlineData("description", 0, "Skill description is required.")]
    [InlineData("description", 1025, "Skill description must be 1024 characters or fewer.")]
    public async Task GetSkillsAsync_InvalidFrontmatter_ReportsValidationReasonAsync(string field, int length, string reason)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["frontmatter"]![field] = new string('a', length);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Equal($"Skill '{SkillUri}' has invalid frontmatter: {reason}", exception.Message);
    }

    [Theory]
    [InlineData("uri")]
    [InlineData("frontmatter")]
    [InlineData("resources")]
    public async Task GetSkillsAsync_MissingEntryField_ThrowsAsync(string field)
    {
        // Arrange
        JsonObject entry = Entry();
        entry.Remove(field);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData("uri", "\"skill://other/checklist.md\"", typeof(InvalidOperationException))]
    [InlineData("uri", "\"skill://unit-converter/../escape.md\"", typeof(InvalidOperationException))]
    [InlineData("uri", "\"skill://unit-converter/%252e%252e/escape.md\"", typeof(InvalidOperationException))]
    [InlineData("uri", "\"skill://unit-converter/\"", typeof(InvalidOperationException))]
    [InlineData("uri", "null", typeof(JsonException))]
    public async Task GetSkillsAsync_InvalidManifestEntry_ThrowsAsync(string field, string value, Type exceptionType)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![1]![field] = JsonNode.Parse(value);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync(exceptionType, () => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData(0, "uri")]
    [InlineData(1, "uri")]
    [InlineData(0, "digest")]
    [InlineData(1, "digest")]
    [InlineData(0, "size")]
    [InlineData(1, "size")]
    public async Task GetSkillsAsync_MissingResourceField_ThrowsAsync(int resourceIndex, string field)
    {
        // Arrange
        JsonObject entry = Entry();
        Assert.IsType<JsonObject>(entry["resources"]![resourceIndex]).Remove(field);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        JsonException exception = await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Contains(field, exception.Message);
    }

    [Theory]
    [InlineData("")]
    [InlineData("sha256:abc")]
    [InlineData("sha512:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    [InlineData("SHA256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    [InlineData("sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")]
    [InlineData("sha256:gaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    [InlineData("sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")]
    public async Task GetSkillsAsync_InvalidDigest_ThrowsBeforeReadingAsync(string digest)
    {
        foreach (int resourceIndex in new[] { 0, 1 })
        {
            // Arrange
            JsonObject entry = Entry();
            entry["resources"]![resourceIndex]!["digest"] = digest;
            List<string> reads = [];
            await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
            {
                reads.Add(uri);
                return ValueTask.FromResult(Text(uri, "Must not be read."));
            });
            await using var client = await server.CreateClientAsync();
            using var source = new AgentMcpSkillsSource(client);

            // Act
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

            // Assert
            Assert.Contains("digest", exception.Message);
            Assert.Contains(entry["resources"]![resourceIndex]!["uri"]!.GetValue<string>(), exception.Message);
            Assert.Empty(reads);
        }
    }

    [Theory]
    [InlineData(0, -1L)]
    [InlineData(1, -1L)]
    [InlineData(0, long.MinValue)]
    [InlineData(1, long.MinValue)]
    public async Task GetSkillsAsync_NegativeSize_ThrowsAsync(int resourceIndex, long size)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![resourceIndex]!["size"] = size;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Contains("nonnegative size", exception.Message);
        Assert.Contains(entry["resources"]![resourceIndex]!["uri"]!.GetValue<string>(), exception.Message);
    }

    [Theory]
    [InlineData(0, 1_048_577L)]
    [InlineData(1, 1_048_577L)]
    [InlineData(0, long.MaxValue)]
    [InlineData(1, long.MaxValue)]
    public async Task GetSkillsAsync_OversizedResource_ThrowsWithoutReadingAsync(int resourceIndex, long size)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![resourceIndex]!["size"] = size;
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, SkillContent));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Contains("maximum allowed size (1048576 bytes)", exception.Message);
        Assert.Contains(entry["resources"]![resourceIndex]!["uri"]!.GetValue<string>(), exception.Message);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData(200L)]
    [InlineData(2_097_152L)]
    public async Task GetSkillsAsync_ConfiguredResourceLimit_AcceptsBoundaryAndRejectsLargerAsync(long limit)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![0]!["size"] = limit;
        entry["resources"]![1]!["size"] = limit;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry.DeepClone())));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client, new() { ListedResourceMaxSizeBytes = limit });

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        entry["resources"]![1]!["size"] = limit + 1;
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Single(skills);
        Assert.Contains($"maximum allowed size ({limit} bytes)", exception.Message);
    }

    [Fact]
    public async Task GetSkillsAsync_ResourceLimit_HasNoCombinedSkillLimitAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![0]!["size"] = 1_048_576L;
        entry["resources"]![1]!["size"] = 1_048_576L;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Single(skills);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_ConfiguredResourceLimit_IsAppliedToReadsAsync(bool instructions)
    {
        // Arrange
        long limit = Encoding.UTF8.GetByteCount(SkillContent);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (uri, _) => ValueTask.FromResult(Text(uri, new string('x', (int)limit + 1))));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client, new() { ListedResourceMaxSizeBytes = limit });
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            if (instructions)
            {
                await skill.GetContentAsync();
            }
            else
            {
                await skill.GetResourceAsync("references/checklist.md");
            }
        });

        // Assert
        Assert.Contains($"maximum allowed size ({limit} bytes)", exception.Message);
    }

    [Fact]
    public async Task GetSkillsAsync_RaisedResourceLimit_AllowsLargerReadsAsync()
    {
        // Arrange
        string content = new('x', 1_048_577);
        JsonObject entry = Entry();
        entry["resources"]![1] = Resource("skill://unit-converter/references/checklist.md", content);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)),
            (uri, _) => ValueTask.FromResult(Text(uri, content)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client, new() { ListedResourceMaxSizeBytes = 2_097_152 });
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var resource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(resource);
        Assert.Equal(content, await resource.ReadAsync());
    }

    [Theory]
    [InlineData(0L)]
    [InlineData(-1L)]
    [InlineData(long.MinValue)]
    public void Constructor_InvalidResourceLimit_Throws(long limit)
    {
        // Arrange
        var client = new Mock<McpClient>();
        var options = new AgentMcpSkillsSourceOptions
        {
            ListedResourceMaxSizeBytes = limit,
        };

        // Act
        var exception = Assert.Throws<ArgumentOutOfRangeException>(() => new AgentMcpSkillsSource(client.Object, options));

        // Assert
        Assert.Equal(nameof(options.ListedResourceMaxSizeBytes), exception.ParamName);
    }

    [Fact]
    public async Task DiscoverAsync_LargeManifest_IsNotSubjectToResourceSizeLimitAsync()
    {
        // Arrange
        JsonObject result = ListResult(Entry());
        result["padding"] = new string('x', 1_048_577);
        var client = new Mock<McpClient>();
        client.Setup(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new JsonRpcResponse { Id = new RequestId(1), Result = result });
        using var loader = new McpListedSkillsLoader(client.Object);

        // Act
        var skills = await loader.DiscoverAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_Refresh_KeepsPreviouslyReturnedDigestsAndSizesAsync()
    {
        // Arrange
        const string UpdatedInstructions = SkillContent + "\nUpdated instructions.";
        const string ResourceUri = "skill://unit-converter/references/checklist.md";
        JsonObject updatedEntry = Entry(content: UpdatedInstructions);
        updatedEntry["resources"]![1] = Resource(ResourceUri, "Updated checklist.");
        int calls = 0;
        await using var server = CreateServer((_, _) =>
            ValueTask.FromResult<JsonNode?>(ListResult(++calls == 1 ? Entry() : updatedEntry)),
            (uri, _) => ValueTask.FromResult(Text(uri, uri == SkillUri ? UpdatedInstructions : "Updated checklist.")));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var first = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var updated = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await first.GetContentAsync());
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await first.GetResourceAsync("references/checklist.md"));
        Assert.Equal(UpdatedInstructions, await updated.GetContentAsync());
        var resource = Assert.IsType<AgentMcpListedSkillResource>(await updated.GetResourceAsync("references/checklist.md"));
        Assert.Equal("Updated checklist.", await resource.ReadAsync());
    }

    [Fact]
    public async Task GetSkillsAsync_ResourceMetadata_ReturnsReadableSkillAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, uri == SkillUri ? SkillContent : "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        string instructions = await skill.GetContentAsync();
        var supportingResource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.Equal(SkillContent, instructions);
        Assert.NotNull(supportingResource);
        Assert.Equal("Checklist.", await supportingResource.ReadAsync());
        Assert.Equal([SkillUri, "skill://unit-converter/references/checklist.md"], reads);
    }

    [Fact]
    public async Task GetSkillsAsync_UnknownFieldsAndCaseVariants_AreIgnoredAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        entry["Uri"] = null;
        entry["Frontmatter"] = false;
        entry["Resources"] = 42;
        entry["future-field"] = new JsonArray(1, 2);
        entry["frontmatter"]!["Name"] = null;
        entry["frontmatter"]!["Description"] = false;
        entry["resources"]![1]!["Uri"] = null;
        entry["resources"]![1]!["Digest"] = 42;
        entry["resources"]![1]!["Size"] = "ignored";
        JsonObject listResult = ListResult(entry);
        listResult["ttlMs"] = 300000;
        listResult["cacheScope"] = "public";
        listResult["NextCursor"] = "ignored-case-variant";
        listResult["future-field"] = true;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(listResult));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Equal("unit-converter", skill.Frontmatter.Name);
        Assert.Equal("Convert units.", skill.Frontmatter.Description);
    }

    [Theory]
    [InlineData("null", typeof(JsonException))]
    [InlineData("42", typeof(JsonException))]
    [InlineData("\"skill://other/SKILL.md\"", typeof(InvalidOperationException))]
    [InlineData("\"skill://unit-converter/../SKILL.md\"", typeof(InvalidOperationException))]
    public async Task GetSkillsAsync_InvalidInstructionUri_ThrowsBeforeSkippingAsync(string value, Type exceptionType)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![0]!["uri"] = JsonNode.Parse(value);
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync(exceptionType, () => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetSkillsAsync_DuplicateManifestUri_ThrowsWithoutReadingAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        var resources = Assert.IsType<JsonArray>(entry["resources"]);
        resources.Add(Resource("skill://unit-converter/references/checklist.md"));
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Contains("duplicate resource URI", exception.Message);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task GetSkillsAsync_InstructionsManifestEntry_IsRequiredAsync(bool includeInstructions, bool includeSupportingResources)
    {
        // Arrange
        JsonObject entry = Entry();
        var resources = Assert.IsType<JsonArray>(entry["resources"]);
        resources.RemoveAt(0);

        if (!includeSupportingResources)
        {
            resources.Clear();
        }

        if (includeInstructions)
        {
            resources.Insert(0, Resource(SkillUri));
        }

        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, SkillContent));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        if (!includeInstructions)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            Assert.Contains("must include SKILL.md", exception.Message);
            Assert.Empty(reads);
            return;
        }

        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var instructionResource = await skill.GetResourceAsync("SKILL.md");

        // Assert
        Assert.Null(instructionResource);
        Assert.Empty(reads);
        Assert.Equal(SkillContent, await skill.GetContentAsync());
        Assert.Equal(SkillUri, Assert.Single(reads));
    }

    [Fact]
    public async Task GetSkillsAsync_NullEntry_ThrowsAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult((JsonNode?)null)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_DuplicateUri_ReturnsAllEntriesWithoutWarningsAsync(bool conflicting)
    {
        // Arrange
        JsonObject duplicate = Entry();

        if (conflicting)
        {
            duplicate["frontmatter"]!["description"] = "Changed description.";
            duplicate["resources"]![1]!["uri"] = "skill://unit-converter/references/changed.md";
        }

        JsonObject another = (JsonObject)duplicate.DeepClone();

        if (conflicting)
        {
            another["frontmatter"]!["description"] = "Another description.";
        }

        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(), duplicate, another)));
        await using var client = await server.CreateClientAsync();
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        var loggerFactory = new Mock<ILoggerFactory>();
        loggerFactory.Setup(f => f.CreateLogger(It.IsAny<string>())).Returns(logger.Object);
        using var source = new AgentMcpSkillsSource(client, loggerFactory: loggerFactory.Object);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Equal(3, skills.Count);
        var skill = Assert.IsType<AgentMcpListedSkill>(skills[0]);
        Assert.Equal("Convert units.", skill.Frontmatter.Description);
        Assert.Null(await skill.GetResourceAsync("references/changed.md"));
        var secondSkill = Assert.IsType<AgentMcpListedSkill>(skills[1]);
        Assert.Equal(conflicting ? "Changed description." : "Convert units.", secondSkill.Frontmatter.Description);
        var thirdSkill = Assert.IsType<AgentMcpListedSkill>(skills[2]);
        Assert.Equal(conflicting ? "Another description." : "Convert units.", thirdSkill.Frontmatter.Description);
        logger.Verify(
            l => l.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.IsAny<It.IsAnyType>(),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Never());
    }

    [Theory]
    [InlineData("skill://unit-converter/")]
    [InlineData("skill://acme/unit-converter/")]
    [InlineData("github://owner/repo/skills/unit-converter/")]
    [InlineData("custom:skills/unit-converter/")]
    [InlineData("custom:unit-converter/")]
    public async Task GetContentAsync_LazyAndOriginBound_PreservesSchemeAsync(string root)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(root))),
            (uri, _) =>
            {
                reads.Add(uri);
                return ValueTask.FromResult(Text(uri, SkillContent));
            });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.IsType<AgentMcpListedSkill>(Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));
        Assert.Empty(reads);
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Equal(SkillContent, content);
        Assert.Equal(content, cached);
        Assert.Equal(root + "SKILL.md", Assert.Single(reads));
        Assert.Null(skill.Frontmatter.License);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_BlobSkillMd_ThrowsAsync(bool invalidUtf8)
    {
        // Arrange
        byte[] bytes = invalidUtf8 ? [0xff] : Encoding.UTF8.GetBytes(SkillContent);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [BlobResourceContents.FromBytes(bytes, uri, "text/markdown")],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        Assert.Equal($"The MCP server returned no text content for SKILL.md resource '{SkillUri}'.", exception.Message);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_EmptySkillMd_ThrowsAsync(bool noContents)
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (uri, _) => ValueTask.FromResult(noContents ? new ReadResourceResult { Contents = [] } : Text(uri, "")));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task GetContentAsync_MultipleContentBlocks_ThrowsAsync(bool firstText, bool secondText)
    {
        // Arrange
        byte[] bytes = Encoding.UTF8.GetBytes(SkillContent);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    firstText
                        ? new TextResourceContents { Uri = uri, Text = SkillContent }
                        : BlobResourceContents.FromBytes(bytes, uri),
                    secondText
                        ? new TextResourceContents { Uri = uri, Text = SkillContent }
                        : BlobResourceContents.FromBytes(bytes, uri),
                ],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());

        // Assert
        Assert.Contains("exactly one text or binary content block", exception.Message);
        Assert.Contains(SkillUri, exception.Message);
    }

    [Fact]
    public async Task GetContentAsync_SameUriOnDifferentServers_ReadsFromEachOriginAsync()
    {
        // Arrange
        await using var firstServer = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(content: SkillContent + "\nFirst server."))),
            (uri, _) => ValueTask.FromResult(Text(uri, SkillContent + "\nFirst server.")));
        await using var secondServer = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(content: SkillContent + "\nSecond server."))),
            (uri, _) => ValueTask.FromResult(Text(uri, SkillContent + "\nSecond server.")));
        await using var firstClient = await firstServer.CreateClientAsync();
        await using var secondClient = await secondServer.CreateClientAsync();
        using var firstSource = new AgentMcpSkillsSource(firstClient);
        using var secondSource = new AgentMcpSkillsSource(secondClient);
        var firstSkill = Assert.Single(await firstSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var secondSkill = Assert.Single(await secondSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        Assert.Equal(SkillContent + "\nFirst server.", await firstSkill.GetContentAsync());
        Assert.Equal(SkillContent + "\nSecond server.", await secondSkill.GetContentAsync());
    }

    [Theory]
    [InlineData("name")]
    [InlineData("description")]
    public async Task GetContentAsync_FetchedFrontmatterDiffersFromListing_ThrowsAsync(string field)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["frontmatter"]![field] = field == "name" ? "other-skill" : "Changed description.";
        if (field == "name")
        {
            entry["uri"] = "skill://other-skill/SKILL.md";
        }

        entry["resources"] = new JsonArray(Resource(entry["uri"]!.GetValue<string>(), SkillContent));

        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)),
            (uri, _) => ValueTask.FromResult(Text(uri, SkillContent)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        Assert.Contains($"frontmatter {field}", exception.Message);
        Assert.Contains(entry["uri"]!.GetValue<string>(), exception.Message);
    }

    [Theory]
    [InlineData("|", "Convert units.\n")]
    [InlineData(">", "Convert units.\n")]
    [InlineData("|-", "Convert units.")]
    [InlineData(">-", "Convert units.")]
    [InlineData("|+", "Convert units.\n\n")]
    [InlineData(">+", "Convert units.\n\n")]
    [InlineData("|2-", "Convert units.")]
    [InlineData(">2-", "Convert units.")]
    [InlineData("|2+", "Convert units.\n\n")]
    [InlineData(">2+", "Convert units.\n\n")]
    public async Task GetContentAsync_BlockScalarMatchesListing_ReturnsAndCachesContentAsync(string indicator, string description)
    {
        // Arrange
        string content = $"---\nname: unit-converter\ndescription: {indicator}\n  Convert units.\n\n---\nInstructions.";
        JsonObject entry = Entry(content: content);
        entry["frontmatter"]!["description"] = description;
        int reads = 0;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, content));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        string loaded = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Equal(content, loaded);
        Assert.Equal(content, cached);
        Assert.Equal(description, skill.Frontmatter.Description);
        Assert.Equal(1, reads);
    }

    [Theory]
    [InlineData("|", "Convert units.")]
    [InlineData(">", "Convert units.")]
    [InlineData("|-", "Convert units.\n")]
    [InlineData(">-", "Convert units.\n")]
    [InlineData("|+", "Convert units.\n")]
    [InlineData(">+", "Convert units.\n")]
    public async Task GetContentAsync_BlockScalarTrailingNewlinesDifferFromListing_ThrowsAsync(string indicator, string description)
    {
        // Arrange
        string content = $"---\nname: unit-converter\ndescription: {indicator}\n  Convert units.\n\n---\nInstructions.";
        JsonObject entry = Entry(content: content);
        entry["frontmatter"]!["description"] = description;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)),
            (uri, _) => ValueTask.FromResult(Text(uri, content)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        Assert.Contains("frontmatter description", exception.Message);
    }

    [Fact]
    public async Task GetContentAsync_InvalidFrontmatter_LogsParserDiagnosticAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(content: "No frontmatter."))),
            (uri, _) => ValueTask.FromResult(Text(uri, "No frontmatter.")));
        await using var client = await server.CreateClientAsync();
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        var loggerFactory = new Mock<ILoggerFactory>();
        loggerFactory.Setup(f => f.CreateLogger(It.IsAny<string>())).Returns(logger.Object);
        using var source = new AgentMcpSkillsSource(client, loggerFactory: loggerFactory.Object);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        logger.Verify(
            l => l.Log(
                LogLevel.Error,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((state, _) => state.ToString()!.Contains(SkillUri)),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Once());
    }

    [Theory]
    [InlineData("references/checklist.md", false)]
    [InlineData("references\\checklist.md", false)]
    [InlineData("assets/icon.bin", true)]
    [InlineData("empty.txt", false)]
    public async Task GetResourceAsync_ManifestFile_ReturnsTextOrBinaryAsync(string name, bool binary)
    {
        // Arrange
        List<string> reads = [];
        string uri = "skill://unit-converter/" + name.Replace('\\', '/');
        byte[] bytes = [1, 2, 3, 4];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (requested, _) =>
        {
            reads.Add(requested);
            return ValueTask.FromResult(binary
                ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(bytes, requested, "application/octet-stream")] }
                : Text(requested, name == "empty.txt" ? "" : "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var resource = await skill.GetResourceAsync(name);
        var content = await Assert.IsType<AgentMcpListedSkillResource>(resource).ReadAsync();

        // Assert
        Assert.Equal(uri, Assert.Single(reads));
        if (binary)
        {
            var data = Assert.IsType<DataContent>(content);
            Assert.Equal(bytes, data.Data.ToArray());
            Assert.Equal("application/octet-stream", data.MediaType);
        }
        else
        {
            Assert.Equal(name == "empty.txt" ? null : "Checklist.", content);
        }
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task GetResourceAsync_MultipleContentBlocks_ThrowsAsync(bool firstText, bool secondText)
    {
        // Arrange
        byte[] bytes = Encoding.UTF8.GetBytes("Checklist.");
        JsonObject entry = Entry();
        entry["resources"]![1] = Resource("skill://unit-converter/references/checklist.md", bytes);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    firstText
                        ? new TextResourceContents { Uri = uri, Text = "Checklist." }
                        : BlobResourceContents.FromBytes(bytes, uri),
                    secondText
                        ? new TextResourceContents { Uri = "skill://other/checklist.md", Text = "Checklist." }
                        : BlobResourceContents.FromBytes(bytes, "skill://other/checklist.md"),
                ],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.IsType<AgentMcpListedSkill>(Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("references/checklist.md"));

        // Assert
        Assert.Contains("exactly one text or binary content block", exception.Message);
        Assert.Contains("skill://unit-converter/references/checklist.md", exception.Message);
    }

    [Theory]
    [InlineData(null, typeof(ArgumentNullException))]
    [InlineData("", typeof(ArgumentException))]
    [InlineData(" ", typeof(ArgumentException))]
    [InlineData("\t\r\n", typeof(ArgumentException))]
    public async Task GetResourceAsync_NullOrWhitespaceName_ThrowsWithoutReadingAsync(string? name, Type exceptionType)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var exception = await Assert.ThrowsAsync(exceptionType, async () => await skill.GetResourceAsync(name!));

        // Assert
        Assert.Equal("name", Assert.IsAssignableFrom<ArgumentException>(exception).ParamName);
        Assert.Empty(reads);
    }

    [Theory]
    [InlineData("../escape.md")]
    [InlineData("%252e%252e/escape.md")]
    [InlineData("/etc/passwd")]
    [InlineData("https://example.com/escape.md")]
    [InlineData("references/guide.md?value=%00")]
    [InlineData("not-listed.md")]
    public async Task GetResourceAsync_UnsafeOrUnlistedName_DoesNotReadOrLogAsync(string name)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        var loggerFactory = new Mock<ILoggerFactory>();
        loggerFactory.Setup(f => f.CreateLogger(It.IsAny<string>())).Returns(logger.Object);
        using var source = new AgentMcpSkillsSource(client, loggerFactory: loggerFactory.Object);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        logger.Invocations.Clear();

        // Act
        var resource = await skill.GetResourceAsync(name);

        // Assert
        Assert.Null(resource);
        Assert.Empty(reads);
        logger.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task GetResourceAsync_ReadFailure_PropagatesAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (_, _) => throw new McpProtocolException("Resource unavailable.", McpErrorCode.ResourceNotFound));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        await Assert.ThrowsAsync<McpProtocolException>(async () => await skill.GetResourceAsync("references/checklist.md"));
    }

    [Fact]
    public async Task GetResourceAsync_Cancelled_PropagatesAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (uri, _) => ValueTask.FromResult(Text(uri, "Checklist.")));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await skill.GetResourceAsync("references/checklist.md", cts.Token));
    }

    [Fact]
    public async Task GetContentAsync_TextBlock_DoesNotRequireUriMatchAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [new TextResourceContents { Uri = "skill://other/SKILL.md", Text = SkillContent }],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        string content = await skill.GetContentAsync();

        // Assert
        Assert.Equal(SkillContent, content);
    }

    [Fact]
    public async Task GetResourceAsync_TextBlock_DoesNotRequireUriMatchAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![1] = Resource("skill://unit-converter/references/checklist.md", "Checklist.");
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [new TextResourceContents { Uri = "skill://other/checklist.md", Text = "Checklist." }],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var resource = Assert.IsType<AgentMcpListedSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
        var content = await resource.ReadAsync();

        // Assert
        Assert.Equal("Checklist.", content);
    }

    [Fact]
    public async Task ReadAsync_EmptyResourceContent_ReturnsNullAsync()
    {
        // Arrange
        var resource = new AgentMcpListedSkillResource("empty.txt", new TextResourceContents { Uri = "skill://unit-converter/empty.txt", Text = "" });

        // Act
        var content = await resource.ReadAsync();

        // Assert
        Assert.Null(content);
    }

    [Fact]
    public async Task UseMcpSkills_ServerWithSkillsExtension_ExposesWorkingSkillToolsAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (uri, _) => ValueTask.FromResult(Text(uri, uri == SkillUri ? SkillContent : "Checklist.")));
        await using var client = await server.CreateClientAsync();
        using var provider = new AgentSkillsProviderBuilder().UseMcpSkills(client).Build();
        var context = new AIContextProvider.InvokingContext(TestAgentSkillsSourceContextFactory.Create().Agent, session: null, new AIContext());
        using var services = new ServiceCollection().BuildServiceProvider();

        // Act
        var result = await provider.InvokingAsync(context, CancellationToken.None);
        var loadTool = Assert.IsType<AIFunction>(Assert.Single(result.Tools!, tool => tool.Name == "load_skill"), exactMatch: false);
        var resourceTool = Assert.IsType<AIFunction>(Assert.Single(result.Tools!, tool => tool.Name == "read_skill_resource"), exactMatch: false);
        var loaded = await loadTool.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?> { ["skillName"] = "unit-converter" }));
        var resource = await resourceTool.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?>
        {
            ["skillName"] = "unit-converter",
            ["resourceName"] = "references/checklist.md",
        })
        { Services = services });

        // Assert
        Assert.Contains("unit-converter", result.Instructions);
        Assert.Equal(SkillContent, loaded!.ToString());
        Assert.Equal("Checklist.", resource!.ToString());
    }

    private static JsonObject Entry(string root = "skill://unit-converter/", string content = SkillContent) => new()
    {
        ["uri"] = root + "SKILL.md",
        ["frontmatter"] = new JsonObject
        {
            ["name"] = "unit-converter",
            ["description"] = "Convert units.",
            ["license"] = "MIT",
            ["future-field"] = new JsonObject { ["nested"] = 42 },
        },
        ["resources"] = new JsonArray(
            Resource(root + "SKILL.md", content),
            Resource(root + "references/checklist.md"),
            Resource(root + "assets/icon.bin"),
            Resource(root + "empty.txt")),
    };

    private static JsonObject Resource(string uri) => uri.EndsWith("/assets/icon.bin", StringComparison.Ordinal)
        ? Resource(uri, new byte[] { 1, 2, 3, 4 })
        : Resource(uri, uri.EndsWith("/SKILL.md", StringComparison.Ordinal) ? SkillContent
            : uri.EndsWith("/empty.txt", StringComparison.Ordinal) ? "" : "Checklist.");

    private static JsonObject Resource(string uri, string text) => Resource(uri, Encoding.UTF8.GetBytes(text));

    [SuppressMessage("Globalization", "CA1308:Normalize strings to uppercase", Justification = "Resource digests require lowercase hexadecimal characters.")]
    private static JsonObject Resource(string uri, byte[] bytes) => new()
    {
        ["uri"] = uri,
        ["digest"] = "sha256:" + Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
        ["size"] = bytes.Length,
    };

    private static JsonObject ListResult(params JsonNode?[] entries) => new()
    {
        ["resultType"] = "complete",
        ["skills"] = new JsonArray(entries),
    };

    private static ReadResourceResult Text(string uri, string text) => new()
    {
        Contents = [new TextResourceContents { Uri = uri, Text = text }],
    };

#pragma warning disable MCPEXP002 // Custom extension methods require raw server request handlers.
    private static InMemoryMcpServer CreateServer(
        Func<JsonRpcRequest, CancellationToken, ValueTask<JsonNode?>> listHandler,
        Func<string, CancellationToken, ValueTask<ReadResourceResult>>? readHandler = null) =>
        new(builder => builder.WithReadResourceHandler((request, token) =>
            readHandler is not null
                ? readHandler(request.Params!.Uri, token)
                : throw new McpProtocolException("Resource unavailable.", McpErrorCode.ResourceNotFound)),
            options =>
            {
                options.Capabilities = new ServerCapabilities
                {
                    Resources = new(),
                    Extensions = new Dictionary<string, object>
                    {
                        ["io.modelcontextprotocol/skills"] = JsonSerializer.Deserialize<JsonElement>("{}"),
                    },
                };
                options.RequestHandlers = [new() { Method = "skills/list", Handler = listHandler }];
            });
#pragma warning restore MCPEXP002
}
