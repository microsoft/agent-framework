// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

/// <summary>
/// Integration tests for CosmosActorStateStorage focusing on concurrency control and ETag progression.
/// </summary>
[Collection("Cosmos Test Collection")]
public class CosmosActorStateStorageConcurrencyTests
{
    private readonly CosmosTestFixture _fixture;

    public CosmosActorStateStorageConcurrencyTests(CosmosTestFixture fixture)
    {
        this._fixture = fixture;
    }

    private static readonly TimeSpan s_defaultTimeout = TimeSpan.FromSeconds(300);

    [Fact]
    public async Task ETagProgression_ShouldChangeWithEachWriteAsync()
    {
        // CosmosDB ETags are not guaranteed to be numeric or monotonically increasing
        // They are opaque strings that change with each update, which is sufficient for optimistic concurrency

        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        const string Key = "testKey";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        // Act - First write
        var operations1 = new List<ActorStateWriteOperation> { new SetValueOperation(Key, value1) };
        var result1 = await storage.WriteStateAsync(testActorId, operations1, "0", cancellationToken);

        // Act - Second write
        var operations2 = new List<ActorStateWriteOperation> { new SetValueOperation(Key, value2) };
        var result2 = await storage.WriteStateAsync(testActorId, operations2, result1.ETag, cancellationToken);

        // Act - Third write
        var operations3 = new List<ActorStateWriteOperation> { new RemoveKeyOperation(Key) };
        var result3 = await storage.WriteStateAsync(testActorId, operations3, result2.ETag, cancellationToken);

        // Assert
        Assert.True(result1.Success);
        Assert.True(result2.Success);
        Assert.True(result3.Success);
        Assert.NotEqual("0", result1.ETag);
        Assert.NotEqual(result1.ETag, result2.ETag);
        Assert.NotEqual(result2.ETag, result3.ETag);

        // Verify ETags are all different and represent progression
        string[] etags = [result1.ETag, result2.ETag, result3.ETag];
        Assert.Equal(3, etags.Distinct().Count());
    }

