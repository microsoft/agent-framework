// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests instruction and supporting resource access for listed skills.
/// </summary>
public sealed class AgentMcpListedSkillTests
{
    private const string SkillRootUri = "skill://unit-converter/";
    private const string SkillUri = SkillRootUri + "SKILL.md";
    private const string SkillContent = "---\nname: unit-converter\ndescription: Convert units.\n---\nInstructions.";

    [Fact]
    public async Task Constructor_PreservesProvidedFrontmatterAsync()
    {
        // Arrange
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, SkillContent)));
        await using var client = await server.CreateClientAsync();
        var frontmatter = new AgentSkillFrontmatter("unit-converter", "Convert units.") { License = "MIT" };

        // Act
        var skill = new AgentMcpListedSkill(frontmatter, SkillUri, [Resource(SkillUri, SkillContent)], client);

        // Assert
        Assert.Same(frontmatter, skill.Frontmatter);
    }

    [Fact]
    public async Task GetContentAsync_ResourceList_FindsInstructionsByExactUriAsync()
    {
        // Arrange
        const string NestedUri = SkillRootUri + "nested/SKILL.md";
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, uri == SkillUri ? SkillContent : "Nested instructions."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = new AgentMcpListedSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri,
        [
            Resource(NestedUri, "Nested instructions."),
            Resource(SkillUri, SkillContent),
        ], client);

        // Act
        string instructions = await skill.GetContentAsync();
        var nestedResource = await skill.GetResourceAsync("nested/SKILL.md");

        // Assert
        Assert.Equal(SkillContent, instructions);
        Assert.NotNull(nestedResource);
        Assert.Equal("Nested instructions.", await nestedResource.ReadAsync());
        Assert.Equal([SkillUri, NestedUri], reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_MissingInstructionResource_ThrowsWithoutReadingAsync(bool includeNestedInstructions)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, SkillContent));
        });
        await using var client = await server.CreateClientAsync();
        var frontmatter = new AgentSkillFrontmatter("unit-converter", "Convert units.");
        McpListedSkillResourceEntry[] resources = includeNestedInstructions
            ? [Resource(SkillRootUri + "nested/SKILL.md", SkillContent)]
            : [];
        var skill = new AgentMcpListedSkill(frontmatter, SkillUri, resources, client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());

        // Assert
        Assert.Contains("must include the skill's SKILL.md", exception.Message);
        Assert.Contains(SkillUri, exception.Message);
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetResourceAsync_SeparateSkills_KeepOwnSupportingResourcesAsync()
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        var first = CreateSkill(client);
        var updated = CreateSkill(client, resources: [Resource(SkillRootUri + "references/updated.md", "Checklist.")]);

        // Act
        var originalResource = await first.GetResourceAsync("references/checklist.md");
        var unavailableUpdatedResource = await first.GetResourceAsync("references/updated.md");
        var updatedResource = await updated.GetResourceAsync("references/updated.md");
        var unavailableOriginalResource = await updated.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(originalResource);
        Assert.Null(unavailableUpdatedResource);
        Assert.NotNull(updatedResource);
        Assert.Null(unavailableOriginalResource);
        Assert.Equal([SkillRootUri + "references/checklist.md", SkillRootUri + "references/updated.md"], reads);
    }

    [Fact]
    public async Task GetContentAsync_AndGetResourceAsync_ReadDeclaredResourcesAsync()
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, uri == SkillUri ? SkillContent : "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act
        string instructions = await skill.GetContentAsync();
        var supportingResource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.Equal(SkillContent, instructions);
        Assert.NotNull(supportingResource);
        Assert.Equal("Checklist.", await supportingResource.ReadAsync());
        Assert.Equal([SkillUri, SkillRootUri + "references/checklist.md"], reads);
    }

    [Fact]
    public async Task GetResourceAsync_MultipleManifestEntries_VerifiesRequestedResourceAsync()
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources:
        [
            Resource(SkillRootUri + "references/other.md", "Different."),
            Resource(SkillRootUri + "references/checklist.md", "Checklist."),
        ]);

        // Act
        var resource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(resource);
        Assert.Equal("Checklist.", await resource.ReadAsync());
        Assert.Equal(SkillRootUri + "references/checklist.md", Assert.Single(reads));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_OutsideSupportingResources_ReadsDirectlyAsync(bool includeSupportingResources)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, SkillContent));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: includeSupportingResources
            ? [Resource(SkillRootUri + "references/checklist.md", "Checklist.")]
            : []);

        // Act
        var instructionResource = await skill.GetResourceAsync("SKILL.md");

        // Assert
        Assert.Null(instructionResource);
        Assert.Empty(reads);
        Assert.Equal(SkillContent, await skill.GetContentAsync());
        Assert.Equal(SkillUri, Assert.Single(reads));
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
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    new TextResourceContents { Uri = uri, Text = SkillContent },
                    new TextResourceContents { Uri = root + "unrelated.md", Text = "Additional instructions." },
                ],
            });
        });
        await using var client = await server.CreateClientAsync();

        // Act
        var skill = CreateSkill(client, root, content: SkillContent + "\nAdditional instructions.");
        Assert.Empty(reads);
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Equal(SkillContent + "\nAdditional instructions.", content);
        Assert.Equal(content, cached);
        Assert.Equal(root + "SKILL.md", Assert.Single(reads));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_BlobSkillMd_ThrowsAsync(bool invalidUtf8)
    {
        // Arrange
        byte[] bytes = invalidUtf8 ? [0xff] : Encoding.UTF8.GetBytes(SkillContent);
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [BlobResourceContents.FromBytes(bytes, uri, "text/markdown")],
            }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

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
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(noContents ? new ReadResourceResult { Contents = [] } : Text(uri, "")));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
    }

    [Fact]
    public async Task GetContentAsync_MixedContent_ConcatenatesTextAndIgnoresBlobsAsync()
    {
        // Arrange
        byte[] bytes = [0xff];
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    new TextResourceContents { Uri = uri, Text = SkillContent },
                    BlobResourceContents.FromBytes(bytes, uri, "text/markdown"),
                    new TextResourceContents { Uri = "skill://other/SKILL.md", Text = "Second text block." },
                ],
            }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, content: SkillContent + "\nSecond text block.");

        // Act
        string content = await skill.GetContentAsync();

        // Assert
        Assert.Equal(SkillContent + "\nSecond text block.", content);
    }

    [Fact]
    public async Task GetContentAsync_SameUriOnDifferentServers_ReadsFromEachOriginAsync()
    {
        // Arrange
        await using var firstServer = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, SkillContent + "\nFirst server.")));
        await using var secondServer = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, SkillContent + "\nSecond server.")));
        await using var firstClient = await firstServer.CreateClientAsync();
        await using var secondClient = await secondServer.CreateClientAsync();
        var firstSkill = CreateSkill(firstClient, content: SkillContent + "\nFirst server.");
        var secondSkill = CreateSkill(secondClient, content: SkillContent + "\nSecond server.");

        // Act & Assert
        Assert.Equal(SkillContent + "\nFirst server.", await firstSkill.GetContentAsync());
        Assert.Equal(SkillContent + "\nSecond server.", await secondSkill.GetContentAsync());
    }

    [Theory]
    [InlineData("---\nname: other-skill\ndescription: Convert units.\n---\nInstructions.", "name")]
    [InlineData("---\nname: unit-converter\ndescription: Different instructions.\n---\nInstructions.", "description")]
    [InlineData("---\nname: unit-converter\ndescription: convert units.\n---\nInstructions.", "description")]
    [InlineData("---\nname: unit-converter\ndescription: \" Convert units. \"\n---\nInstructions.", "description")]
    [InlineData("---\nname: unit-converter\ndescription: \"\"\n---\nInstructions.", "description")]
    public async Task GetContentAsync_MismatchedFrontmatter_ThrowsWithoutCachingAsync(string content, string field)
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, content));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, content: content);
        var advertised = skill.Frontmatter;

        // Act & Assert
        for (int i = 0; i < 2; i++)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Contains(SkillUri, exception.Message);
            Assert.Contains($"frontmatter {field}", exception.Message);
            Assert.Contains("skills/list", exception.Message);
        }

        Assert.Equal(2, reads);
        Assert.Same(advertised, skill.Frontmatter);
        Assert.Equal("unit-converter", skill.Frontmatter.Name);
        Assert.Equal("Convert units.", skill.Frontmatter.Description);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_InvalidFrontmatter_ThrowsWithoutCachingAsync(bool overlengthCompatibility)
    {
        // Arrange
        string content = overlengthCompatibility
            ? SkillContent.Replace("\n---\n", $"\ncompatibility: {new string('a', 501)}\n---\n")
            : "Instructions without frontmatter.";
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, content));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, content: content);

        // Act & Assert
        for (int i = 0; i < 2; i++)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Equal($"SKILL.md resource '{SkillUri}' contains invalid frontmatter.", exception.Message);
        }

        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_AfterVerificationFailure_RetriesAndCachesVerifiedContentAsync(bool invalidFrontmatter)
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, reads > 1
                ? SkillContent
                : invalidFrontmatter ? "Invalid frontmatter." : SkillContent.Replace("Convert units.", "Changed.")));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        Assert.Equal(SkillContent, await skill.GetContentAsync());
        Assert.Equal(SkillContent, await skill.GetContentAsync());
        Assert.Equal(2, reads);
    }

    [Fact]
    public async Task GetContentAsync_OptionalFrontmatter_IsNotComparedOrAppliedAsync()
    {
        // Arrange
        const string Content = "---\nname: unit-converter\ndescription: Convert units.\nlicense: Apache-2.0\ncompatibility: Any runtime\nallowed-tools: read\nmetadata:\n  author: Example\n---\nInstructions.";
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, Content)));
        await using var client = await server.CreateClientAsync();
        var frontmatter = new AgentSkillFrontmatter("unit-converter", "Convert units.") { License = "MIT" };
        var skill = new AgentMcpListedSkill(frontmatter, SkillUri, [Resource(SkillUri, Content)], client);

        // Act
        string verified = await skill.GetContentAsync();

        // Assert
        Assert.Equal(Content, verified);
        Assert.Same(frontmatter, skill.Frontmatter);
        Assert.Equal("MIT", skill.Frontmatter.License);
        Assert.Null(skill.Frontmatter.Compatibility);
        Assert.Null(skill.Frontmatter.AllowedTools);
        Assert.Null(skill.Frontmatter.Metadata);
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
        string uri = SkillRootUri + name.Replace('\\', '/');
        byte[] bytes = [1, 2, 3, 4];
        await using var server = CreateServer((requested, _) =>
        {
            reads.Add(requested);
            return ValueTask.FromResult(binary
                ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(bytes, requested, "application/octet-stream")] }
                : Text(requested, name == "empty.txt" ? "" : "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

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
        await using var server = CreateServer((uri, _) =>
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
        var skill = CreateSkill(client, resources: [Resource(SkillRootUri + "references/checklist.md", bytes)]);

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
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

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
    public async Task GetResourceAsync_UnsafeName_DoesNotReadAsync(string name)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(SkillRootUri + name, "Checklist.")]);

        // Act
        var resource = await skill.GetResourceAsync(name);

        // Assert
        Assert.Null(resource);
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetResourceAsync_UnlistedName_DoesNotReadAsync()
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act
        var resource = await skill.GetResourceAsync("not-listed.md");

        // Assert
        Assert.Null(resource);
        Assert.Empty(reads);
    }

    [Fact]
    public async Task GetResourceAsync_ReadFailure_PropagatesAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => throw new McpProtocolException("Resource unavailable.", McpErrorCode.ResourceNotFound));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act & Assert
        await Assert.ThrowsAsync<McpProtocolException>(async () => await skill.GetResourceAsync("references/checklist.md"));
    }

    [Fact]
    public async Task GetResourceAsync_Cancelled_PropagatesAsync()
    {
        // Arrange
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, "Checklist.")));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);
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
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = duplicate
                    ? [new TextResourceContents { Uri = uri, Text = SkillContent }, new TextResourceContents { Uri = uri, Text = SkillContent }]
                    : [new TextResourceContents { Uri = "skill://other/SKILL.md", Text = SkillContent }],
            }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, content: duplicate ? SkillContent + "\n" + SkillContent : SkillContent);

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
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = duplicate
                    ? [new TextResourceContents { Uri = uri, Text = "Checklist." }, new TextResourceContents { Uri = uri, Text = "Checklist." }]
                    : [new TextResourceContents { Uri = "skill://other/checklist.md", Text = "Checklist." }],
            }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources:
        [
            Resource(SkillRootUri + "references/checklist.md", duplicate ? "Checklist.\nChecklist." : "Checklist."),
        ]);

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
        var result = noContents ? new ReadResourceResult { Contents = [] } : Text(SkillRootUri + "empty.txt", "");
        var resource = new AgentMcpListedSkillResource("empty.txt", result);

        // Act
        var content = await resource.ReadAsync();

        // Assert
        Assert.Null(content);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_IntegrityFailure_RetriesAndCachesOnlyVerifiedContentAsync(bool sizeMismatch)
    {
        // Arrange
        string changed = sizeMismatch ? SkillContent + "\nChanged." : SkillContent.Replace("Instructions.", "Changed text.");
        Assert.Equal(SkillContent.Length, changed.Length - (sizeMismatch ? "\nChanged.".Length : 0));
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(Text(uri, ++reads == 1 ? changed : SkillContent)));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Contains(sizeMismatch ? "byte size" : "SHA-256 digest", exception.Message);
        Assert.Contains(SkillUri, exception.Message);
        Assert.Equal(SkillContent, content);
        Assert.Equal(content, cached);
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task GetResourceAsync_IntegrityFailure_ThrowsWithoutReturningContentAsync(bool binary, bool sizeMismatch)
    {
        // Arrange
        const string Uri = SkillRootUri + "references/checklist.md";
        byte[] expected = Encoding.UTF8.GetBytes("Checklist.");
        byte[] changed = Encoding.UTF8.GetBytes(sizeMismatch ? "Changed checklist." : "Different.");
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(binary
                ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(changed, uri, "application/octet-stream")] }
                : Text(uri, Encoding.UTF8.GetString(changed))));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, expected)]);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("references/checklist.md"));

        // Assert
        Assert.Contains(sizeMismatch ? "byte size" : "SHA-256 digest", exception.Message);
        Assert.Contains(Uri, exception.Message);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_Utf8Content_UsesByteCountAsync(bool useCharacterCount)
    {
        // Arrange
        const string Content = SkillContent + "\n\u00e9\U0001f600\r\n";
        var instructions = Resource(SkillUri, Content);
        Assert.True(instructions.Size > Content.Length);
        if (useCharacterCount)
        {
            instructions = new() { Uri = instructions.Uri, Digest = instructions.Digest, Size = Content.Length };
        }

        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, Content)));
        await using var client = await server.CreateClientAsync();
        var skill = new AgentMcpListedSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri, [instructions], client);

        // Act & Assert
        if (useCharacterCount)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Contains("byte size", exception.Message);
        }
        else
        {
            Assert.Equal(Content, await skill.GetContentAsync());
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetResourceAsync_Utf8Content_VerifiesTextAndDecodedBlobAsync(bool binary)
    {
        // Arrange
        const string Content = "\u00e9\U0001f600\r\n";
        const string Uri = SkillRootUri + "references/checklist.md";
        byte[] bytes = Encoding.UTF8.GetBytes(Content);
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(binary
                ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(bytes, uri, "text/plain")] }
                : Text(uri, Content)));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)]);

        // Act
        var resource = Assert.IsType<AgentMcpListedSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
        var content = await resource.ReadAsync();

        // Assert
        if (binary)
        {
            Assert.Equal(bytes, Assert.IsType<DataContent>(content).Data.ToArray());
        }
        else
        {
            Assert.Equal(Content, content);
        }
    }

    [Fact]
    public async Task GetResourceAsync_MissingContent_ThrowsEvenWhenEmptyFileIsListedAsync()
    {
        // Arrange
        await using var server = CreateServer((_, _) => ValueTask.FromResult(new ReadResourceResult { Contents = [] }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("empty.txt"));

        // Assert
        Assert.Contains("returned no content", exception.Message);
        Assert.Contains(SkillRootUri + "empty.txt", exception.Message);
    }

    private static AgentMcpListedSkill CreateSkill(
        McpClient client,
        string root = SkillRootUri,
        IReadOnlyList<McpListedSkillResourceEntry>? resources = null,
        string content = SkillContent) =>
        new(new AgentSkillFrontmatter("unit-converter", "Convert units."), root + "SKILL.md",
        [
            Resource(root + "SKILL.md", content),
            .. resources ??
            [
                Resource(root + "references/checklist.md", "Checklist."),
                Resource(root + "assets/icon.bin", new byte[] { 1, 2, 3, 4 }),
                Resource(root + "empty.txt", ""),
            ],
        ], client);

    private static McpListedSkillResourceEntry Resource(string uri, string text) => Resource(uri, Encoding.UTF8.GetBytes(text));

    [SuppressMessage("Globalization", "CA1308:Normalize strings to uppercase", Justification = "Resource digests require lowercase hexadecimal characters.")]
    private static McpListedSkillResourceEntry Resource(string uri, byte[] bytes) => new()
    {
        Uri = uri,
        Digest = "sha256:" + Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
        Size = bytes.Length,
    };

    private static ReadResourceResult Text(string uri, string text) => new()
    {
        Contents = [new TextResourceContents { Uri = uri, Text = text }],
    };

    private static InMemoryMcpServer CreateServer(Func<string, CancellationToken, ValueTask<ReadResourceResult>> readHandler) =>
        new(builder => builder.WithReadResourceHandler((request, token) => readHandler(request.Params!.Uri, token)));
}
