// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using Moq;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ReadResource_CacheMiss_ForwardsUriAndCancellationTokenAsync(bool instructions)
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        int reads = 0;
        var client = CreateResourceClient((uri, token) =>
        {
            Assert.Equal(instructions ? SkillUri : SkillRootUri + "references/checklist.md", uri);
            Assert.Equal(cts.Token, token);
            reads++;
            return Task.FromResult(ResourceResponse(uri, instructions ? SkillContent : "Checklist."));
        });
        var skill = CreateSkill(client.Object);

        // Act
        await ReadSnapshotAsync(skill, instructions, cts.Token);
        await ReadSnapshotAsync(skill, instructions, cts.Token);

        // Assert
        Assert.Equal(1, reads);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ReadResource_FailedRead_PropagatesAndReleasesWaiterAsync(bool cached, bool canceled)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        var error = new InvalidOperationException("Resource read failed.");
        int reads = 0;
        var client = CreateResourceClient((uri, token) =>
            Interlocked.Increment(ref reads) == (cached ? 2 : 1)
                ? release.Task.WaitAsync(token)
                : Task.FromResult(ResourceResponse(uri, SkillContent)));
        var skill = CreateSkill(client.Object, timeProvider: clock);
        if (cached)
        {
            await ReadSnapshotAsync(skill, instructions: true);
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        using var cts = new CancellationTokenSource();
        var active = ReadSnapshotAsync(skill, instructions: true, cts.Token);
        var waiting = ReadSnapshotAsync(skill, instructions: true);

        // Act & Assert
        if (canceled)
        {
            await cts.CancelAsync();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => active.WaitAsync(TimeSpan.FromSeconds(10)));
        }
        else
        {
            release.SetException(error);
            Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(() => active.WaitAsync(TimeSpan.FromSeconds(10))));
        }

        await waiting.WaitAsync(TimeSpan.FromSeconds(10));
        await ReadSnapshotAsync(skill, instructions: true);
        Assert.Equal(cached ? 3 : 2, reads);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ReadResource_CanceledResponse_DoesNotCacheContentAsync(bool cached, bool instructions)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        using var cts = new CancellationTokenSource();
        int reads = 0;
        var client = CreateResourceClient((uri, token) =>
        {
            if (++reads == (cached ? 2 : 1))
            {
                Assert.Equal(cts.Token, token);
                cts.Cancel();
            }

            return Task.FromResult(ResourceResponse(uri, instructions ? SkillContent : "Checklist."));
        });
        var skill = CreateSkill(client.Object, timeProvider: clock);
        if (cached)
        {
            await ReadSnapshotAsync(skill, instructions);
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ReadSnapshotAsync(skill, instructions, cts.Token));

        // Act
        await ReadSnapshotAsync(skill, instructions);
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(cached ? 3 : 2, reads);
    }

    [Theory]
    [InlineData(true, false)]
    [InlineData(true, true)]
    [InlineData(false, false)]
    [InlineData(false, true)]
    public async Task ReadResource_ConcurrentMismatches_ReturnCachedContentWithoutRenewingTtlAsync(bool instructions, bool sizeMismatch)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        string original = instructions ? SkillContent : "Checklist.";
        string changed = sizeMismatch ? original + "Changed." : original.Replace('I', 'i').Replace('C', 'c');
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        bool mismatching = false;
        int reads = 0;
        var client = CreateResourceClient(async (uri, token) =>
        {
            if (Interlocked.Increment(ref reads) == 2)
            {
                await release.Task.WaitAsync(token);
            }

            return ResourceResponse(uri, mismatching ? changed : original, reads == 1 ? 1000 : 2000);
        });
        var skill = CreateSkill(client.Object, timeProvider: clock);
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromSeconds(1));
        mismatching = true;

        // Act
        Task[] pending = Enumerable.Range(0, 8).Select(_ => ReadSnapshotAsync(skill, instructions)).ToArray();
        release.SetResult();
        await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(9, reads);

        // Act
        mismatching = false;
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromMilliseconds(1999));
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(10, reads);

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(1));
        await ReadSnapshotAsync(skill, instructions);

        // Assert
        Assert.Equal(11, reads);
    }

    [Theory]
    [InlineData(true, null, 8)]
    [InlineData(false, null, 8)]
    [InlineData(true, 0L, 8)]
    [InlineData(false, 0L, 8)]
    [InlineData(true, -1L, 8)]
    [InlineData(false, -1L, 8)]
    [InlineData(true, 1000L, 1)]
    [InlineData(false, 1000L, 1)]
    public async Task ReadResource_ConcurrentRefetches_ReuseOnlyFreshResultsAsync(bool instructions, long? ttl, int expectedReads)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int reads = 0;
        var client = CreateResourceClient(async (uri, token) =>
        {
            int read = Interlocked.Increment(ref reads);
            if (read == 2)
            {
                await release.Task.WaitAsync(token);
            }

            return ResourceResponse(uri, instructions ? SkillContent : "Checklist.", read == 1 ? 1000 : ttl);
        });
        var skill = CreateSkill(client.Object, timeProvider: clock);
        await ReadSnapshotAsync(skill, instructions);
        clock.Advance(TimeSpan.FromSeconds(1));

        // Act
        Task[] pending = Enumerable.Range(0, 8).Select(_ => ReadSnapshotAsync(skill, instructions)).ToArray();
        release.SetResult();
        await Task.WhenAll(pending).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(expectedReads + 1, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ReadResource_OtherSkillHasContent_DoesNotUseItOnMismatchAsync(bool sizeMismatch)
    {
        // Arrange
        int reads = 0;
        string changed = sizeMismatch ? SkillContent + "Changed." : SkillContent.Replace('I', 'i');
        var client = CreateResourceClient((uri, _) =>
            Task.FromResult(ResourceResponse(uri, ++reads == 1 ? SkillContent : changed)));
        var original = CreateSkill(client.Object);
        var replacement = CreateSkill(client.Object);
        await ReadSnapshotAsync(original, instructions: true);

        // Act
        var error = await Assert.ThrowsAsync<InvalidOperationException>(async () => await replacement.GetContentAsync());

        // Assert
        Assert.Contains(sizeMismatch ? "byte size" : "SHA-256 digest", error.Message);
        await ReadSnapshotAsync(original, instructions: true);
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ReadResource_IndependentReads_DoNotShareReadGatesAsync(bool differentSkill)
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int reads = 0;
        var client = CreateResourceClient((uri, token) =>
            Interlocked.Increment(ref reads) == 1
                ? release.Task.WaitAsync(token)
                : Task.FromResult(ResourceResponse(uri, uri == SkillUri ? SkillContent : "Checklist.")));
        var original = CreateSkill(client.Object);
        var other = differentSkill ? CreateSkill(client.Object) : original;
        var active = ReadSnapshotAsync(original, instructions: true);

        // Act
        await ReadSnapshotAsync(other, instructions: differentSkill).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.False(active.IsCompleted);

        // Act
        release.SetResult(ResourceResponse(SkillUri, SkillContent));
        await active.WaitAsync(TimeSpan.FromSeconds(10));
        await ReadSnapshotAsync(original, instructions: true);
        await ReadSnapshotAsync(other, instructions: differentSkill);

        // Assert
        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ReadResource_CanceledWaiter_DoesNotCancelActiveReadAsync(bool cached)
    {
        // Arrange
        var clock = new ResourceTimeProvider();
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int reads = 0;
        var client = CreateResourceClient((uri, token) =>
            Interlocked.Increment(ref reads) == (cached ? 2 : 1)
                ? release.Task.WaitAsync(token)
                : Task.FromResult(ResourceResponse(uri, SkillContent)));
        var skill = CreateSkill(client.Object, timeProvider: clock);
        if (cached)
        {
            await ReadSnapshotAsync(skill, instructions: true);
            clock.Advance(TimeSpan.FromSeconds(1));
        }

        using var cts = new CancellationTokenSource();
        var active = ReadSnapshotAsync(skill, instructions: true);
        var waiting = ReadSnapshotAsync(skill, instructions: true, cts.Token);

        // Act
        await cts.CancelAsync();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => waiting.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.False(active.IsCompleted);

        // Act
        release.SetResult(ResourceResponse(SkillUri, SkillContent));
        await active.WaitAsync(TimeSpan.FromSeconds(10));
        await ReadSnapshotAsync(skill, instructions: true);

        // Assert
        Assert.Equal(cached ? 2 : 1, reads);
    }

    [Theory]
    [InlineData(true, true, true)]
    [InlineData(true, true, false)]
    [InlineData(true, false, true)]
    [InlineData(true, false, false)]
    [InlineData(false, true, true)]
    [InlineData(false, true, false)]
    [InlineData(false, false, true)]
    [InlineData(false, false, false)]
    public async Task ReadResource_CanceledWaiters_PreserveReadOrderAsync(bool instructions, bool cancelBeforeNextRead, bool fresh)
    {
        // Arrange
        var release = new TaskCompletionSource<JsonObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        int reads = 0;
        string uri = instructions ? SkillUri : SkillRootUri + "references/checklist.md";
        string content = instructions ? SkillContent : "Checklist.";
        var client = CreateResourceClient((requestedUri, token) =>
        {
            Assert.Equal(uri, requestedUri);
            if (Interlocked.Increment(ref reads) == 1)
            {
                return release.Task.WaitAsync(token);
            }

            Assert.True(release.Task.IsCompleted);
            return Task.FromResult(ResourceResponse(uri, content, fresh ? 1000 : 0));
        });
        var skill = CreateSkill(client.Object);
        using var cts = new CancellationTokenSource();
        Task active = ReadSnapshotAsync(skill, instructions);
        Task[] canceled = Enumerable.Range(0, 3)
            .Select(_ => ReadSnapshotAsync(skill, instructions, cts.Token)).ToArray();

        // Act
        if (cancelBeforeNextRead)
        {
            await cts.CancelAsync();
        }

        Task next = ReadSnapshotAsync(skill, instructions);
        if (!cancelBeforeNextRead)
        {
            await cts.CancelAsync();
        }

        // Assert
        foreach (Task waiting in canceled)
        {
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => waiting.WaitAsync(TimeSpan.FromSeconds(10)));
        }

        Assert.False(active.IsCompleted);
        Assert.False(next.IsCompleted);
        Assert.Equal(1, reads);

        // Act
        release.SetResult(ResourceResponse(uri, content, fresh ? 1000 : 0));
        await Task.WhenAll(active, next).WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.Equal(fresh ? 1 : 2, reads);
    }

    /// <summary>
    /// Creates a client that forwards resource reads to the test handler and rejects other requests.
    /// </summary>
    private static Mock<McpClient> CreateResourceClient(Func<string, CancellationToken, Task<JsonObject>> handler)
    {
        var client = new Mock<McpClient>();
        client.Setup(c => c.SendRequestAsync(It.IsAny<JsonRpcRequest>(), It.IsAny<CancellationToken>()))
            .Returns((JsonRpcRequest request, CancellationToken token) => RespondAsync(request, token));
        return client;

        async Task<JsonRpcResponse> RespondAsync(JsonRpcRequest request, CancellationToken token)
        {
            Assert.Equal("resources/read", request.Method);
            return new() { Id = request.Id, Result = await handler(request.Params!["uri"]!.GetValue<string>(), token) };
        }
    }

    /// <summary>
    /// Creates a text resource response with an optional TTL.
    /// </summary>
    private static JsonObject ResourceResponse(string uri, string text, long? ttl = 1000)
    {
        JsonObject result = new()
        {
            ["contents"] = new JsonArray(new JsonObject { ["uri"] = uri, ["text"] = text }),
        };
        if (ttl is not null)
        {
            result["ttlMs"] = ttl.Value;
        }

        return result;
    }
}
