// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using CosmosDB.Testing.AppHost;
using Microsoft.Azure.Cosmos;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB.Tests;

/// <summary>
/// Integration tests for LazyCosmosContainer to verify lazy initialization behavior.
/// </summary>
[Collection("Cosmos Test Collection")]
public class LazyCosmosContainerTests
{
    private readonly CosmosTestFixture _fixture;

    public LazyCosmosContainerTests(CosmosTestFixture fixture)
    {
        this._fixture = fixture;
    }

    private static readonly TimeSpan s_defaultTimeout = TimeSpan.FromSeconds(300);

    [Fact]
    public async Task GetContainerAsync_WithExistingContainer_ShouldReturnImmediatelyAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.Container);

        // Act
        var result = await lazyContainer.GetContainerAsync();

        // Assert
        Assert.Same(this._fixture.Container, result);
    }

    [Fact]
    public async Task GetContainerAsync_WithExistingContainer_MultipleCalls_ShouldReturnSameInstanceAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.Container);

        // Act
        var result1 = await lazyContainer.GetContainerAsync();
        var result2 = await lazyContainer.GetContainerAsync();
        var result3 = await lazyContainer.GetContainerAsync();

        // Assert
        Assert.Same(result1, result2);
        Assert.Same(result2, result3);
        Assert.Same(this._fixture.Container, result1);
    }

    [SkipOnEmulatorFact]
    public async Task GetContainerAsync_WithCosmosClient_ShouldInitializeAndWorkCorrectlyAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        // Create a unique container name for this test
        var testContainerName = $"LazyContainerTest_{Guid.NewGuid():N}";
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.CosmosClient, CosmosDBTestConstants.TestCosmosDbDatabaseName, testContainerName);

        try
        {
            // Act
            var container = await lazyContainer.GetContainerAsync();

            // Assert - Container should be usable for actual operations
            Assert.NotNull(container);
            Assert.Equal(testContainerName, container.Id);

            // Verify the container can perform basic operations
            var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());
            await using var storage = new CosmosActorStateStorage(lazyContainer);

            const string Key = "testKey";
            var value = JsonSerializer.SerializeToElement("testValue");
            var operations = new List<ActorStateWriteOperation>
            {
                new SetValueOperation(Key, value)
            };

            // This should work if the container was properly initialized
            var writeResult = await storage.WriteStateAsync(testActorId, operations, "0", cancellationToken);
            Assert.True(writeResult.Success);
            Assert.NotEqual("0", writeResult.ETag);
        }
        finally
        {
            // Cleanup - delete the test container
            try
            {
                var container = await lazyContainer.GetContainerAsync();
                await container.DeleteContainerAsync();
            }
            catch
            {
                // Ignore cleanup errors
            }
        }
    }

    [Fact]
    public async Task GetContainerAsync_WithCosmosClient_MultipleCalls_ShouldReturnSameInstanceAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);

        // Create a unique container name for this test
        var testContainerName = $"LazyContainerTest_{Guid.NewGuid():N}";
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.CosmosClient, CosmosDBTestConstants.TestCosmosDbDatabaseName, testContainerName);

        try
        {
            // Act
            var result1 = await lazyContainer.GetContainerAsync();
            var result2 = await lazyContainer.GetContainerAsync();
            var result3 = await lazyContainer.GetContainerAsync();

            // Assert
            Assert.Same(result1, result2);
            Assert.Same(result2, result3);
            Assert.Equal(testContainerName, result1.Id);
        }
        finally
        {
            // Cleanup
            try
            {
                var container = await lazyContainer.GetContainerAsync();
                await container.DeleteContainerAsync();
            }
            catch
            {
                // Ignore cleanup errors
            }
        }
    }

    [Fact]
    public async Task GetContainerAsync_WithCosmosClient_ConcurrentAccess_ShouldInitializeOnlyOnceAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);

        // Create a unique container name for this test
        var testContainerName = $"LazyContainerTest_{Guid.NewGuid():N}";
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.CosmosClient, CosmosDBTestConstants.TestCosmosDbDatabaseName, testContainerName);

        try
        {
            // Act - Execute multiple concurrent calls
            var tasks = new List<Task<Container>>();
            for (int i = 0; i < 10; i++)
            {
                tasks.Add(lazyContainer.GetContainerAsync());
            }
            var results = await Task.WhenAll(tasks);

            // Assert
            // All results should be the same instance
            for (int i = 1; i < results.Length; i++)
            {
                Assert.Same(results[0], results[i]);
            }
            Assert.Equal(testContainerName, results[0].Id);
        }
        finally
        {
            // Cleanup
            try
            {
                var container = await lazyContainer.GetContainerAsync();
                await container.DeleteContainerAsync();
            }
            catch
            {
                // Ignore cleanup errors
            }
        }
    }

    [Fact]
    public void Constructor_WithNullContainer_ShouldThrowArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new LazyCosmosContainer(null!));

    [Fact]
    public void Constructor_WithNullCosmosClient_ShouldThrowArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new LazyCosmosContainer(null!, "test-db", "test-container"));

    [Fact]
    public void Constructor_WithNullDatabaseName_ShouldThrowArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new LazyCosmosContainer(this._fixture.CosmosClient, null!, "test-container"));

    [Fact]
    public void Constructor_WithNullContainerName_ShouldThrowArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new LazyCosmosContainer(this._fixture.CosmosClient, "test-db", null!));

    [SkipOnEmulatorFact]
    public async Task LazyCosmosContainer_WithInternalConstructor_ShouldWorkWithCosmosActorStateStorageAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);
        var cancellationToken = cts.Token;

        // Create a unique container name for this test
        var testContainerName = $"LazyContainerTest_{Guid.NewGuid():N}";
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.CosmosClient, CosmosDBTestConstants.TestCosmosDbDatabaseName, testContainerName);

        try
        {
            // Act - Create storage using the internal constructor (like DI would)
            await using var storage = new CosmosActorStateStorage(lazyContainer);
            var testActorId = new ActorId("TestActor", Guid.NewGuid().ToString());

            const string Key = "testKey";
            var value = JsonSerializer.SerializeToElement("testValue");
            var operations = new List<ActorStateWriteOperation>
            {
                new SetValueOperation(Key, value)
            };

            // This should work - container should be initialized on first storage operation
            var writeResult = await storage.WriteStateAsync(testActorId, operations, "0", cancellationToken);

            // Assert
            Assert.True(writeResult.Success);
            Assert.NotEqual("0", writeResult.ETag);

            // Verify we can read back the value
            var readOperations = new List<ActorStateReadOperation>
            {
                new GetValueOperation(Key)
            };
            var readResult = await storage.ReadStateAsync(testActorId, readOperations, cancellationToken);

            Assert.Single(readResult.Results);
            var getValue = readResult.Results[0] as GetValueResult;
            Assert.NotNull(getValue);
            Assert.Equal("testValue", getValue.Value?.GetString());
        }
        finally
        {
            // Cleanup
            try
            {
                var container = await lazyContainer.GetContainerAsync();
                await container.DeleteContainerAsync();
            }
            catch
            {
                // Ignore cleanup errors
            }
        }
    }

    [Fact]
    public async Task GetContainerAsync_WithInvalidDatabaseName_ShouldThrowCosmosExceptionAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource(s_defaultTimeout);

        // Use an invalid database name that should cause Cosmos to reject it
        var invalidDatabaseName = new string('a', 256); // Database names have limits
        await using var lazyContainer = new LazyCosmosContainer(this._fixture.CosmosClient, invalidDatabaseName, "test-container");

        // Act & Assert
        await Assert.ThrowsAsync<CosmosException>(lazyContainer.GetContainerAsync);
    }
}
