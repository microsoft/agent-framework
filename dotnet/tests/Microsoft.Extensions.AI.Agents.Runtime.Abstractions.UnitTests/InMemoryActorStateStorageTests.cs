// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="InMemoryActorStateStorage"/> class.
/// </summary>
[System.Diagnostics.CodeAnalysis.SuppressMessage("Style", "IDE1006:Naming Styles", Justification = "Test naming convention")]
public sealed class InMemoryActorStateStorageTests
{
    private readonly InMemoryActorStateStorage _storage = new();
    private readonly ActorId _testActorId = new("TestActor", "test-instance");
    private readonly ActorId _anotherActorId = new("AnotherActor", "another-instance");

    [Fact]
    public async Task WriteStateAsync_WithSetValueOperation_ShouldStoreValueAsync()
    {
        // Arrange
        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");
        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        // Act
        var result = await this._storage.WriteStateAsync(this._testActorId, operations, "0", CancellationToken.None);

        // Assert
        Assert.True(result.Success);
        Assert.NotEqual("0", result.ETag);
        Assert.Equal(1, this._storage.GetKeyCount(this._testActorId));
    }

    [Fact]
    public async Task WriteStateAsync_WithRemoveKeyOperation_ShouldRemoveValueAsync()
    {
        // Arrange
        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");

        // First set a value
        var setOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };
        var setResult = await this._storage.WriteStateAsync(this._testActorId, setOperations, "0", CancellationToken.None);

        // Now remove the value
        var removeOperations = new List<ActorStateWriteOperation>
        {
            new RemoveKeyOperation(Key)
        };

        // Act
        var result = await this._storage.WriteStateAsync(this._testActorId, removeOperations, setResult.ETag, CancellationToken.None);

