// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillTests
{
    [Theory]
    [InlineData(true, 1000L)]
    [InlineData(false, 1000L)]
    [InlineData(true, null)]
    [InlineData(false, null)]
    [InlineData(true, 0L)]
    [InlineData(false, 0L)]
    [InlineData(true, -1L)]
    [InlineData(false, -1L)]
    public async Task ReadResource_ExpiredTtl_RefetchesAgainstOriginalManifestAsync(bool instructions, long? ttl)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            ReadResourceResult result = Text(uri, uri == SkillUri ? SkillContent : "Checklist.");
            result.TimeToLive = ttl is null ? null : TimeSpan.FromMilliseconds(ttl.Value);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);
        await ReadSnapshotAsync(skill, instructions);

        if (ttl > 0)
        {
            // Act
            clock.Advance(TimeSpan.FromMilliseconds(ttl.Value - 1));
            await ReadSnapshotAsync(skill, instructions);

            // Assert
            Assert.Equal(1, reads);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        // Act
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(2, reads);

        // Act
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(ttl > 0 ? 2 : 3, reads);
    }

    [Fact]
    public async Task GetResourceAsync_ExpiredBinaryContent_RefetchesAndPreservesReturnedResourceAsync()
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        byte[] bytes = [1, 2, 3, 4];
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [BlobResourceContents.FromBytes(bytes, uri, "image/png")],
                TimeToLive = TimeSpan.FromSeconds(1),
            });
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);
        var first = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        var data = Assert.IsType<DataContent>(await first.ReadAsync());

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        var second = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        var repeated = Assert.IsType<DataContent>(await second.ReadAsync());

        // Assert
        Assert.Equal(bytes, repeated.Data.ToArray());
        Assert.NotSame(data.RawRepresentation, repeated.RawRepresentation);
        Assert.Equal("image/png", repeated.MediaType);
        var retained = Assert.IsType<DataContent>(await first.ReadAsync());
        Assert.Same(data.RawRepresentation, retained.RawRepresentation);
        Assert.Equal(data.Data, retained.Data);
        Assert.Equal(2, reads);
    }

    [Fact]
    public async Task ReadResource_SeparateTtls_RefetchesOnlyExpiredResourceAsync()
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int instructionReads = 0;
        int supportingReads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            if (uri == SkillUri)
            {
                instructionReads++;
            }
            else
            {
                supportingReads++;
            }

            ReadResourceResult result = Text(uri, uri == SkillUri ? SkillContent : "Checklist.");
            result.TimeToLive = TimeSpan.FromMilliseconds(uri == SkillUri ? 1000 : 3000);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);
        await ReadSnapshotAsync(skill, instructions: true);
        await ReadSnapshotAsync(skill, instructions: false);

        // Act
        clock.Advance(TimeSpan.FromSeconds(1));
        await ReadSnapshotAsync(skill, instructions: false);
        await ReadSnapshotAsync(skill, instructions: true);

        // Assert
        Assert.Equal(2, instructionReads);
        Assert.Equal(1, supportingReads);
    }

    [Fact]
    public async Task ReadResource_SlowRequest_DoesNotConsumeTtlAsync()
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            clock.Advance(TimeSpan.FromSeconds(2));
            ReadResourceResult result = Text(uri, SkillContent);
            result.TimeToLive = TimeSpan.FromSeconds(1);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);

        // Act
        await ReadSnapshotAsync(skill, instructions: true);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        await ReadSnapshotAsync(skill, instructions: true);

        // Assert
        Assert.Equal(1, reads);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await ReadSnapshotAsync(skill, instructions: true);

        // Assert
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(500)]
    [InlineData(1000)]
    [InlineData(1500)]
    public async Task GetContentAsync_ValidationTime_ConsumesResourceTtlAsync(int validationMilliseconds)
    {
        // Arrange
        const string Content = "---\nname: unit-converter\ndescription: Convert units.\nmetadata:\n  key: first\n  key: second\n---\nInstructions.";
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            ReadResourceResult result = Text(uri, Content);
            result.TimeToLive = TimeSpan.FromSeconds(1);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        // Duplicate metadata logs a warning during otherwise successful frontmatter validation.
        logger.Setup(l => l.Log(
            LogLevel.Warning,
            It.IsAny<EventId>(),
            It.IsAny<It.IsAnyType>(),
            It.IsAny<Exception?>(),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()))
            .Callback(() => clock.Advance(TimeSpan.FromMilliseconds(validationMilliseconds)));
        var skill = new AgentMcpSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri,
            [Resource(SkillUri, Content)], client, CreateLoader(clock), logger.Object, timeProvider: clock);

        // Act
        Assert.Equal(Content, await skill.GetContentAsync());

        // Assert
        Assert.Equal(1, reads);
        if (validationMilliseconds < 1000)
        {
            // Act
            clock.Advance(TimeSpan.FromMilliseconds(999 - validationMilliseconds));
            Assert.Equal(Content, await skill.GetContentAsync());

            // Assert
            Assert.Equal(1, reads);
            clock.Advance(TimeSpan.FromMilliseconds(1));
        }

        // Act
        Assert.Equal(Content, await skill.GetContentAsync());

        // Assert
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_CanceledDuringFrontmatterValidation_DoesNotCacheContentAsync(bool cached)
    {
        // Arrange
        const string Content = "---\nname: unit-converter\ndescription: Convert units.\nmetadata:\n  key: first\n  key: second\n---\nInstructions.";
        var clock = new ResourceTimeProvider();
        using var cts = new CancellationTokenSource();
        int reads = 0;
        var client = CreateResourceClient((uri, _) =>
        {
            reads++;
            return Task.FromResult(ResourceResponse(uri, Content));
        });
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        bool cancelDuringValidation = !cached;
        // Duplicate metadata logs a warning while the otherwise valid SKILL.md is being parsed.
        logger.Setup(l => l.Log(
            LogLevel.Warning,
            It.IsAny<EventId>(),
            It.IsAny<It.IsAnyType>(),
            It.IsAny<Exception?>(),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()))
            .Callback(() =>
            {
                if (cancelDuringValidation)
                {
                    cts.Cancel();
                }
            });
        using var loader = CreateLoader(clock);
        var skill = new AgentMcpSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri,
            [Resource(SkillUri, Content)], client.Object, loader, logger.Object, timeProvider: clock);
        if (cached)
        {
            Assert.Equal(Content, await skill.GetContentAsync());
            clock.Advance(TimeSpan.FromSeconds(1));
            cancelDuringValidation = true;
        }

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await skill.GetContentAsync(cts.Token));
        Assert.Equal(cached ? 2 : 1, reads);

        // Act
        cancelDuringValidation = false;
        Assert.Equal(Content, await skill.GetContentAsync());
        Assert.Equal(Content, await skill.GetContentAsync());

        // Assert
        Assert.Equal(cached ? 3 : 2, reads);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(false, false)]
    [InlineData(true, true)]
    [InlineData(false, true)]
    public async Task ReadResource_ConcurrentLookups_ShareFreshFetchAsync(bool instructions, bool expired)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        var release = new TaskCompletionSource<ReadResourceResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        int reads = 0;
        await using var server = CreateServer((uri, token) =>
        {
            int read = Interlocked.Increment(ref reads);
            return expired && read == 1
                ? ValueTask.FromResult(Text(uri, uri == SkillUri ? SkillContent : "Checklist."))
                : new ValueTask<ReadResourceResult>(release.Task.WaitAsync(token));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);
        if (expired)
        {
            await ReadSnapshotAsync(skill, instructions);
            clock.Advance(TimeSpan.FromMinutes(1));
        }

        // Act
        Task[] pending = Enumerable.Range(0, 8).Select(_ => ReadSnapshotAsync(skill, instructions)).ToArray();
        release.SetResult(Text(instructions ? SkillUri : SkillRootUri + "references/checklist.md", instructions ? SkillContent : "Checklist."));
        await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(expired ? 2 : 1, reads);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ReadResource_CanceledExpiredLookup_DoesNotFetchAsync(bool instructions)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, uri == SkillUri ? SkillContent : "Checklist."));
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromMinutes(1));
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ReadSnapshotAsync(skill, instructions, cts.Token));
        Assert.Equal(1, reads);
        await ReadSnapshotAsync(skill, instructions);
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(true, false, 1000L)]
    [InlineData(false, false, 1000L)]
    [InlineData(true, true, 1000L)]
    [InlineData(false, true, 1000L)]
    [InlineData(true, false, null)]
    [InlineData(false, false, null)]
    [InlineData(true, true, null)]
    [InlineData(false, true, null)]
    [InlineData(true, false, 0L)]
    [InlineData(false, false, 0L)]
    [InlineData(true, true, 0L)]
    [InlineData(false, true, 0L)]
    [InlineData(true, false, -1L)]
    [InlineData(false, false, -1L)]
    [InlineData(true, true, -1L)]
    [InlineData(false, true, -1L)]
    public async Task ReadResource_ExpiredTtl_ReturnsCachedContentOnMismatchAndRetriesAsync(bool instructions, bool sizeMismatch, long? ttl)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        string original = instructions ? SkillContent : "Checklist.";
        string changed = sizeMismatch ? original + "Changed." : original.Replace('I', 'i').Replace('C', 'c');
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            ReadResourceResult result = Text(uri, ++reads is 2 or 3 ? changed : original);
            result.TimeToLive = reads == 1
                ? ttl is { } milliseconds ? TimeSpan.FromMilliseconds(milliseconds) : null
                : TimeSpan.FromMinutes(reads is 2 or 3 ? 10 : 1);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        var skill = new AgentMcpSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri,
            [Resource(SkillUri, SkillContent), Resource(SkillRootUri + "references/checklist.md", "Checklist.")],
            client, CreateLoader(clock), logger.Object, timeProvider: clock);
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromMilliseconds(Math.Max(ttl.GetValueOrDefault(), 0)));

        // Act
        await ReadSnapshotAsync(skill, instructions);
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(3, reads);
        logger.Verify(
            l => l.Log(
                LogLevel.Warning,
                It.IsAny<EventId>(),
                It.Is<It.IsAnyType>((state, _) => state.ToString()!.Contains(instructions ? SkillUri : SkillRootUri + "references/checklist.md")
                    && state.ToString()!.Contains(sizeMismatch ? "byte size" : "SHA-256 digest")),
                It.IsAny<Exception?>(),
                It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
            Times.Exactly(2));

        // Act
        await ReadSnapshotAsync(skill, instructions);
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(4, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetResourceAsync_ExpiredBinaryContent_ReturnsCachedBytesAndPreservesReturnedResourceAsync(bool sizeMismatch)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        byte[] bytes = [1, 2, 3, 4];
        byte[] changed = sizeMismatch ? [1, 2, 3, 4, 5] : [4, 3, 2, 1];
        int reads = 0;
        await using var server = CreateServer((uri, _) => ValueTask.FromResult(new ReadResourceResult
        {
            Contents = [BlobResourceContents.FromBytes(++reads == 2 ? changed : bytes, uri)],
            TimeToLive = TimeSpan.FromSeconds(1),
        }));
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);
        var retained = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        clock.Advance(TimeSpan.FromSeconds(1));

        // Act
        var fallback = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));

        // Assert
        Assert.Equal(bytes, Assert.IsType<DataContent>(await fallback.ReadAsync()).Data.ToArray());
        Assert.Equal(bytes, Assert.IsType<DataContent>(await retained.ReadAsync()).Data.ToArray());
        Assert.Equal(2, reads);
        var retried = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("assets/icon.bin"));
        Assert.Equal(bytes, Assert.IsType<DataContent>(await retried.ReadAsync()).Data.ToArray());
        Assert.Equal(3, reads);
    }

    [Fact]
    public async Task GetResourceAsync_SameUriInDifferentSkillInstances_KeepsSeparateSnapshotsAsync()
    {
        // Arrange
        const string ResourceUri = SkillRootUri + "references/checklist.md";
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
            ValueTask.FromResult(Text(uri, ++reads == 1 ? "Checklist." : "Updated checklist.")));
        await using var client = await server.CreateClientAsync();
        var original = CreateSkill(client);
        var replacement = CreateSkill(client, resources: [Resource(ResourceUri, "Updated checklist.")]);

        // Act
        var first = Assert.IsType<AgentMcpSkillResource>(await original.GetResourceAsync("references/checklist.md"));
        var updated = Assert.IsType<AgentMcpSkillResource>(await replacement.GetResourceAsync("references/checklist.md"));
        var retained = Assert.IsType<AgentMcpSkillResource>(await original.GetResourceAsync("references/checklist.md"));

        // Assert
        Assert.Equal("Checklist.", await first.ReadAsync());
        Assert.Equal("Updated checklist.", await updated.ReadAsync());
        Assert.Equal("Checklist.", await retained.ReadAsync());
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ReadResource_UnchangedContent_UsesNewTtlWithoutExtendingItOnHitsAsync(bool instructions)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        int reads = 0;
        await using var server = CreateServer((uri, _) =>
        {
            ReadResourceResult result = Text(uri, uri == SkillUri ? SkillContent : "Checklist.");
            result.TimeToLive = TimeSpan.FromSeconds(++reads == 1 ? 1 : 2);
            return ValueTask.FromResult(result);
        });
        await using var client = await server.CreateClientAsync();
        var skill = CreateSkill(client, timeProvider: clock);

        // Act
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(1, reads);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromSeconds(1));
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromMilliseconds(999));
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(2, reads);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(3, reads);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ReadResource_CanceledDuringMismatch_DoesNotReturnOrReplaceCachedContentAsync(bool cached, bool instructions)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        using var cts = new CancellationTokenSource();
        bool mismatch = !cached;
        int reads = 0;
        string original = instructions ? SkillContent : "Checklist.";
        var client = CreateResourceClient((uri, _) =>
        {
            reads++;
            return Task.FromResult(ResourceResponse(uri, mismatch ? original + "Changed." : original));
        });
        var logger = new Mock<ILogger>();
        logger.Setup(l => l.IsEnabled(It.IsAny<LogLevel>())).Returns(true);
        logger.Setup(l => l.Log(
            LogLevel.Warning,
            It.IsAny<EventId>(),
            It.IsAny<It.IsAnyType>(),
            It.IsAny<Exception?>(),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()))
            .Callback(cts.Cancel);
        using var loader = CreateLoader(clock);
        var skill = new AgentMcpSkill(new AgentSkillFrontmatter("unit-converter", "Convert units."), SkillUri,
            [Resource(SkillUri, SkillContent), Resource(SkillRootUri + "references/checklist.md", "Checklist.")],
            client.Object, loader, logger.Object, timeProvider: clock);
        if (cached)
        {
            await ReadSnapshotAsync(skill, instructions);
            clock.Advance(TimeSpan.FromSeconds(1));
            mismatch = true;
        }

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ReadSnapshotAsync(skill, instructions, cts.Token));

        // Act
        mismatch = false;
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(cached ? 3 : 2, reads);
    }

    /// <summary>
    /// Reads <c>SKILL.md</c> or a supporting resource and checks that its content still matches the test's initial version.
    /// </summary>
    private static async Task ReadSnapshotAsync(AgentMcpSkill skill, bool instructions, CancellationToken cancellationToken = default)
    {
        if (instructions)
        {
            Assert.Equal(SkillContent, await skill.GetContentAsync(cancellationToken));
        }
        else
        {
            var resource = Assert.IsType<AgentMcpSkillResource>(await skill.GetResourceAsync("references/checklist.md", cancellationToken));
            Assert.Equal("Checklist.", await resource.ReadAsync(cancellationToken: cancellationToken));
        }
    }

    /// <summary>
    /// Provides a clock that tests can advance without waiting.
    /// </summary>
    private sealed class ResourceTimeProvider : TimeProvider
    {
        private long _timestamp;

        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public override long GetTimestamp() => Interlocked.Read(ref this._timestamp);

        public void Advance(TimeSpan duration) => Interlocked.Add(ref this._timestamp, duration.Ticks);
    }
}
