// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels.UnitTests;

public class HostStateStoreTests
{
    [Fact]
    public async Task InMemory_GetActiveAlias_StableUntilRotatedAsync()
    {
        // Arrange
        var store = new InMemoryHostStateStore();

        // Act
        var first = await store.GetActiveSessionAliasAsync("user:alice", CancellationToken.None);
        var second = await store.GetActiveSessionAliasAsync("user:alice", CancellationToken.None);
        await store.RotateSessionAliasAsync("user:alice", CancellationToken.None);
        var rotated = await store.GetActiveSessionAliasAsync("user:alice", CancellationToken.None);

        // Assert
        Assert.Equal(first, second);
        Assert.NotEqual(first, rotated);
    }

    [Fact]
    public async Task InMemory_CheckpointLocation_IsNullAsync()
    {
        // Arrange
        var store = new InMemoryHostStateStore();

        // Act - the in-memory store does not persist checkpoints
        var location = await store.GetCheckpointLocationAsync("k1", CancellationToken.None);

        // Assert
        Assert.Null(location);
    }

    [Fact]
    public async Task File_Alias_PersistsAcrossInstancesAsync()
    {
        // Arrange
        var root = Path.Combine(Path.GetTempPath(), "afhost-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            string alias1;
            using (var store1 = new FileHostStateStore(new HostStatePathOptions { Root = root }))
            {
                await store1.RotateSessionAliasAsync("user:bob", CancellationToken.None);
                alias1 = await store1.GetActiveSessionAliasAsync("user:bob", CancellationToken.None) ?? string.Empty;
            }

            // Act - a fresh instance over the same directory (after the first released its lock)
            using var store2 = new FileHostStateStore(new HostStatePathOptions { Root = root });
            var alias2 = await store2.GetActiveSessionAliasAsync("user:bob", CancellationToken.None);

            // Assert
            Assert.Equal(alias1, alias2);
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }

    [Fact]
    public void File_SecondInstanceSameRoot_ThrowsWhileLocked()
    {
        // Arrange
        var root = Path.Combine(Path.GetTempPath(), "afhost-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store1 = new FileHostStateStore(new HostStatePathOptions { Root = root });

            // Act / Assert - a second owner of the same directory fails fast
            Assert.Throws<InvalidOperationException>(() => new FileHostStateStore(new HostStatePathOptions { Root = root }));
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }

    [Theory]
    [InlineData("../escape")]
    [InlineData("a/b")]
    [InlineData("a\\b")]
    [InlineData("..")]
    [InlineData("C:evil")]
    public async Task File_CheckpointLocation_RejectsTraversalAsync(string badKey)
    {
        // Arrange
        var root = Path.Combine(Path.GetTempPath(), "afhost-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store = new FileHostStateStore(new HostStatePathOptions { Root = root });

            // Act / Assert
            await Assert.ThrowsAsync<ArgumentException>(async () => await store.GetCheckpointLocationAsync(badKey, CancellationToken.None));
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }

    [Fact]
    public async Task File_CheckpointLocation_AllowsNamespacedKeyAsync()
    {
        // Arrange
        var root = Path.Combine(Path.GetTempPath(), "afhost-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var store = new FileHostStateStore(new HostStatePathOptions { Root = root });

            // Act - a legitimate namespaced key is preserved and yields a directory under the root
            var location = await store.GetCheckpointLocationAsync("telegram:42", CancellationToken.None);

            // Assert
            Assert.NotNull(location);
            Assert.True(Directory.Exists(location));
        }
        finally
        {
            if (Directory.Exists(root)) { Directory.Delete(root, recursive: true); }
        }
    }
}
