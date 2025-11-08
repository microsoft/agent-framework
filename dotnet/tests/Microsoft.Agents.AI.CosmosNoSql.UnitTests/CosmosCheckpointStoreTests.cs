// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Azure.Cosmos;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Xunit;

namespace Microsoft.Agents.AI.CosmosNoSql.UnitTests;

/// <summary>
/// Contains tests for <see cref="CosmosCheckpointStore"/>.
///
/// Test Modes:
/// - Default Mode: Cleans up all test data after each test run (deletes database)
/// - Preserve Mode: Keeps containers and data for inspection in Cosmos DB Emulator Data Explorer
///
/// To enable Preserve Mode, set environment variable: COSMOS_PRESERVE_CONTAINERS=true
/// Example: $env:COSMOS_PRESERVE_CONTAINERS="true"; dotnet test
///
/// In Preserve Mode, you can view the data in Cosmos DB Emulator Data Explorer at:
/// https://localhost:8081/_explorer/index.html
/// Database: AgentFrameworkTests
/// Container: Checkpoints
/// </summary>
[Collection("CosmosDB")]
public class CosmosCheckpointStoreTests : IAsyncLifetime, IDisposable
{
    // Cosmos DB Emulator connection settings
    private const string EmulatorEndpoint = "https://localhost:8081";
    private const string EmulatorKey = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==";
    private const string TestContainerId = "Checkpoints";
    // Use unique database ID per test class instance to avoid conflicts
#pragma warning disable CA1802 // Use literals where appropriate
    private static readonly string TestDatabaseId = $"AgentFrameworkTests-CheckpointStore-{Guid.NewGuid():N}";
#pragma warning restore CA1802

    private string _connectionString = string.Empty;
    private CosmosClient? _cosmosClient;
    private Database? _database;
    private Container? _container;
    private bool _emulatorAvailable;
    private bool _preserveContainer;

    // JsonSerializerOptions configured for .NET 9+ compatibility
    private static readonly JsonSerializerOptions s_jsonOptions = CreateJsonOptions();

    private static JsonSerializerOptions CreateJsonOptions()
    {
        var options = new JsonSerializerOptions();
#if NET9_0_OR_GREATER
        options.TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver();
#endif
        return options;
    }

