// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
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
public sealed class AgentMcpSkillTests
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
        var skill = new AgentMcpSkill(frontmatter, SkillUri, [Resource(SkillUri, SkillContent)], client);

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
        var skill = new AgentMcpSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri,
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
        McpSkillResourceEntry[] resources = includeNestedInstructions
            ? [Resource(SkillRootUri + "nested/SKILL.md", SkillContent)]
            : [];
        var skill = new AgentMcpSkill(frontmatter, SkillUri, resources, client);

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
            return ValueTask.FromResult(Text(uri, SkillContent));
        });
        await using var client = await server.CreateClientAsync();

        // Act
        var skill = CreateSkill(client, root);
        Assert.Empty(reads);
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Equal(SkillContent, content);
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
    public async Task GetContentAsync_EmptyContentMatchingManifest_ThrowsInvalidFrontmatterWithoutCachingAsync()
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, ""));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, content: "");

        // Act
        var first = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        var second = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());

        // Assert
        Assert.Equal($"SKILL.md resource '{SkillUri}' contains invalid frontmatter.", first.Message);
        Assert.Equal(first.Message, second.Message);
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task GetContentAsync_MultipleContentBlocks_ThrowsWithoutCachingAsync(bool firstText, bool secondText)
    {
        // Arrange
        byte[] bytes = Encoding.UTF8.GetBytes(SkillContent);
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(++reads > 1 ? Text(uri, SkillContent) : new ReadResourceResult
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
        var skill = CreateSkill(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Contains("exactly one text or binary content block", exception.Message);
        Assert.Contains(SkillUri, exception.Message);
        Assert.Equal(SkillContent, content);
        Assert.Equal(content, cached);
        Assert.Equal(2, reads);
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
        var skill = new AgentMcpSkill(frontmatter, SkillUri, [Resource(SkillUri, Content)], client);

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
        var content = await Assert.IsType<AgentMcpSkillResource>(resource).ReadAsync();

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
        const string Uri = SkillRootUri + "references/checklist.md";
        byte[] bytes = Encoding.UTF8.GetBytes("Checklist.");
        await using var server = CreateServer((uri, _) =>
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
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)]);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("references/checklist.md"));

        // Assert
        Assert.Contains("exactly one text or binary content block", exception.Message);
        Assert.Contains(Uri, exception.Message);
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

    [Fact]
    public async Task GetContentAsync_TextBlock_DoesNotRequireUriMatchAsync()
    {
        // Arrange
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [new TextResourceContents { Uri = "skill://other/SKILL.md", Text = SkillContent }],
            }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act
        string content = await skill.GetContentAsync();

        // Assert
        Assert.Equal(SkillContent, content);
    }

    [Fact]
    public async Task GetResourceAsync_TextBlock_DoesNotRequireUriMatchAsync()
    {
        // Arrange
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [new TextResourceContents { Uri = "skill://other/checklist.md", Text = "Checklist." }],
            }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources:
        [
            Resource(SkillRootUri + "references/checklist.md", "Checklist."),
        ]);

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
        var content = await resource.ReadAsync();

        // Assert
        Assert.Equal("Checklist.", content);
    }

    [Fact]
    public async Task ReadAsync_EmptyResourceContent_ReturnsNullAsync()
    {
        // Arrange
        var resource = new AgentMcpSkillResource("empty.txt", new TextResourceContents { Uri = SkillRootUri + "empty.txt", Text = "" });

        // Act
        var content = await resource.ReadAsync();

        // Assert
        Assert.Null(content);
    }

    [Fact]
    public async Task GetResourceAsync_TextContent_ReusesVerifiedTextAcrossReadsAsync()
    {
        // Arrange
        const string Uri = SkillRootUri + "references/checklist.md";
        const string Content = "\n\u00e9\U0001f600\n";
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, Content));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, Content)], maxResourceSizeBytes: Encoding.UTF8.GetByteCount(Content));

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
        var first = await resource.ReadAsync();
        var second = await resource.ReadAsync();

        // Assert
        Assert.Equal(Content, Assert.IsType<string>(first));
        Assert.Same(first, second);
        Assert.Equal(1, reads);
    }

    [Fact]
    public async Task GetResourceAsync_BinaryContent_ReusesVerifiedDataAcrossReadsAsync()
    {
        // Arrange
        const string Uri = SkillRootUri + "assets/icon.bin";
        byte[] bytes = [1, 2, 3, 4];
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(new ReadResourceResult
            {
                Contents =
                [
                    BlobResourceContents.FromBytes(bytes, uri, "image/png"),
                ],
            });
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)], maxResourceSizeBytes: bytes.Length);

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        var first = Assert.IsType<DataContent>(await resource.ReadAsync());
        var second = Assert.IsType<DataContent>(await resource.ReadAsync());

        // Assert
        Assert.Equal(bytes, first.Data.ToArray());
        Assert.Equal(first.Data, second.Data);
        Assert.Equal("image/png", first.MediaType);
        Assert.Equal(first.MediaType, second.MediaType);
        Assert.Equal(1, reads);
    }

    [Fact]
    public async Task GetResourceAsync_BinaryContent_PreservesMetadataAsync()
    {
        // Arrange
        const string Uri = SkillRootUri + "assets/icon.bin";
        const string ContentUri = "skill://other/icon.bin";
        byte[] bytes = [1, 2, 3, 4];
        var metadata = new JsonObject { ["source"] = "server" };
        await using var server = CreateServer((_, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents =
            [
                new BlobResourceContents
                {
                    Uri = ContentUri,
                    MimeType = "image/png",
                    Meta = metadata,
                    Blob = Encoding.UTF8.GetBytes(Convert.ToBase64String(bytes)),
                },
            ],
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)]);

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        var content = Assert.IsType<DataContent>(await resource.ReadAsync());

        // Assert
        var binary = Assert.IsType<BlobResourceContents>(content.RawRepresentation);
        Assert.Equal(ContentUri, binary.Uri);
        Assert.Equal("image/png", content.MediaType);
        Assert.True(JsonNode.DeepEquals(metadata, binary.Meta));
        Assert.Equal(bytes, content.Data.ToArray());
    }

    [Fact]
    public async Task GetResourceAsync_EmptyBlob_ReturnsBinaryContentAsync()
    {
        // Arrange
        const string Uri = SkillRootUri + "assets/icon.bin";
        byte[] bytes = [];
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents =
            [
                BlobResourceContents.FromBytes(bytes, uri, "application/octet-stream"),
            ],
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)], maxResourceSizeBytes: 1);

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        var content = Assert.IsType<DataContent>(await resource.ReadAsync());

        // Assert
        Assert.True(content.Data.IsEmpty);
        Assert.Equal("application/octet-stream", content.MediaType);
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
        var skill = new AgentMcpSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri, [instructions], client);

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
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
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

    [Theory]
    [InlineData(-1)]
    [InlineData(0)]
    [InlineData(1)]
    public async Task GetContentAsync_ResourceLimit_EnforcesExactDefaultBoundaryAsync(int excessBytes)
    {
        // Arrange
        string content = SkillContent + new string('x', 1_048_576 - Encoding.UTF8.GetByteCount(SkillContent) + excessBytes);
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, content)));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, content: excessBytes > 0 ? SkillContent : content);

        // Act & Assert
        if (excessBytes <= 0)
        {
            Assert.Equal(content, await skill.GetContentAsync());
        }
        else
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Contains("maximum allowed size (1048576 bytes)", exception.Message);
            Assert.Contains(SkillUri, exception.Message);
        }
    }

    [Theory]
    [InlineData(false, -1)]
    [InlineData(false, 0)]
    [InlineData(false, 1)]
    [InlineData(true, -1)]
    [InlineData(true, 0)]
    [InlineData(true, 1)]
    public async Task GetResourceAsync_ResourceLimit_EnforcesExactDefaultBoundaryAsync(bool binary, int excessBytes)
    {
        // Arrange
        const string Uri = SkillRootUri + "references/checklist.md";
        byte[] bytes = Encoding.UTF8.GetBytes(new string('x', 1_048_576 + excessBytes));
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(binary
                ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(bytes, uri)] }
                : Text(uri, Encoding.UTF8.GetString(bytes))));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, excessBytes > 0 ? new byte[] { 1 } : bytes)]);

        // Act & Assert
        if (excessBytes <= 0)
        {
            var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
            object? content = await resource.ReadAsync();
            Assert.Equal(bytes.Length, binary ? Assert.IsType<DataContent>(content).Data.Length : Assert.IsType<string>(content).Length);
        }
        else
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("references/checklist.md"));
            Assert.Contains("maximum allowed size (1048576 bytes)", exception.Message);
            Assert.Contains(Uri, exception.Message);
        }
    }

    [Theory]
    [InlineData(6, false)]
    [InlineData(7, true)]
    public async Task GetResourceAsync_TextLimit_CountsUtf8BytesAsync(int limit, bool accepted)
    {
        // Arrange
        const string Uri = SkillRootUri + "references/checklist.md";
        const string Content = "\u00e9\n\U0001f600";
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, Content)));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, accepted ? Content : "")], maxResourceSizeBytes: limit);

        // Act & Assert
        if (accepted)
        {
            var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md"));
            Assert.Equal(Content, await resource.ReadAsync());
        }
        else
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("references/checklist.md"));
            Assert.Contains($"maximum allowed size ({limit} bytes)", exception.Message);
        }
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    public async Task GetResourceAsync_BinaryLimit_UsesDecodedSizeAsync(int length)
    {
        // Arrange
        const string Uri = SkillRootUri + "assets/icon.bin";
        byte[] bytes = new byte[length];
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents = [BlobResourceContents.FromBytes(bytes, uri)],
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)], maxResourceSizeBytes: length);

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));

        // Assert
        Assert.Equal(length, Assert.IsType<DataContent>(await resource.ReadAsync()).Data.Length);
    }

    [Theory]
    [InlineData(0, " ")]
    [InlineData(1, " ")]
    [InlineData(2, " ")]
    [InlineData(3, " ")]
    [InlineData(4, " ")]
    [InlineData(191, " ")]
    [InlineData(192, " ")]
    [InlineData(193, " ")]
    [InlineData(4, " \t\r\n")]
    public async Task GetResourceAsync_BinaryLimit_DoesNotRetainEncodedSizeBufferAsync(int length, string whitespace)
    {
        // Arrange
        const string Uri = SkillRootUri + "assets/icon.bin";
        byte[] bytes = new byte[length];
        Array.Fill(bytes, (byte)' ');
        byte[] encoded = Encoding.UTF8.GetBytes(whitespace + string.Join(whitespace, Convert.ToBase64String(bytes).ToCharArray()) + new string(' ', 1024 * 1024));
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents = [new BlobResourceContents { Uri = uri, Blob = encoded }],
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, resources: [Resource(Uri, bytes)], maxResourceSizeBytes: Math.Max(1, bytes.Length));

        // Act
        var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        var content = Assert.IsType<DataContent>(await resource.ReadAsync());

        // Assert
        Assert.Equal(bytes, content.Data.ToArray());
        Assert.True(MemoryMarshal.TryGetArray(content.Data, out ArraySegment<byte> data));
        Assert.Equal(bytes.Length, data.Array!.Length);
        var repeatedContent = Assert.IsType<DataContent>(await resource.ReadAsync());
        Assert.True(MemoryMarshal.TryGetArray(repeatedContent.Data, out ArraySegment<byte> repeatedData));
        Assert.Same(data.Array, repeatedData.Array);
    }

    [Theory]
    [InlineData("%invalid%")]
    [InlineData("=")]
    [InlineData("AAAA====")]
    public async Task GetResourceAsync_InvalidBase64_ThrowsWithoutReturningContentAsync(string encoded)
    {
        // Arrange
        const string Uri = SkillRootUri + "assets/icon.bin";
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents = [new BlobResourceContents { Uri = uri, Blob = Encoding.UTF8.GetBytes(encoded) }],
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("assets/icon.bin"));

        // Assert
        Assert.Contains("invalid base64", exception.Message);
        Assert.Contains(Uri, exception.Message);
    }

    [Fact]
    public async Task GetContentAsync_OversizedResponse_RetriesAndCachesOnlyVerifiedContentAsync()
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(Text(uri, ++reads == 1 ? SkillContent + "x" : SkillContent)));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, maxResourceSizeBytes: Encoding.UTF8.GetByteCount(SkillContent));

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        string content = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Contains("maximum allowed size", exception.Message);
        Assert.Equal(SkillContent, content);
        Assert.Equal(content, cached);
        Assert.Equal(2, reads);
    }

    private static AgentMcpSkill CreateSkill(
        McpClient client,
        string root = SkillRootUri,
        IReadOnlyList<McpSkillResourceEntry>? resources = null,
        string content = SkillContent,
        long maxResourceSizeBytes = AgentMcpSkill.DefaultMaxResourceSizeBytes) =>
        new(new AgentSkillFrontmatter("unit-converter", "Convert units."), root + "SKILL.md",
        [
            Resource(root + "SKILL.md", content),
            .. resources ??
            [
                Resource(root + "references/checklist.md", "Checklist."),
                Resource(root + "assets/icon.bin", new byte[] { 1, 2, 3, 4 }),
                Resource(root + "empty.txt", ""),
            ],
        ], client, maxResourceSizeBytes: maxResourceSizeBytes);

    private static McpSkillResourceEntry Resource(string uri, string text) => Resource(uri, Encoding.UTF8.GetBytes(text));

    [SuppressMessage("Globalization", "CA1308:Normalize strings to uppercase", Justification = "Resource digests require lowercase hexadecimal characters.")]
    private static McpSkillResourceEntry Resource(string uri, byte[] bytes) => new()
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
