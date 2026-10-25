// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// Tests for <see cref="RedisCheckpointStore"/> against a real Redis server. See <see cref="RedisFixture"/> for how to run them.
/// </summary>
/// <remarks>
/// Each test instance writes under its own key prefix and deletes its keys when it is disposed.
/// </remarks>
[Collection(RedisCollectionFixture.Name)]
public sealed class RedisCheckpointStoreServerTests : IAsyncLifetime
{
    private static readonly string[] s_sessionKeySuffixes = ["seq", "index", "data", "parents"];

    private readonly RedisFixture _redis;
    private readonly string _keyPrefix = $"af-tests:{Guid.NewGuid():N}";

    public RedisCheckpointStoreServerTests(RedisFixture redis)
    {
        this._redis = redis;
    }

    public ValueTask InitializeAsync()
    {
        this._redis.SkipIfNotAvailable();
        return default;
    }

    public async ValueTask DisposeAsync()
    {
        if (!this._redis.IsAvailable)
        {
            return;
        }

        IDatabase database = this._redis.Connection.GetDatabase();
        foreach (IServer server in this._redis.Connection.GetServers())
        {
            await foreach (RedisKey key in server.KeysAsync(pattern: $"{this._keyPrefix}:*"))
            {
                await database.KeyDeleteAsync(key);
            }
        }
    }

