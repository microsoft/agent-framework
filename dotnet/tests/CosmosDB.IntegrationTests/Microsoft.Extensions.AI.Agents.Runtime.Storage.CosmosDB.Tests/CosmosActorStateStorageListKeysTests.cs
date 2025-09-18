// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

/// <summary>
/// Integration tests for CosmosActorStateStorage focusing on ListKeys functionality.
/// </summary>
[Collection("Cosmos Test Collection")]
public class CosmosActorStateStorageListKeysTests
{
    private readonly CosmosTestFixture _fixture;

    public CosmosActorStateStorageListKeysTests(CosmosTestFixture fixture)
    {
        this._fixture = fixture;
    }

    private static readonly TimeSpan s_defaultTimeout = TimeSpan.FromSeconds(300);

    [Fact]
    public async Task ReadStateAsync_WithListKeysAndKeyPrefix_ShouldReturnFilteredKeysAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string PrefixKey1 = "prefix_key1";
        const string PrefixKey2 = "prefix_key2";
        const string OtherKey = "other_key";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");
        var value3 = JsonSerializer.SerializeToElement("value3");

        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(PrefixKey1, value1),
            new SetValueOperation(PrefixKey2, value2),
            new SetValueOperation(OtherKey, value3)
        };

        await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);

        // Act - List keys with prefix filter
        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "prefix_")
        };
        var result = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(2, listKeys.Keys.Count);
        Assert.Contains(PrefixKey1, listKeys.Keys);
        Assert.Contains(PrefixKey2, listKeys.Keys);
        Assert.DoesNotContain(OtherKey, listKeys.Keys);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysAndNonMatchingPrefix_ShouldReturnEmptyListAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key1 = "key1";
        const string Key2 = "key2";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2)
        };

        await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);

        // Act - List keys with non-matching prefix
        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "nonexistent_")
        };
        var result = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Empty(listKeys.Keys);
        Assert.Null(listKeys.ContinuationToken);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysForEmptyActor_ShouldReturnEmptyListAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Act - List keys for actor with no state
        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };
        var result = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Empty(listKeys.Keys);
        Assert.Null(listKeys.ContinuationToken);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysOperation_ShouldReturnAllKeysAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key1 = "key1";
        const string Key2 = "key2";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2)
        };

        // First write some data
        var writeResult = await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);
        Assert.True(writeResult.Success);

        // Act - List keys
        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert
        Assert.Single(readResult.Results);
        var listKeys = readResult.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(2, listKeys.Keys.Count);
        Assert.Contains(Key1, listKeys.Keys);
        Assert.Contains(Key2, listKeys.Keys);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysAfterKeyRemoval_ShouldNotIncludeRemovedKeysAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key1 = "key1";
        const string Key2 = "key2";
        const string Key3 = "key3";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");
        var value3 = JsonSerializer.SerializeToElement("value3");

        // Setup initial state with 3 keys
        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2),
            new SetValueOperation(Key3, value3)
        };
        var writeResult = await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);
        Assert.True(writeResult.Success);

        // Remove one key
        var removeOperations = new List<ActorStateWriteOperation>
        {
            new RemoveKeyOperation(Key2)
        };
        var removeResult = await storage.WriteStateAsync(testActorId, removeOperations, writeResult.ETag, cancellationToken);
        Assert.True(removeResult.Success);

        // Act - List keys after removal
        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert - Only remaining keys should be listed
        Assert.Single(readResult.Results);
        var listKeys = readResult.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(2, listKeys.Keys.Count);
        Assert.Contains(Key1, listKeys.Keys);
        Assert.Contains(Key3, listKeys.Keys);
        Assert.DoesNotContain(Key2, listKeys.Keys);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysAndMultiplePrefixes_ShouldFilterCorrectlyAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Create keys with different prefixes
        string[] userKeys = ["user_profile", "user_settings", "user_preferences"];
        string[] sessionKeys = ["session_token", "session_data"];
        string[] cacheKeys = ["cache_item1", "cache_item2", "cache_item3"];
        string[] miscKeys = ["config", "metadata"];

        var writeOperations = new List<ActorStateWriteOperation>();
        foreach (var key in userKeys.Concat(sessionKeys).Concat(cacheKeys).Concat(miscKeys))
        {
            writeOperations.Add(new SetValueOperation(key, JsonSerializer.SerializeToElement($"value_for_{key}")));
        }

        await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);

        // Test user_ prefix
        var userReadOps = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "user_")
        };
        var userResult = await storage.ReadStateAsync(testActorId, userReadOps, cancellationToken);
        var userListKeys = userResult.Results[0] as ListKeysResult;
        Assert.NotNull(userListKeys);
        Assert.Equal(3, userListKeys.Keys.Count);
        Assert.All(userKeys, key => Assert.Contains(key, userListKeys.Keys));

        // Test session_ prefix
        var sessionReadOps = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "session_")
        };
        var sessionResult = await storage.ReadStateAsync(testActorId, sessionReadOps, cancellationToken);
        var sessionListKeys = sessionResult.Results[0] as ListKeysResult;
        Assert.NotNull(sessionListKeys);
        Assert.Equal(2, sessionListKeys.Keys.Count);
        Assert.All(sessionKeys, key => Assert.Contains(key, sessionListKeys.Keys));

        // Test cache_ prefix
        var cacheReadOps = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "cache_")
        };
        var cacheResult = await storage.ReadStateAsync(testActorId, cacheReadOps, cancellationToken);
        var cacheListKeys = cacheResult.Results[0] as ListKeysResult;
        Assert.NotNull(cacheListKeys);
        Assert.Equal(3, cacheListKeys.Keys.Count);
        Assert.All(cacheKeys, key => Assert.Contains(key, cacheListKeys.Keys));

        // Test no prefix (should return all keys)
        var allReadOps = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };
        var allResult = await storage.ReadStateAsync(testActorId, allReadOps, cancellationToken);
        var allListKeys = allResult.Results[0] as ListKeysResult;
        Assert.NotNull(allListKeys);
        Assert.Equal(10, allListKeys.Keys.Count); // 3 + 2 + 3 + 2 = 10 total keys
    }
}