    public async Task InitializeAsync()
    {
        // Check environment variable to determine if we should preserve containers
        // Set COSMOS_PRESERVE_CONTAINERS=true to keep containers and data for inspection
        _preserveContainer = string.Equals(Environment.GetEnvironmentVariable("COSMOS_PRESERVE_CONTAINERS"), "true", StringComparison.OrdinalIgnoreCase);

        _connectionString = $"AccountEndpoint={EmulatorEndpoint};AccountKey={EmulatorKey}";

        try
        {
            _cosmosClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);

            // Test connection by attempting to create database
            _database = await _cosmosClient.CreateDatabaseIfNotExistsAsync(TestDatabaseId);
            _container = await _database.CreateContainerIfNotExistsAsync(
                TestContainerId,
                "/runId",
                throughput: 400);

            _emulatorAvailable = true;
        }
        catch (Exception ex) when (!(ex is OutOfMemoryException || ex is StackOverflowException || ex is AccessViolationException))
        {
            // Emulator not available, tests will be skipped
            _emulatorAvailable = false;
            _cosmosClient?.Dispose();
            _cosmosClient = null;
        }
    }

    public async Task DisposeAsync()
    {
        if (_cosmosClient != null && _emulatorAvailable)
        {
            try
            {
                if (_preserveContainer)
                {
                    // Preserve mode: Don't delete the database/container, keep data for inspection
                    // This allows viewing data in the Cosmos DB Emulator Data Explorer
                    // No cleanup needed - data persists for debugging
                }
                else
                {
                    // Clean mode: Delete the test database and all data
                    await _database!.DeleteAsync();
                }
            }
            catch (Exception ex)
            {
                // Ignore cleanup errors, but log for diagnostics
                Console.WriteLine($"[DisposeAsync] Cleanup error: {ex.Message}\n{ex.StackTrace}");
            }
            finally
            {
                _cosmosClient.Dispose();
            }
        }
    }

        private void SkipIfEmulatorNotAvailable()
        {
            if (!this._emulatorAvailable)
            {
                // Skip test if emulator is not available (e.g., on Linux CI runners)
                return;
            }
        }

    #region Constructor Tests

    [Fact]
    public void Constructor_WithCosmosClient_SetsProperties()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);

        // Assert
        Assert.Equal(TestDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [Fact]
    public void Constructor_WithConnectionString_SetsProperties()
    {
        // Arrange
        SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosCheckpointStore(_connectionString, TestDatabaseId, TestContainerId);

        // Assert
        Assert.Equal(TestDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [Fact]
    public void Constructor_WithNullCosmosClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new CosmosCheckpointStore((CosmosClient)null!, TestDatabaseId, TestContainerId));
    }

    [Fact]
    public void Constructor_WithNullConnectionString_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new CosmosCheckpointStore((string)null!, TestDatabaseId, TestContainerId));
    }

    #endregion

    #region Checkpoint Operations Tests

    [Fact]
    public async Task CreateCheckpointAsync_NewCheckpoint_CreatesSuccessfully()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test checkpoint" }, s_jsonOptions);

        // Act
        var checkpointInfo = await store.CreateCheckpointAsync(runId, checkpointValue);

        // Assert
        Assert.NotNull(checkpointInfo);
        Assert.Equal(runId, checkpointInfo.RunId);
        Assert.NotNull(checkpointInfo.CheckpointId);
        Assert.NotEmpty(checkpointInfo.CheckpointId);
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_ExistingCheckpoint_ReturnsCorrectValue()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var originalData = new { message = "Hello, World!", timestamp = DateTimeOffset.UtcNow };
        var checkpointValue = JsonSerializer.SerializeToElement(originalData, s_jsonOptions);

        // Act
        var checkpointInfo = await store.CreateCheckpointAsync(runId, checkpointValue);
        var retrievedValue = await store.RetrieveCheckpointAsync(runId, checkpointInfo);

        // Assert
        Assert.Equal(JsonValueKind.Object, retrievedValue.ValueKind);
        Assert.True(retrievedValue.TryGetProperty("message", out var messageProp));
        Assert.Equal("Hello, World!", messageProp.GetString());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_NonExistentCheckpoint_ThrowsInvalidOperationException()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var fakeCheckpointInfo = new CheckpointInfo(runId, "nonexistent-checkpoint");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            store.RetrieveCheckpointAsync(runId, fakeCheckpointInfo).AsTask());
    }

    [Fact]
    public async Task RetrieveIndexAsync_EmptyStore_ReturnsEmptyCollection()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();

        // Act
        var index = await store.RetrieveIndexAsync(runId);

        // Assert
        Assert.NotNull(index);
        Assert.Empty(index);
    }

    [Fact]
    public async Task RetrieveIndexAsync_WithCheckpoints_ReturnsAllCheckpoints()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Create multiple checkpoints
        var checkpoint1 = await store.CreateCheckpointAsync(runId, checkpointValue);
        var checkpoint2 = await store.CreateCheckpointAsync(runId, checkpointValue);
        var checkpoint3 = await store.CreateCheckpointAsync(runId, checkpointValue);

        // Act
        var index = (await store.RetrieveIndexAsync(runId)).ToList();

        // Assert
        Assert.Equal(3, index.Count);
        Assert.Contains(index, c => c.CheckpointId == checkpoint1.CheckpointId);
        Assert.Contains(index, c => c.CheckpointId == checkpoint2.CheckpointId);
        Assert.Contains(index, c => c.CheckpointId == checkpoint3.CheckpointId);
    }

    [Fact]
    public async Task CreateCheckpointAsync_WithParent_CreatesHierarchy()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act
        var parentCheckpoint = await store.CreateCheckpointAsync(runId, checkpointValue);
        var childCheckpoint = await store.CreateCheckpointAsync(runId, checkpointValue, parentCheckpoint);

        // Assert
        Assert.NotEqual(parentCheckpoint.CheckpointId, childCheckpoint.CheckpointId);
        Assert.Equal(runId, parentCheckpoint.RunId);
        Assert.Equal(runId, childCheckpoint.RunId);
    }

    [Fact]
    public async Task RetrieveIndexAsync_WithParentFilter_ReturnsFilteredResults()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Create parent and child checkpoints
        var parent = await store.CreateCheckpointAsync(runId, checkpointValue);
        var child1 = await store.CreateCheckpointAsync(runId, checkpointValue, parent);
        var child2 = await store.CreateCheckpointAsync(runId, checkpointValue, parent);

        // Create an orphan checkpoint
        var orphan = await store.CreateCheckpointAsync(runId, checkpointValue);

        // Act
        var allCheckpoints = (await store.RetrieveIndexAsync(runId)).ToList();
        var childrenOfParent = (await store.RetrieveIndexAsync(runId, parent)).ToList();

        // Assert
        Assert.Equal(4, allCheckpoints.Count); // parent + 2 children + orphan
        Assert.Equal(2, childrenOfParent.Count); // only children

        Assert.Contains(childrenOfParent, c => c.CheckpointId == child1.CheckpointId);
        Assert.Contains(childrenOfParent, c => c.CheckpointId == child2.CheckpointId);
        Assert.DoesNotContain(childrenOfParent, c => c.CheckpointId == parent.CheckpointId);
        Assert.DoesNotContain(childrenOfParent, c => c.CheckpointId == orphan.CheckpointId);
    }

    #endregion

    #region Run Isolation Tests

    [Fact]
    public async Task CheckpointOperations_DifferentRuns_IsolatesData()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId1 = Guid.NewGuid().ToString();
        var runId2 = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act
        var checkpoint1 = await store.CreateCheckpointAsync(runId1, checkpointValue);
        var checkpoint2 = await store.CreateCheckpointAsync(runId2, checkpointValue);

        var index1 = (await store.RetrieveIndexAsync(runId1)).ToList();
        var index2 = (await store.RetrieveIndexAsync(runId2)).ToList();

        // Assert
        Assert.Single(index1);
        Assert.Single(index2);
        Assert.Equal(checkpoint1.CheckpointId, index1[0].CheckpointId);
        Assert.Equal(checkpoint2.CheckpointId, index2[0].CheckpointId);
        Assert.NotEqual(checkpoint1.CheckpointId, checkpoint2.CheckpointId);
    }

    #endregion

    #region Error Handling Tests

    [Fact]
    public async Task CreateCheckpointAsync_WithNullRunId_ThrowsArgumentException()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync(null!, checkpointValue).AsTask());
    }

    [Fact]
    public async Task CreateCheckpointAsync_WithEmptyRunId_ThrowsArgumentException()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync("", checkpointValue).AsTask());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_WithNullCheckpointInfo_ThrowsArgumentNullException()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            store.RetrieveCheckpointAsync(runId, null!).AsTask());
    }

    #endregion

    #region Disposal Tests

    [Fact]
    public async Task Dispose_AfterDisposal_ThrowsObjectDisposedException()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act
        store.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            store.CreateCheckpointAsync("test-run", checkpointValue).AsTask());
    }

    [Fact]
    public void Dispose_MultipleCalls_DoesNotThrow()
    {
        SkipIfEmulatorNotAvailable();

        // Arrange
        var store = new CosmosCheckpointStore(_cosmosClient!, TestDatabaseId, TestContainerId);

        // Act & Assert (should not throw)
        store.Dispose();
        store.Dispose();
        store.Dispose();
    }

    #endregion

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (disposing)
        {
            this._cosmosClient?.Dispose();
        }
    }
}
