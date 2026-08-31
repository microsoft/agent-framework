// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for <see cref="CheckpointManager.GetLatestCheckpointAsync"/>, which must return the most recently
/// committed checkpoint for a session regardless of the backing store implementation.
/// </summary>
public class CheckpointManagerLatestTests
{
    [Fact]
    public async Task GetLatestCheckpointAsync_FileStore_ReturnsLastCommittedAsync()
    {
        // Arrange: commit a chain of checkpoints to a durable file store in a known order.
        using TempDirectory dir = new();
        using FileSystemJsonCheckpointStore store = new(dir);
        CheckpointManager manager = CheckpointManager.CreateJson(store);

        const string SessionId = "session-latest";
        List<CheckpointInfo> committed = [];
        CheckpointInfo? parent = null;
        for (int i = 0; i < 8; i++)
        {
            JsonElement value = JsonSerializer.SerializeToElement($"checkpoint-{i}");
            CheckpointInfo info = await store.CreateCheckpointAsync(SessionId, value, parent);
            committed.Add(info);
            parent = info;
        }

        // Act
        IEnumerable<CheckpointInfo> index = await store.RetrieveIndexAsync(SessionId);
        CheckpointInfo? latest = await manager.GetLatestCheckpointAsync(SessionId);

        // Assert: the durable index preserves commit order, so the latest checkpoint is the last committed.
        Assert.Equal(committed, index);
        Assert.Equal(committed[^1], latest);
    }
}
