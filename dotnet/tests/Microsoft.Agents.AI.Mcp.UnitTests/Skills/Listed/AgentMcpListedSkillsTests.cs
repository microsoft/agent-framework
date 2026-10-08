// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests discovery and content access for skills returned by <c>skills/list</c>.
/// </summary>
public sealed class AgentMcpListedSkillsTests
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
                return ValueTask.FromResult(Text(uri, "Supporting content."));
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
        JsonException exception = await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
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

    [Fact]
    public async Task GetSkillsAsync_ListCancellation_PropagatesAsync()
    {
        // Arrange
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var server = CreateServer(async (_, token) =>
        {
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

    [Fact]
    public async Task GetSkillsAsync_NoDeclaration_ReadsIndexInsteadOfListAsync()
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
        using var source = new AgentMcpSkillsSource(client);

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
    [InlineData("uri", "null")]
    [InlineData("uri", "\"skill://other/SKILL.md\"")]
    [InlineData("uri", "\"relative/SKILL.md\"")]
    [InlineData("frontmatter", "null")]
    [InlineData("frontmatter", "[]")]
    [InlineData("frontmatter", "\"metadata\"")]
    [InlineData("frontmatter", "{}")]
    [InlineData("frontmatter", """{"name":"unit-converter"}""")]
    [InlineData("frontmatter", """{"description":"Convert units."}""")]
    [InlineData("frontmatter", """{"name":null,"description":"Convert units."}""")]
    [InlineData("frontmatter", """{"name":42,"description":"Convert units."}""")]
    [InlineData("frontmatter", """{"name":"INVALID","description":"Description."}""")]
    [InlineData("frontmatter", """{"name":"unit-converter","description":null}""")]
    [InlineData("frontmatter", """{"name":"unit-converter","description":false}""")]
    [InlineData("resources", "null")]
    [InlineData("resources", "false")]
    [InlineData("resources", "\"other\"")]
    [InlineData("resources", "\"dynamic\"")]
    [InlineData("resources", "{}")]
    [InlineData("resources", "[null]")]
    [InlineData("resources", "[42]")]
    [InlineData("resources", "[[]]")]
    [InlineData("resources", "[{}]")]
    [InlineData("resources", """[{"uri":null}]""")]
    [InlineData("resources", """[{"uri":42}]""")]
    [InlineData("resources", """[{"uri":true}]""")]
    public async Task GetSkillsAsync_InvalidEntry_ThrowsAsync(string field, string value)
    {
        // Arrange
        JsonObject entry = Entry();
        entry[field] = JsonNode.Parse(value);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
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
        JsonException exception = await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

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
    [InlineData("uri", "\"skill://other/checklist.md\"")]
    [InlineData("uri", "\"skill://unit-converter/../escape.md\"")]
    [InlineData("uri", "\"skill://unit-converter/%252e%252e/escape.md\"")]
    [InlineData("uri", "\"skill://unit-converter/\"")]
    [InlineData("uri", "null")]
    public async Task GetSkillsAsync_InvalidManifestEntry_ThrowsAsync(string field, string value)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["resources"]![1]![field] = JsonNode.Parse(value);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public async Task GetSkillsAsync_MissingResourceUri_ThrowsAsync(int resourceIndex)
    {
        // Arrange
        JsonObject entry = Entry();
        Assert.IsType<JsonObject>(entry["resources"]![resourceIndex]).Remove("uri");
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        JsonException exception = await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Contains("uri", exception.Message);
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
        entry["resources"]![1]!["digest"] = 42;
        entry["resources"]![1]!["size"] = "ignored";
        JsonObject listResult = ListResult(entry);
        listResult["ttlMs"] = 300000;
        listResult["cacheScope"] = "public";
        listResult["nextCursor"] = "next-page";
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
    [InlineData("null")]
    [InlineData("42")]
    [InlineData("\"skill://other/SKILL.md\"")]
    [InlineData("\"skill://unit-converter/../SKILL.md\"")]
    public async Task GetSkillsAsync_InvalidInstructionUri_ThrowsBeforeSkippingAsync(string value)
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
        await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetResourceAsync_DuplicateManifestUri_ReadsSupportingResourceAsync()
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
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var resource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(resource);
        Assert.Equal("Checklist.", await resource.ReadAsync());
        Assert.Equal("skill://unit-converter/references/checklist.md", Assert.Single(reads));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task GetContentAsync_InstructionsOutsideSupportingManifest_ReadsDirectlyAsync(bool includeInstructions, bool includeSupportingResources)
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
        await Assert.ThrowsAsync<JsonException>(() => source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
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
                return ValueTask.FromResult(new ReadResourceResult
                {
                    Contents =
                    [
                        new TextResourceContents { Uri = root + "unrelated.md", Text = "Additional instructions." },
                        new TextResourceContents { Uri = uri, Text = SkillContent },
                    ],
                });
            });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.IsType<AgentMcpListedSkill>(Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));
        Assert.Empty(reads);
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Equal("Additional instructions.\n" + SkillContent, content);
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

    [Fact]
    public async Task GetContentAsync_MixedContent_ConcatenatesTextAndIgnoresBlobsAsync()
    {
        // Arrange
        byte[] bytes = [0xff];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    new TextResourceContents { Uri = uri, Text = "First text block." },
                    BlobResourceContents.FromBytes(bytes, uri, "text/markdown"),
                    new TextResourceContents { Uri = "skill://other/SKILL.md", Text = "Second text block." },
                ],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        string content = await skill.GetContentAsync();

        // Assert
        Assert.Equal("First text block.\nSecond text block.", content);
    }

    [Fact]
    public async Task GetContentAsync_SameUriOnDifferentServers_ReadsFromEachOriginAsync()
    {
        // Arrange
        await using var firstServer = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (uri, _) => ValueTask.FromResult(Text(uri, "First server.")));
        await using var secondServer = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())),
            (uri, _) => ValueTask.FromResult(Text(uri, "Second server.")));
        await using var firstClient = await firstServer.CreateClientAsync();
        await using var secondClient = await secondServer.CreateClientAsync();
        using var firstSource = new AgentMcpSkillsSource(firstClient);
        using var secondSource = new AgentMcpSkillsSource(secondClient);
        var firstSkill = Assert.Single(await firstSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var secondSkill = Assert.Single(await secondSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        Assert.Equal("First server.", await firstSkill.GetContentAsync());
        Assert.Equal("Second server.", await secondSkill.GetContentAsync());
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

    [Fact]
    public async Task GetResourceAsync_MultipleUris_ReturnsFirstBlobAsync()
    {
        // Arrange
        byte[] bytes = [1, 2, 3, 4];
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    new TextResourceContents { Uri = "skill://other/guide.md", Text = "Ignored text." },
                    BlobResourceContents.FromBytes(bytes, "skill://other/icon.bin", "application/octet-stream"),
                    BlobResourceContents.FromBytes(new byte[] { 5, 6 }, uri, "application/octet-stream"),
                    new TextResourceContents { Uri = uri, Text = "Checklist." },
                ],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.IsType<AgentMcpListedSkill>(Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));

        // Act
        var resource = Assert.IsType<AgentMcpListedSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
        var content = await resource.ReadAsync();

        // Assert
        var data = Assert.IsType<DataContent>(content);
        Assert.Equal(bytes, data.Data.ToArray());
        Assert.Equal("application/octet-stream", data.MediaType);
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

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_TextBlocks_DoesNotRequireUriMatchAsync(bool duplicate)
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = duplicate
                    ? [new TextResourceContents { Uri = uri, Text = SkillContent }, new TextResourceContents { Uri = uri, Text = SkillContent }]
                    : [new TextResourceContents { Uri = "skill://other/SKILL.md", Text = SkillContent }],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        string content = await skill.GetContentAsync();

        // Assert
        Assert.Equal(duplicate ? SkillContent + "\n" + SkillContent : SkillContent, content);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetResourceAsync_TextBlocks_DoesNotRequireUriMatchAsync(bool duplicate)
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry())), (uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = duplicate
                    ? [new TextResourceContents { Uri = uri, Text = "Checklist." }, new TextResourceContents { Uri = uri, Text = "Checklist." }]
                    : [new TextResourceContents { Uri = "skill://other/checklist.md", Text = "Checklist." }],
            }));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        var resource = Assert.IsType<AgentMcpListedSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
        var content = await resource.ReadAsync();

        // Assert
        Assert.Equal(duplicate ? "Checklist.\nChecklist." : "Checklist.", content);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ReadAsync_EmptyResourceContent_ReturnsNullAsync(bool noContents)
    {
        // Arrange
        var result = noContents ? new ReadResourceResult { Contents = [] } : Text("skill://unit-converter/empty.txt", "");
        var resource = new AgentMcpListedSkillResource("empty.txt", result);

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

    private static JsonObject Entry(string root = "skill://unit-converter/") => new()
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
            Resource(root + "SKILL.md"),
            Resource(root + "references/checklist.md"),
            Resource(root + "assets/icon.bin"),
            Resource(root + "empty.txt")),
    };

    private static JsonObject Resource(string uri) => new()
    {
        ["uri"] = uri,
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
