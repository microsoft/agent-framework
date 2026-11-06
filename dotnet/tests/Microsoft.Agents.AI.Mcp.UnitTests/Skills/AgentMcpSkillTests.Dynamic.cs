// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillTests
{
    [Fact]
    public async Task DynamicSkill_ReadsOnlyRequestedInstructionsAndResourcesAsync()
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreateServer((uri, _) =>
        {
            reads.Add(uri);
            return ValueTask.FromResult(uri.EndsWith(".bin", StringComparison.Ordinal)
                ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(new byte[] { 1, 2, 3 }, uri, "application/octet-stream")] }
                : Text(uri, uri == SkillUri ? SkillContent : "Read references/next.md."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client);
        Assert.Empty(reads);

        // Act
        string instructions = await skill.GetContentAsync();
        Assert.Equal([SkillUri], reads);
        var resource = await skill.GetResourceAsync("references\\guide.md");
        var binary = await skill.GetResourceAsync("assets/icon.bin");

        // Assert
        Assert.Equal(SkillContent, instructions);
        Assert.NotNull(resource);
        Assert.NotNull(binary);
        Assert.Equal("Read references/next.md.", await resource.ReadAsync());
        Assert.Equal(new byte[] { 1, 2, 3 }, Assert.IsType<DataContent>(await binary.ReadAsync()).Data.ToArray());
        Assert.Equal([SkillUri, SkillRootUri + "references/guide.md", SkillRootUri + "assets/icon.bin"], reads);
        Assert.False(skill.NeedsRefresh);
    }

    [Theory]
    [InlineData("../escape.md")]
    [InlineData("%252e%252e/escape.md")]
    [InlineData("references\\..\\..\\escape.md")]
    [InlineData("/etc/passwd")]
    [InlineData("https://example.com/escape.md")]
    [InlineData("references/guide.md?value=%00")]
    [InlineData("SKILL.md")]
    public async Task DynamicSkill_UnsafeOrInstructionResourceName_DoesNotReadAsync(string name)
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client);

        // Act
        var resource = await skill.GetResourceAsync(name);

        // Assert
        Assert.Null(resource);
        Assert.Equal(0, reads);
    }

    [Theory]
    [InlineData(true, 1000L)]
    [InlineData(false, 1000L)]
    [InlineData(true, null)]
    [InlineData(false, 0L)]
    [InlineData(false, -1L)]
    public async Task DynamicSkill_ExpiredContent_AcceptsChangesWithoutManifestRefreshAsync(bool instructions, long? ttl)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            string content = instructions ? SkillContent : "Original resource.";
            ReadResourceResult result = Text(uri, ++reads == 1 ? content : content + "\nChanged.");
            result.TimeToLive = ttl is null ? null : TimeSpan.FromMilliseconds(ttl.Value);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client, timeProvider: clock);

        // Act
        string original = instructions
            ? await skill.GetContentAsync()
            : Assert.IsType<string>(await (await skill.GetResourceAsync("references/guide.md"))!.ReadAsync());
        if (ttl > 0)
        {
            clock.Advance(TimeSpan.FromMilliseconds(ttl.Value - 1));
            if (instructions)
            {
                Assert.Equal(original, await skill.GetContentAsync());
            }
            else
            {
                Assert.Equal(original, await (await skill.GetResourceAsync("references/guide.md"))!.ReadAsync());
            }

            Assert.Equal(1, reads);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        string changed = instructions
            ? await skill.GetContentAsync()
            : Assert.IsType<string>(await (await skill.GetResourceAsync("references/guide.md"))!.ReadAsync());

        // Assert
        Assert.Equal(original + "\nChanged.", changed);
        Assert.Equal(2, reads);
        Assert.False(skill.NeedsRefresh);
    }

    [Theory]
    [InlineData("Instructions without frontmatter.")]
    [InlineData("---\nname: unit-converter\ndescription: Changed.\n---\nInstructions.")]
    [InlineData("---\nname: unit-converter\ndescription: Convert units.\nfuture-field: changed\n---\nInstructions.")]
    public async Task DynamicSkill_InvalidFrontmatter_IsRejectedAndNotCachedAsync(string content)
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(Text(uri, ++reads == 1 ? content : SkillContent)));
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        Assert.Equal(SkillContent, await skill.GetContentAsync());
        Assert.Equal(SkillContent, await skill.GetContentAsync());
        Assert.Equal(2, reads);
        Assert.False(skill.NeedsRefresh);
    }

    [Theory]
    [InlineData("text")]
    [InlineData("utf8")]
    [InlineData("binary")]
    public async Task DynamicSkill_ResourceSizeLimit_UsesByteCountAsync(string kind)
    {
        // Arrange
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(kind == "binary"
            ? new ReadResourceResult { Contents = [BlobResourceContents.FromBytes(new byte[5], uri)] }
            : Text(uri, kind == "utf8" ? "\u00e9\u00e9\u00e9" : "12345")));
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client, maxResourceSizeBytes: 4);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetResourceAsync("file"));

        // Assert
        Assert.Contains("maximum allowed size (4 bytes)", exception.Message);
        Assert.False(skill.NeedsRefresh);
    }

    [Theory]
    [InlineData("empty")]
    [InlineData("multiple")]
    [InlineData("binary-instructions")]
    public async Task DynamicSkill_InvalidResourceResponse_IsRejectedAsync(string kind)
    {
        // Arrange
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents = kind switch
            {
                "empty" => [],
                "multiple" => [new TextResourceContents { Uri = uri, Text = SkillContent }, new TextResourceContents { Uri = uri, Text = SkillContent }],
                _ => [BlobResourceContents.FromBytes(new byte[] { 1 }, uri)],
            },
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
        Assert.False(skill.NeedsRefresh);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DynamicSkill_PrivateResource_RequiresCacheIsolationAsync(bool hasIsolationKey)
    {
        // Arrange
        await using var server = CreateServer((uri, _) =>
        {
            ReadResourceResult result = Text(uri, SkillContent);
            result.CacheScope = CacheScope.Private;
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client, hasIsolationKey: hasIsolationKey);

        // Act & Assert
        if (hasIsolationKey)
        {
            Assert.Equal(SkillContent, await skill.GetContentAsync());
        }
        else
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Contains("private cacheScope", exception.Message);
        }
    }

    [Theory]
    [InlineData(McpErrorCode.ResourceNotFound)]
    [InlineData(McpErrorCode.InternalError)]
    public async Task DynamicSkill_ReadFailure_PropagatesWithoutCachingAsync(McpErrorCode errorCode)
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            if (++reads == 1)
            {
                throw new McpProtocolException("Read failed.", errorCode);
            }

            return ValueTask.FromResult(Text(uri, "Available now."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<McpProtocolException>(async () => await skill.GetResourceAsync("references/guide.md"));
        Assert.Equal(errorCode, exception.ErrorCode);
        Assert.Equal("Available now.", await (await skill.GetResourceAsync("references/guide.md"))!.ReadAsync());
        Assert.Equal(2, reads);
        Assert.False(skill.NeedsRefresh);
    }

    [Fact]
    public async Task DynamicSkill_ExpiredReadFailure_DoesNotReturnStaleContentAsync()
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            if (++reads == 2)
            {
                throw new McpProtocolException("Read failed.", McpErrorCode.InternalError);
            }

            ReadResourceResult result = Text(uri, reads == 1 ? "Original." : "Updated.");
            result.TimeToLive = TimeSpan.FromSeconds(1);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client, timeProvider: clock);
        var original = await skill.GetResourceAsync("references/guide.md");
        Assert.NotNull(original);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        await Assert.ThrowsAsync<McpProtocolException>(async () => await skill.GetResourceAsync("references/guide.md"));
        var updated = await skill.GetResourceAsync("references/guide.md");

        // Assert
        Assert.NotNull(updated);
        Assert.Equal("Updated.", await updated.ReadAsync());
        Assert.Equal("Original.", await original.ReadAsync());
        Assert.Equal(3, reads);
        Assert.False(skill.NeedsRefresh);
    }

    [Fact]
    public async Task DynamicSkill_CanceledRead_DoesNotFetchAsync()
    {
        // Arrange
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, "Must not be read."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateDynamicSkill(client);
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await skill.GetResourceAsync("references/guide.md", cts.Token));
        Assert.Equal(0, reads);
    }

    private static AgentMcpSkill CreateDynamicSkill(
        McpClient client,
        long maxResourceSizeBytes = AgentMcpSkill.DefaultMaxResourceSizeBytes,
        TimeProvider? timeProvider = null,
        bool hasIsolationKey = false) =>
        new(CreateFrontmatter(), CreateAdvertisedFrontmatter(), SkillUri, new McpSkillDynamicResources(), client,
            maxResourceSizeBytes: maxResourceSizeBytes, timeProvider: timeProvider, hasIsolationKey: hasIsolationKey);
}
