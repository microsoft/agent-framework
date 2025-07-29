// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

#pragma warning disable CA5394 // Insecure randomness is okay for test purposes

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

        var storage = new CosmosActorStateStorage(this._fixture.Container);
        var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

        var key = "testKey";
        var value1 = JsonSerializer.SerializeToElement("value1");
        var value2 = JsonSerializer.SerializeToElement("value2");

        // Act - First write
        var operations1 = new List<ActorStateWriteOperation> { new SetValueOperation(key, value1) };
        var result1 = await storage.WriteStateAsync(testActorId, operations1, "0", cancellationToken);

        // Act - Second write
        var operations2 = new List<ActorStateWriteOperation> { new SetValueOperation(key, value2) };
        var result2 = await storage.WriteStateAsync(testActorId, operations2, result1.ETag, cancellationToken);

        // Act - Third write
        var operations3 = new List<ActorStateWriteOperation> { new RemoveKeyOperation(key) };
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

        var storage = new CosmosActorStateStorage(this._fixture.Container);
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
}