        // Assert
        Assert.True(result.Success);
        Assert.NotEqual(setResult.ETag, result.ETag);
        Assert.Equal(0, this._storage.GetKeyCount(this._testActorId));
    }

    [Fact]
    public async Task WriteStateAsync_WithIncorrectETag_ShouldReturnFailureAsync()
    {
        // Arrange
        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");
        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        // Act
        var result = await this._storage.WriteStateAsync(this._testActorId, operations, "incorrect-etag", CancellationToken.None);

        // Assert
        Assert.False(result.Success);
        Assert.Equal("0", result.ETag); // Should return current ETag
        Assert.Equal(0, this._storage.GetKeyCount(this._testActorId));
    }

    [Fact]
    public async Task ReadStateAsync_WithGetValueOperation_ShouldReturnValueAsync()
    {
        // Arrange
        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");
        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };
        await this._storage.WriteStateAsync(this._testActorId, writeOperations, "0", CancellationToken.None);

        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };

        // Act
        var result = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);

        // Assert
        Assert.Single(result.Results);
        var getValue = result.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.NotNull(getValue.Value);
        Assert.Equal("testValue", getValue.Value?.GetString());
    }

    [Fact]
    public async Task ReadStateAsync_WithGetValueOperationForNonExistentKey_ShouldReturnNullAsync()
    {
        // Arrange
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation("nonExistentKey")
        };

        // Act
        var result = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);

        // Assert
        Assert.Single(result.Results);
        var getValue = result.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.Null(getValue.Value);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysOperation_ShouldReturnAllKeysAsync()
    {
        // Arrange
        const string Key1 = "key1";
        const string Key2 = "key2";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2)
        };
        await this._storage.WriteStateAsync(this._testActorId, writeOperations, "0", CancellationToken.None);

        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };

        // Act
        var result = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(2, listKeys.Keys.Count);
        Assert.Contains(Key1, listKeys.Keys);
        Assert.Contains(Key2, listKeys.Keys);
        Assert.Null(listKeys.ContinuationToken);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysOperationForEmptyActor_ShouldReturnEmptyListAsync()
    {
        // Arrange
        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };

        // Act
        var result = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Empty(listKeys.Keys);
        Assert.Null(listKeys.ContinuationToken);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysOperationAndKeyPrefix_ShouldReturnFilteredKeysAsync()
    {
        // Arrange
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
        await this._storage.WriteStateAsync(this._testActorId, writeOperations, "0", CancellationToken.None);

        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "prefix_")
        };

        // Act
        var result = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(2, listKeys.Keys.Count);
        Assert.Contains(PrefixKey1, listKeys.Keys);
        Assert.Contains(PrefixKey2, listKeys.Keys);
        Assert.DoesNotContain(OtherKey, listKeys.Keys);
        Assert.Null(listKeys.ContinuationToken);
    }

    [Fact]
    public async Task ReadStateAsync_WithListKeysOperationAndNonMatchingKeyPrefix_ShouldReturnEmptyListAsync()
    {
        // Arrange
        const string Key1 = "key1";
        const string Key2 = "key2";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2)
        };
        await this._storage.WriteStateAsync(this._testActorId, writeOperations, "0", CancellationToken.None);

        var readOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null, keyPrefix: "prefix_")
        };

        // Act
        var result = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);

        // Assert
        Assert.Single(result.Results);
        var listKeys = result.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Empty(listKeys.Keys);
        Assert.Null(listKeys.ContinuationToken);
    }

    [Fact]
    public async Task MultipleOperations_ShouldBeProcessedInOrderAsync()
    {
        // Arrange
        const string Key1 = "key1";
        const string Key2 = "key2";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2),
            new RemoveKeyOperation(Key1)
        };

        // Act
        var result = await this._storage.WriteStateAsync(this._testActorId, operations, "0", CancellationToken.None);

        // Assert
        Assert.True(result.Success);
        Assert.Equal(1, this._storage.GetKeyCount(this._testActorId));

        // Verify remaining key
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key2)
        };
        var readResult = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);
        var getValue = readResult.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.Equal("value2", getValue.Value?.GetString());
    }

    [Fact]
    public async Task DifferentActors_ShouldHaveIsolatedStateAsync()
    {
        // Arrange
        const string Key = "sharedKey";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        var operations1 = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value1)
        };
        var operations2 = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value2)
        };

        // Act
        await this._storage.WriteStateAsync(this._testActorId, operations1, "0", CancellationToken.None);
        await this._storage.WriteStateAsync(this._anotherActorId, operations2, "0", CancellationToken.None);

        // Assert
        Assert.Equal(2, this._storage.ActorCount);
        Assert.Equal(1, this._storage.GetKeyCount(this._testActorId));
        Assert.Equal(1, this._storage.GetKeyCount(this._anotherActorId));

        // Verify values are different
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };

        var result1 = await this._storage.ReadStateAsync(this._testActorId, readOperations, CancellationToken.None);
        var result2 = await this._storage.ReadStateAsync(this._anotherActorId, readOperations, CancellationToken.None);

        var getValue1 = result1.Results[0] as GetValueResult;
        var getValue2 = result2.Results[0] as GetValueResult;

        Assert.NotNull(getValue1);
        Assert.NotNull(getValue2);
        Assert.Equal("value1", getValue1.Value?.GetString());
        Assert.Equal("value2", getValue2.Value?.GetString());
    }

    [Fact]
    public async Task ConcurrentOperations_ShouldBeThreadSafeAsync()
    {
        // Arrange
        const int OperationCount = 100;
        var tasks = new List<Task>();

        // Act
        for (int i = 0; i < OperationCount; i++)
        {
            var key = $"key{i}";
            var value = JsonSerializer.SerializeToElement($"value{i}");
            var actorId = new ActorId("TestActor", $"instance{i % 10}"); // 10 different actors
            var operations = new List<ActorStateWriteOperation>
            {
                new SetValueOperation(key, value)
            };

            tasks.Add(Task.Run(async () =>
            {
                // Retry logic to handle concurrent updates
                var success = false;
                var retryCount = 0;
                const int MaxRetries = 10;

                while (!success && retryCount < MaxRetries)
                {
                    var currentETag = this._storage.GetETag(actorId);
                    var result = await this._storage.WriteStateAsync(actorId, operations, currentETag, CancellationToken.None);
                    success = result.Success;
                    retryCount++;
                }
            }));
        }

        await Task.WhenAll(tasks);

        // Assert
        Assert.Equal(10, this._storage.ActorCount); // 10 different actors

        // Verify each actor has the expected number of keys
        for (int i = 0; i < 10; i++)
        {
            var actorId = new ActorId("TestActor", $"instance{i}");
            Assert.Equal(10, this._storage.GetKeyCount(actorId)); // Each actor should have 10 keys
        }
    }

    [Fact]
    public async Task Clear_ShouldRemoveAllStateAsync()
    {
        // Arrange
        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");
        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        await this._storage.WriteStateAsync(this._testActorId, operations, "0", CancellationToken.None);
        Assert.Equal(1, this._storage.ActorCount);

        // Act
        this._storage.Clear();

        // Assert
        Assert.Equal(0, this._storage.ActorCount);
        Assert.Equal(0, this._storage.GetKeyCount(this._testActorId));
        Assert.Equal("0", this._storage.GetETag(this._testActorId));
    }

    [Fact]
    public void GetETag_ForNewActor_ShouldReturnZero()
    {
        // Act
        var etag = this._storage.GetETag(this._testActorId);

        // Assert
        Assert.Equal("0", etag);
    }

    [Fact]
    public async Task WriteStateAsync_WithNullOperations_ShouldThrowArgumentNullExceptionAsync() =>
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            this._storage.WriteStateAsync(this._testActorId, null!, "0", CancellationToken.None).AsTask());

    [Fact]
    public async Task WriteStateAsync_WithNullETag_ShouldThrowArgumentNullExceptionAsync()
    {
        // Arrange
        var operations = new List<ActorStateWriteOperation>();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            this._storage.WriteStateAsync(this._testActorId, operations, null!, CancellationToken.None).AsTask());
    }

    [Fact]
    public async Task ReadStateAsync_WithNullOperations_ShouldThrowArgumentNullExceptionAsync() =>
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            this._storage.ReadStateAsync(this._testActorId, null!, CancellationToken.None).AsTask());

    [Fact]
    public async Task WriteStateAsync_WithCancelledToken_ShouldThrowOperationCanceledExceptionAsync()
    {
        // Arrange
        var operations = new List<ActorStateWriteOperation>();
        var cancellationToken = new CancellationToken(canceled: true);

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            this._storage.WriteStateAsync(this._testActorId, operations, "0", cancellationToken).AsTask());
    }

    [Fact]
    public async Task ReadStateAsync_WithCancelledToken_ShouldThrowOperationCanceledExceptionAsync()
    {
        // Arrange
        var operations = new List<ActorStateReadOperation>();
        var cancellationToken = new CancellationToken(canceled: true);

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            this._storage.ReadStateAsync(this._testActorId, operations, cancellationToken).AsTask());
    }

    [Fact]
    public async Task ETagProgression_ShouldIncrementMonotonicallyAsync()
    {
        // Arrange
        const string Key = "testKey";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        // Act
        var operations1 = new List<ActorStateWriteOperation> { new SetValueOperation(Key, value1) };
        var result1 = await this._storage.WriteStateAsync(this._testActorId, operations1, "0", CancellationToken.None);

        var operations2 = new List<ActorStateWriteOperation> { new SetValueOperation(Key, value2) };
        var result2 = await this._storage.WriteStateAsync(this._testActorId, operations2, result1.ETag, CancellationToken.None);

        // Assert
        Assert.True(result1.Success);
        Assert.True(result2.Success);
        Assert.NotEqual("0", result1.ETag);
        Assert.NotEqual(result1.ETag, result2.ETag);

        // ETags should be numeric and increasing
        Assert.True(long.Parse(result1.ETag) < long.Parse(result2.ETag));
    }

    [Fact]
    public void ListKeysOperation_JsonSerialization_ShouldWorkCorrectly()
    {
        // Arrange
        var operation = new ListKeysOperation(continuationToken: "token123", keyPrefix: "prefix_");

        // Act - Serialize to JSON
        var json = JsonSerializer.Serialize(operation);

        // Deserialize back to object
        var deserializedOperation = JsonSerializer.Deserialize<ListKeysOperation>(json);

        // Assert
        Assert.NotNull(deserializedOperation);
        Assert.Equal("token123", deserializedOperation.ContinuationToken);
        Assert.Equal("prefix_", deserializedOperation.KeyPrefix);
        Assert.Equal(ActorReadOperationType.ListKeys, deserializedOperation.Type);
    }
}
