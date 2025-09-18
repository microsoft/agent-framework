// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

/// <summary>
/// Integration tests for CosmosActorStateStorage covering basic CRUD operations and advanced scenarios.
/// </summary>
[Collection("Cosmos Test Collection")]
public class CosmosActorStateStorageTests
{
    private readonly CosmosTestFixture _fixture;

    public CosmosActorStateStorageTests(CosmosTestFixture fixture)
    {
        this._fixture = fixture;
    }

    private static readonly TimeSpan s_defaultTimeout = TimeSpan.FromSeconds(300);

    [Fact]
    public async Task WriteStateAsync_WithSetValueOperation_ShouldStoreValueAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");

        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        // Act
        var result = await storage.WriteStateAsync(testActorId, operations, "0", cancellationToken);

        // Assert
        Assert.True(result.Success);
        Assert.NotEqual("0", result.ETag);
    }

    [Fact]
    public async Task WriteAndReadState_WithMultipleOperations_ShouldMaintainConsistencyAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key1 = "key1";
        const string Key2 = "key2";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement(42);

        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),
            new SetValueOperation(Key2, value2)
        };

        // Act - Write state
        var writeResult = await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);

        // Assert write succeeded
        Assert.True(writeResult.Success);
        Assert.NotNull(writeResult.ETag);
        Assert.NotEqual("0", writeResult.ETag);

        // Act - Read individual values
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key1),
            new GetValueOperation(Key2)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert read succeeded and values match
        Assert.Equal(2, readResult.Results.Count);

        var getValue1 = readResult.Results[0] as GetValueResult;
        var getValue2 = readResult.Results[1] as GetValueResult;

        Assert.NotNull(getValue1);
        Assert.NotNull(getValue2);
        Assert.Equal("value1", getValue1.Value?.GetString());
        Assert.Equal(42, getValue2.Value?.GetInt32());

        // Act - List keys
        var listKeysOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };
        var listResult = await storage.ReadStateAsync(testActorId, listKeysOperations, cancellationToken);

        // Assert keys are listed correctly
        Assert.Single(listResult.Results);
        var listKeys = listResult.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(2, listKeys.Keys.Count);
        Assert.Contains(Key1, listKeys.Keys);
        Assert.Contains(Key2, listKeys.Keys);

        // Act - Update with correct ETag
        var updateOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, JsonSerializer.SerializeToElement("updated_value1")),
            new RemoveKeyOperation(Key2)
        };
        var updateResult = await storage.WriteStateAsync(testActorId, updateOperations, writeResult.ETag, cancellationToken);

        // Assert update succeeded
        Assert.True(updateResult.Success);
        Assert.NotEqual(writeResult.ETag, updateResult.ETag);

        // Act - Verify final state
        var finalReadOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key1),
            new GetValueOperation(Key2),
            new ListKeysOperation(continuationToken: null)
        };
        var finalResult = await storage.ReadStateAsync(testActorId, finalReadOperations, cancellationToken);

        // Assert final state is correct
        Assert.Equal(3, finalResult.Results.Count);

        var finalValue1 = finalResult.Results[0] as GetValueResult;
        var finalValue2 = finalResult.Results[1] as GetValueResult;
        var finalKeys = finalResult.Results[2] as ListKeysResult;

        Assert.NotNull(finalValue1);
        Assert.NotNull(finalValue2);
        Assert.NotNull(finalKeys);

        Assert.Equal("updated_value1", finalValue1.Value?.GetString());
        Assert.Null(finalValue2.Value); // key2 was removed
        Assert.Single(finalKeys.Keys);
        Assert.Contains(Key1, finalKeys.Keys);
        Assert.DoesNotContain(Key2, finalKeys.Keys);
    }

    [Fact]
    public async Task WriteStateAsync_WithIncorrectETag_ShouldReturnFailureAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");
        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        // First write to establish state
        var firstResult = await storage.WriteStateAsync(testActorId, operations, "0", cancellationToken);
        Assert.True(firstResult.Success);

        // Act - Try to write with incorrect ETag
        var incorrectOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, JsonSerializer.SerializeToElement("newValue"))
        };
        var result = await storage.WriteStateAsync(testActorId, incorrectOperations, "incorrect-etag", cancellationToken);

        // Assert
        Assert.False(result.Success);
        Assert.Empty(result.ETag);

        // Verify original value is unchanged
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);
        var getValue = readResult.Results[0] as GetValueResult;
        Assert.Equal("testValue", getValue?.Value?.GetString());
    }

    [Fact]
    public async Task DifferentActors_ShouldHaveIsolatedStateAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId1 = new ActorId("TestActor1", Guid.NewGuid().ToString());
        var testActorId2 = new ActorId("TestActor2", Guid.NewGuid().ToString());

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

        // Act - Write to both actors
        await storage.WriteStateAsync(testActorId1, operations1, "0", cancellationToken);
        await storage.WriteStateAsync(testActorId2, operations2, "0", cancellationToken);

        // Assert - Verify values are different
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };

        var result1 = await storage.ReadStateAsync(testActorId1, readOperations, cancellationToken);
        var result2 = await storage.ReadStateAsync(testActorId2, readOperations, cancellationToken);

        var getValue1 = result1.Results[0] as GetValueResult;
        var getValue2 = result2.Results[0] as GetValueResult;

        Assert.NotNull(getValue1);
        Assert.NotNull(getValue2);
        Assert.Equal("value1", getValue1.Value?.GetString());
        Assert.Equal("value2", getValue2.Value?.GetString());
        Assert.NotEqual(result1.ETag, result2.ETag);
    }

    [Fact]
    public async Task WriteStateAsync_WithEmptyOperations_ShouldThrowExceptionAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;
        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());
        var emptyOperations = new List<ActorStateWriteOperation>();
        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await storage.WriteStateAsync(testActorId, emptyOperations, "0", cancellationToken));
    }

    [Fact]
    public async Task ReadStateAsync_WithGetValueForNonExistentKey_ShouldReturnNullAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation("nonExistentKey")
        };

        // Act
        var result = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert
        Assert.Single(result.Results);
        var getValue = result.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.Null(getValue.Value);
    }

    [Fact]
    public async Task WriteStateAsync_WithComplexJsonValue_ShouldSerializeCorrectlyAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Create a complex object with various types
        var complexObject = new
        {
            Id = 123,
            Name = "Test Object",
            Properties = new Dictionary<string, object>
            {
                { "StringProp", "value" },
                { "NumberProp", 42.5 },
                { "BoolProp", true },
                { "ArrayProp", (int[])[1, 2, 3] },
                { "NestedProp", new { Inner = "nested value" } }
            },
            Tags = new[] { "tag1", "tag2", "tag3" },
            Metadata = new Dictionary<string, string>
            {
                { "version", "1.0" },
                { "author", "test" }
            }
        };

        const string Key = "complexObject";
        var value = JsonSerializer.SerializeToElement(complexObject);

        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        // Act - Write complex object
        var writeResult = await storage.WriteStateAsync(testActorId, operations, "0", cancellationToken);
        Assert.True(writeResult.Success);

        // Act - Read back complex object
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert - Verify complex object was stored and retrieved correctly
        Assert.Single(readResult.Results);
        var getValue = readResult.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.NotNull(getValue.Value);

        // Deserialize and verify structure
        var retrievedObject = JsonSerializer.Deserialize<JsonElement>(getValue.Value!.Value.GetRawText());
        Assert.Equal(123, retrievedObject.GetProperty("Id").GetInt32());
        Assert.Equal("Test Object", retrievedObject.GetProperty("Name").GetString());

        var properties = retrievedObject.GetProperty("Properties");
        Assert.Equal("value", properties.GetProperty("StringProp").GetString());
        Assert.Equal(42.5, properties.GetProperty("NumberProp").GetDouble());
        Assert.True(properties.GetProperty("BoolProp").GetBoolean());

        var tags = retrievedObject.GetProperty("Tags");
        Assert.Equal(3, tags.GetArrayLength());
        Assert.Equal("tag1", tags[0].GetString());
    }

    [Fact]
    public async Task MultipleOperationsInSequence_ShouldBeProcessedInOrderAsync()
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

        // Act - Perform multiple operations in a single batch
        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key1, value1),      // Set key1
            new SetValueOperation(Key2, value2),      // Set key2  
            new SetValueOperation(Key3, value3),      // Set key3
            new RemoveKeyOperation(Key1),             // Remove key1
            new SetValueOperation(Key1, JsonSerializer.SerializeToElement("new_value1")) // Re-add key1 with new value
        };

        var result = await storage.WriteStateAsync(testActorId, operations, "0", cancellationToken);

        // Assert write succeeded
        Assert.True(result.Success);

        // Act - Verify final state
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key1),
            new GetValueOperation(Key2),
            new GetValueOperation(Key3),
            new ListKeysOperation(continuationToken: null)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert final state is correct
        Assert.Equal(4, readResult.Results.Count);

        var getValue1 = readResult.Results[0] as GetValueResult;
        var getValue2 = readResult.Results[1] as GetValueResult;
        var getValue3 = readResult.Results[2] as GetValueResult;
        var listKeys = readResult.Results[3] as ListKeysResult;

        Assert.NotNull(getValue1);
        Assert.NotNull(getValue2);
        Assert.NotNull(getValue3);
        Assert.NotNull(listKeys);

        // key1 should have the final value from the last operation
        Assert.Equal("new_value1", getValue1.Value?.GetString());
        Assert.Equal("value2", getValue2.Value?.GetString());
        Assert.Equal("value3", getValue3.Value?.GetString());

        // All three keys should be present
        Assert.Equal(3, listKeys.Keys.Count);
        Assert.Contains(Key1, listKeys.Keys);
        Assert.Contains(Key2, listKeys.Keys);
        Assert.Contains(Key3, listKeys.Keys);
    }

    [SkipOnEmulatorFact]
    public async Task WriteAndReadState_WithSpecialCharactersInKeys_ShouldHandleSanitizationAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Test keys with special characters that need sanitization
        var specialKeys = new[]
        {
            "key/with/slashes",
            "key with spaces",
            "key:with:colons",
            "key@with@symbols",
            "key%with%percent",
            "key#with#hash",
            "key?with?query",
            "key&with&ampersand"
        };

        var writeOperations = new List<ActorStateWriteOperation>();
        for (int i = 0; i < specialKeys.Length; i++)
        {
            var value = JsonSerializer.SerializeToElement($"value{i}");
            writeOperations.Add(new SetValueOperation(specialKeys[i], value));
        }

        // Act - Write keys with special characters
        var writeResult = await storage.WriteStateAsync(testActorId, writeOperations, "0", cancellationToken);

        // Assert write succeeded
        Assert.True(writeResult.Success);
        Assert.NotNull(writeResult.ETag);

        // Act - Read back each key individually
        for (int i = 0; i < specialKeys.Length; i++)
        {
            var readOperations = new List<ActorStateReadOperation>
            {
                new GetValueOperation(specialKeys[i])
            };
            var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

            // Assert each key can be read back correctly
            Assert.Single(readResult.Results);
            var getValue = readResult.Results[0] as GetValueResult;
            Assert.NotNull(getValue);
            Assert.NotNull(getValue.Value);
            Assert.Equal($"value{i}", getValue.Value?.GetString());
        }

        // Act - List all keys
        var listOperations = new List<ActorStateReadOperation>
        {
            new ListKeysOperation(continuationToken: null)
        };
        var listResult = await storage.ReadStateAsync(testActorId, listOperations, cancellationToken);

        // Assert all keys are present in the list
        Assert.Single(listResult.Results);
        var listKeys = listResult.Results[0] as ListKeysResult;
        Assert.NotNull(listKeys);
        Assert.Equal(specialKeys.Length, listKeys.Keys.Count);

        foreach (var specialKey in specialKeys)
        {
            Assert.Contains(specialKey, listKeys.Keys);
        }
    }
}