    [Fact]
    public async Task ConcurrentWrites_ShouldHandleOptimisticConcurrencyCorrectlyAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Setup initial state
        var initialOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation("counter", JsonSerializer.SerializeToElement(0))
        };
        var initialResult = await storage.WriteStateAsync(testActorId, initialOperations, "0", cancellationToken);
        Assert.True(initialResult.Success);

        const int ConcurrentOperations = 10;
        var tasks = new List<Task<(bool Success, string? ETag, int AttemptNumber)>>();

        // Act - Simulate concurrent writes with retry logic
        for (int i = 0; i < ConcurrentOperations; i++)
        {
            var operationNumber = i;
            tasks.Add(Task.Run(async () =>
            {
                var success = false;
                var retryCount = 0;
                const int MaxRetries = 20;
                string? finalETag = null;

                while (!success && retryCount < MaxRetries)
                {
                    try
                    {
                        // Read current state to get latest ETag
                        var readOps = new List<ActorStateReadOperation>
                        {
                            new GetValueOperation("counter")
                        };
                        var readResult = await storage.ReadStateAsync(testActorId, readOps, cancellationToken);
                        var currentETag = readResult.ETag;

                        var currentValue = readResult.Results[0] as GetValueResult;
                        var currentCounter = currentValue?.Value?.GetInt32() ?? 0;

                        // Try to increment the counter
                        var writeOps = new List<ActorStateWriteOperation>
                        {
                            new SetValueOperation("counter", JsonSerializer.SerializeToElement(currentCounter + 1)),
                            new SetValueOperation($"operation_{operationNumber}", JsonSerializer.SerializeToElement($"completed_attempt_{retryCount}"))
                        };

                        var writeResult = await storage.WriteStateAsync(testActorId, writeOps, currentETag, cancellationToken);

                        if (writeResult.Success)
                        {
                            success = true;
                            finalETag = writeResult.ETag;
                        }
                        else
                        {
                            retryCount++;
                            // Small delay to reduce contention
                            await Task.Delay(Random.Shared.Next(1, 10), cancellationToken);
                        }
                    }
                    catch (Exception)
                    {
                        retryCount++;
                        await Task.Delay(Random.Shared.Next(1, 10), cancellationToken);
                    }
                }

                return (success, finalETag, retryCount);
            }));
        }

        // Wait for all operations to complete
        var results = await Task.WhenAll(tasks);

        // Assert - All operations should eventually succeed
        Assert.All(results, result => Assert.True(result.Success, $"Operation failed after {result.AttemptNumber} attempts"));

        // Act - Verify final state
        var finalReadOps = new List<ActorStateReadOperation>
        {
            new GetValueOperation("counter"),
            new ListKeysOperation(continuationToken: null)
        };
        var finalResult = await storage.ReadStateAsync(testActorId, finalReadOps, cancellationToken);

        var finalCounter = finalResult.Results[0] as GetValueResult;
        var finalKeys = finalResult.Results[1] as ListKeysResult;

        // Assert final state is consistent
        Assert.NotNull(finalCounter);
        Assert.NotNull(finalKeys);
        Assert.Equal(ConcurrentOperations, finalCounter.Value?.GetInt32()); // Counter should equal number of operations
        Assert.Equal(ConcurrentOperations + 1, finalKeys.Keys.Count); // counter + operation_N keys

        // Verify all operation keys are present
        Assert.Contains("counter", finalKeys.Keys);
        for (int i = 0; i < ConcurrentOperations; i++)
        {
            Assert.Contains($"operation_{i}", finalKeys.Keys);
        }

        // Log retry statistics for debugging
        var totalRetries = results.Sum(r => r.AttemptNumber);
        var maxRetries = results.Max(r => r.AttemptNumber);
        Console.WriteLine($"Concurrent operations completed. Total retries: {totalRetries}, Max retries for single operation: {maxRetries}");
    }

    [Fact]
    public async Task WriteStateAsync_InitialETagHandling_ShouldWorkCorrectlyAsync()
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

        // Act & Assert - Test null eTag (should create new document)
        var resultWithNullETag = await storage.WriteStateAsync(testActorId, operations, null!, cancellationToken);
        Assert.True(resultWithNullETag.Success);
        Assert.NotNull(resultWithNullETag.ETag);
        Assert.NotEmpty(resultWithNullETag.ETag);

        // Clean up for next test
        var uniqueActorId1 = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Act & Assert - Test empty eTag (should create new document)
        var resultWithEmptyETag = await storage.WriteStateAsync(uniqueActorId1, operations, string.Empty, cancellationToken);
        Assert.True(resultWithEmptyETag.Success);
        Assert.NotNull(resultWithEmptyETag.ETag);
        Assert.NotEmpty(resultWithEmptyETag.ETag);

        // Clean up for next test
        var uniqueActorId2 = new ActorId("TestActor", Guid.NewGuid().ToString());

        // Act & Assert - Test "0" initial eTag (should create new document)
        var resultWithInitialETag = await storage.WriteStateAsync(uniqueActorId2, operations, "0", cancellationToken);
        Assert.True(resultWithInitialETag.Success);
        Assert.NotNull(resultWithInitialETag.ETag);
        Assert.NotEmpty(resultWithInitialETag.ETag);
        Assert.NotEqual("0", resultWithInitialETag.ETag);

        // Act & Assert - Test writing again with "0" should fail (document already exists)
        var secondWriteWithInitialETag = await storage.WriteStateAsync(uniqueActorId2, operations, "0", cancellationToken);
        Assert.False(secondWriteWithInitialETag.Success);
        Assert.Empty(secondWriteWithInitialETag.ETag);

        // Act & Assert - Test writing with correct eTag should succeed
        var updateOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, JsonSerializer.SerializeToElement("updatedValue"))
        };
        var resultWithCorrectETag = await storage.WriteStateAsync(uniqueActorId2, updateOperations, resultWithInitialETag.ETag, cancellationToken);
        Assert.True(resultWithCorrectETag.Success);
        Assert.NotNull(resultWithCorrectETag.ETag);
        Assert.NotEqual(resultWithInitialETag.ETag, resultWithCorrectETag.ETag);

        // Verify the value was actually updated
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };
        var readResult = await storage.ReadStateAsync(uniqueActorId2, readOperations, cancellationToken);
        var getValue = readResult.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.Equal("updatedValue", getValue.Value?.GetString());
    }

    [Fact]
    public async Task ReadThenWrite_OnNonExistentActor_ShouldWorkCorrectlyAsync()
    {
        // 1. Read state from a non-existent actor (gets initial ETag)
        // 2. Write with that ETag (should succeed)

        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString()); // Fresh actor

        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");

        // Act - Read state from non-existent actor (this calls GetActorETagAsync internally)
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

        // Assert - Read should succeed but return null value and initial ETag
        Assert.Single(readResult.Results);
        var getValue = readResult.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.Null(getValue.Value); // No value exists yet
        Assert.Equal("0", readResult.ETag); // Should return initial ETag for non-existent actor

        // Act - Write using the ETag from the read operation
        var writeOperations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };
        var writeResult = await storage.WriteStateAsync(testActorId, writeOperations, readResult.ETag, cancellationToken);

        // Assert - Write should succeed
        Assert.True(writeResult.Success);
        Assert.NotNull(writeResult.ETag);
        Assert.NotEqual("0", writeResult.ETag); // Should get a real ETag after write

        // Act - Verify the value was written
        var verifyReadResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);
        var verifyGetValue = verifyReadResult.Results[0] as GetValueResult;

        // Assert - Value should now exist
        Assert.NotNull(verifyGetValue);
        Assert.NotNull(verifyGetValue.Value);
        Assert.Equal("testValue", verifyGetValue.Value?.GetString());
        Assert.Equal(writeResult.ETag, verifyReadResult.ETag); // ETags should match
    }

    [Fact]
    public async Task WriteStateAsync_WithInvalidETag_ShouldFailAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        await using var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString()); // Non-existent actor

        const string Key = "testKey";
        var value = JsonSerializer.SerializeToElement("testValue");
        var operations = new List<ActorStateWriteOperation>
        {
            new SetValueOperation(Key, value)
        };

        // Act - Try to write with a completely fabricated/invalid ETag (no document exists)
        const string FabricatedETag = "\"fabricated-etag-12345\""; // Made-up ETag for non-existent document
        var resultWithFabricatedETag = await storage.WriteStateAsync(testActorId, operations, FabricatedETag, cancellationToken);

        // Assert - The write should fail due to ETag mismatch (document doesn't exist)
        Assert.False(resultWithFabricatedETag.Success);
        Assert.Empty(resultWithFabricatedETag.ETag);

        // Verify no document was created
        var readOperations = new List<ActorStateReadOperation>
        {
            new GetValueOperation(Key)
        };
        var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);
        var getValue = readResult.Results[0] as GetValueResult;
        Assert.NotNull(getValue);
        Assert.Null(getValue.Value); // Should be null since no document exists
    }
}