    [Fact]
    public async Task Workflow_ResumesFromCheckpoint_WithNewConnectionAndStoreAsync()
    {
        // Arrange: run the workflow to completion; a checkpoint is created at the end of every super step.
        const string SessionId = "guess-number";
        List<CheckpointInfo> checkpoints = [];
        string? firstOutput = null;
        CheckpointManager firstManager = CheckpointManager.CreateJson(this.CreateStore());
        await using (StreamingRun run = await InProcessExecution.RunStreamingAsync(GuessNumberWorkflow.Build(), NumberSignal.Init, firstManager, SessionId))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
                {
                    checkpoints.Add(checkpoint);
                }
                else if (evt is WorkflowOutputEvent output)
                {
                    firstOutput = output.Data?.ToString();
                }
            }
        }

        // Act: as a restarted process would, open a new connection, store, manager and workflow, and resume from the second checkpoint.
        await using ConnectionMultiplexer secondConnection = await RedisFixture.ConnectAsync();
        RedisCheckpointStore secondStore = this.CreateStore(secondConnection);
        CheckpointManager secondManager = CheckpointManager.CreateJson(secondStore);
        IEnumerable<CheckpointInfo> index = await secondStore.RetrieveIndexAsync(SessionId);
        CheckpointInfo? latest = await secondManager.GetLatestCheckpointAsync(SessionId);

        string? resumedOutput = null;
        await using (StreamingRun resumed = await InProcessExecution.ResumeStreamingAsync(GuessNumberWorkflow.Build(), checkpoints[1], secondManager))
        {
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync())
            {
                if (evt is WorkflowOutputEvent output)
                {
                    resumedOutput = output.Data?.ToString();
                }
            }
        }

        // Assert: the executor state (number of tries) came back from Redis.
        Assert.True(checkpoints.Count >= 4);
        Assert.Equal(checkpoints, index);
        Assert.Equal(checkpoints[^1], latest);
        Assert.Equal("42 found in 7 tries", firstOutput);
        Assert.Equal(firstOutput, resumedOutput);
    }

    [Fact]
    public async Task RetrieveIndexAsync_ReturnsCommitOrderPerSessionAndFiltersByParentAsync()
    {
        // Arrange: many checkpoints within the same second, so a timestamp-based order could not tell them apart.
        RedisCheckpointStore store = this.CreateStore();
        List<CheckpointInfo> committed = [];
        CheckpointInfo? parent = null;
        for (int i = 0; i < 25; i++)
        {
            parent = await store.CreateCheckpointAsync("session-a", JsonSerializer.SerializeToElement(i), parent);
            committed.Add(parent);
        }

        CheckpointInfo other = await store.CreateCheckpointAsync("session-b", JsonSerializer.SerializeToElement("b"));

        // Act
        IEnumerable<CheckpointInfo> index = await store.RetrieveIndexAsync("session-a");
        IEnumerable<CheckpointInfo> children = await store.RetrieveIndexAsync("session-a", withParent: committed[2]);
        IEnumerable<CheckpointInfo> otherIndex = await store.RetrieveIndexAsync("session-b");
        IEnumerable<CheckpointInfo> unknownIndex = await store.RetrieveIndexAsync("session-c");
        CheckpointInfo? latest = await CheckpointManager.CreateJson(store).GetLatestCheckpointAsync("session-a");

        // Assert
        Assert.Equal(committed, index);
        Assert.Equal([committed[3]], children);
        Assert.Equal([other], otherIndex);
        Assert.Empty(unknownIndex);
        Assert.Equal(committed[^1], latest);
    }

    [Fact]
    public async Task CreateCheckpointAsync_ConcurrentWritersOnSeparateConnections_IndexesEveryCheckpointAsync()
    {
        // Arrange
        await using ConnectionMultiplexer secondConnection = await RedisFixture.ConnectAsync();
        RedisCheckpointStore[] stores = [this.CreateStore(), this.CreateStore(secondConnection)];

        // Act
        CheckpointInfo[] created = await Task.WhenAll(Enumerable.Range(0, 40).Select(i =>
            Task.Run(() => stores[i % 2].CreateCheckpointAsync("session-a", JsonSerializer.SerializeToElement(i)).AsTask())));
        IEnumerable<CheckpointInfo> index = await stores[0].RetrieveIndexAsync("session-a");

        // Assert
        Assert.Equal(created.Length, index.Count());
        Assert.Equal(created.OrderBy(c => c.CheckpointId), index.OrderBy(c => c.CheckpointId));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_ReturnsPayloadVerbatimAsync()
    {
        // Arrange: polymorphic payloads need the type discriminator to stay first, so the JSON must not be reordered.
        const string Json = """{"$type":"state","z":1,"a":{"$type":"nested","name":"İstanbul"},"list":[3,2,1]}""";
        CheckpointInfo key = await this.CreateStore().CreateCheckpointAsync("session-a", JsonDocument.Parse(Json).RootElement);

        // Act
        await using ConnectionMultiplexer secondConnection = await RedisFixture.ConnectAsync();
        JsonElement value = await this.CreateStore(secondConnection).RetrieveCheckpointAsync("session-a", key);

        // Assert
        Assert.Equal(Json, value.GetRawText());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_UnknownCheckpointOrSession_ThrowsKeyNotFoundExceptionAsync()
    {
        // Arrange
        RedisCheckpointStore store = this.CreateStore();
        CheckpointInfo key = await store.CreateCheckpointAsync("session-a", JsonSerializer.SerializeToElement(1));

        // Act & Assert
        await Assert.ThrowsAsync<KeyNotFoundException>(() => store.RetrieveCheckpointAsync("session-a", new CheckpointInfo("session-a", "missing")).AsTask());
        await Assert.ThrowsAsync<KeyNotFoundException>(() => store.RetrieveCheckpointAsync("session-b", key).AsTask());
    }

    [Theory]
    [InlineData("}abc")]
    [InlineData("{x}")]
    [InlineData("a{b}c")]
    [InlineData("{}")]
    [InlineData("%7B")]
    [InlineData("İstanbul")]
    public async Task CheckpointOperations_WithBracesOrUnicodeInSessionId_SucceedAsync(string sessionId)
    {
        // Arrange: on Redis Cluster a malformed hash tag would make the create script fail with CROSSSLOT.
        RedisCheckpointStore store = this.CreateStore(timeToLive: TimeSpan.FromHours(1));
        CheckpointInfo first = await store.CreateCheckpointAsync(sessionId, JsonSerializer.SerializeToElement(1));

        // Act
        CheckpointInfo second = await store.CreateCheckpointAsync(sessionId, JsonSerializer.SerializeToElement(2), parent: first);
        IEnumerable<CheckpointInfo> index = await store.RetrieveIndexAsync(sessionId);
        IEnumerable<CheckpointInfo> children = await store.RetrieveIndexAsync(sessionId, withParent: first);
        JsonElement value = await store.RetrieveCheckpointAsync(sessionId, second);

        // Assert
        Assert.Equal([first, second], index);
        Assert.Equal([second], children);
        Assert.Equal(2, value.GetInt32());
    }

    [Fact]
    public async Task CreateCheckpointAsync_SessionKeysShareHashSlotAndExpireTogetherAsync()
    {
        // Arrange
        RedisCheckpointStore store = this.CreateStore(timeToLive: TimeSpan.FromHours(1));
        CheckpointInfo first = await store.CreateCheckpointAsync("session-a", JsonSerializer.SerializeToElement(1));

        // Act
        await store.CreateCheckpointAsync("session-a", JsonSerializer.SerializeToElement(2), parent: first);

        // Assert
        IDatabase database = this._redis.Connection.GetDatabase();
        RedisKey[] keys = [.. s_sessionKeySuffixes.Select(suffix => (RedisKey)$"{this._keyPrefix}:{{session-a}}:{suffix}")];
        Assert.Single(keys.Select(k => RedisHashSlot.Calculate(k.ToString())).Distinct());
        foreach (RedisKey key in keys)
        {
            TimeSpan? timeToLive = await database.KeyTimeToLiveAsync(key);
            Assert.NotNull(timeToLive);
            Assert.InRange(timeToLive.Value, TimeSpan.FromMinutes(59), TimeSpan.FromHours(1));
        }
    }

    private RedisCheckpointStore CreateStore(IConnectionMultiplexer? connection = null, TimeSpan? timeToLive = null) =>
        new(connection ?? this._redis.Connection, new RedisCheckpointStoreOptions { KeyPrefix = this._keyPrefix, TimeToLive = timeToLive });
}
