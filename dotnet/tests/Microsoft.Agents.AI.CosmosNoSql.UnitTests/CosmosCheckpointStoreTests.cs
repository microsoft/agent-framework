// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Azure.Cosmos;
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
    private static readonly string s_testDatabaseId = $"AgentFrameworkTests-CheckpointStore-{Guid.NewGuid():N}";
#pragma warning restore CA1802

    private string _connectionString = string.Empty;
    private CosmosClient? _cosmosClient;
    private Database? _database;
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
        this._preserveContainer = string.Equals(Environment.GetEnvironmentVariable("COSMOS_PRESERVE_CONTAINERS"), "true", StringComparison.OrdinalIgnoreCase);

        this._connectionString = $"AccountEndpoint={EmulatorEndpoint};AccountKey={EmulatorKey}";

        try
        {
            this._cosmosClient = new CosmosClient(EmulatorEndpoint, EmulatorKey);

            // Test connection by attempting to create database
            this._database = await this._cosmosClient.CreateDatabaseIfNotExistsAsync(s_testDatabaseId);
            await this._database.CreateContainerIfNotExistsAsync(
                TestContainerId,
                "/runId",
                throughput: 400);

            this._emulatorAvailable = true;
        }
        catch (Exception ex) when (!(ex is OutOfMemoryException || ex is StackOverflowException || ex is AccessViolationException))
        {
            // Emulator not available, tests will be skipped
            this._emulatorAvailable = false;
            this._cosmosClient?.Dispose();
            this._cosmosClient = null;
        }
    }

    public async Task DisposeAsync()
    {
        if (this._cosmosClient != null && this._emulatorAvailable)
        {
            try
            {
                if (this._preserveContainer)
                {
                    // Preserve mode: Don't delete the database/container, keep data for inspection
                    // This allows viewing data in the Cosmos DB Emulator Data Explorer
                    // No cleanup needed - data persists for debugging
                }
                else
                {
                    // Clean mode: Delete the test database and all data
                    await this._database!.DeleteAsync();
                }
            }
            catch (Exception ex)
            {
                // Ignore cleanup errors, but log for diagnostics
                Console.WriteLine($"[DisposeAsync] Cleanup error: {ex.Message}\n{ex.StackTrace}");
            }
            finally
            {
                this._cosmosClient.Dispose();
            }
        }
    }

    private void SkipIfEmulatorNotAvailable()
    {
        // In CI: Skip if COSMOS_EMULATOR_AVAILABLE is not set to "true"
        // Locally: Skip if emulator connection check failed
        var ciEmulatorAvailable = string.Equals(Environment.GetEnvironmentVariable("COSMOS_EMULATOR_AVAILABLE"), "true", StringComparison.OrdinalIgnoreCase);

        Xunit.Skip.If(!ciEmulatorAvailable && !this._emulatorAvailable, "Cosmos DB Emulator is not available");
    }

    #region Constructor Tests

    [SkippableFact]
    public void Constructor_WithCosmosClient_SetsProperties()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);

        // Assert
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [SkippableFact]
    public void Constructor_WithConnectionString_SetsProperties()
    {
        // Arrange
        this.SkipIfEmulatorNotAvailable();

        // Act
        using var store = new CosmosCheckpointStore(this._connectionString, s_testDatabaseId, TestContainerId);

        // Assert
        Assert.Equal(s_testDatabaseId, store.DatabaseId);
        Assert.Equal(TestContainerId, store.ContainerId);
    }

    [SkippableFact]
    public void Constructor_WithNullCosmosClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new CosmosCheckpointStore((CosmosClient)null!, s_testDatabaseId, TestContainerId));
    }

    [SkippableFact]
    public void Constructor_WithNullConnectionString_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new CosmosCheckpointStore((string)null!, s_testDatabaseId, TestContainerId));
    }

    #endregion

    #region Checkpoint Operations Tests

    [SkippableFact]
    public async Task CreateCheckpointAsync_NewCheckpoint_CreatesSuccessfullyAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
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

    [SkippableFact]
    public async Task RetrieveCheckpointAsync_ExistingCheckpoint_ReturnsCorrectValueAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
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

    [SkippableFact]
    public async Task RetrieveCheckpointAsync_NonExistentCheckpoint_ThrowsInvalidOperationExceptionAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();
        var fakeCheckpointInfo = new CheckpointInfo(runId, "nonexistent-checkpoint");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            store.RetrieveCheckpointAsync(runId, fakeCheckpointInfo).AsTask());
    }

    [SkippableFact]
    public async Task RetrieveIndexAsync_EmptyStore_ReturnsEmptyCollectionAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();

        // Act
        var index = await store.RetrieveIndexAsync(runId);

        // Assert
        Assert.NotNull(index);
        Assert.Empty(index);
    }

    [SkippableFact]
    public async Task RetrieveIndexAsync_WithCheckpoints_ReturnsAllCheckpointsAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
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

    [SkippableFact]
    public async Task CreateCheckpointAsync_WithParent_CreatesHierarchyAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
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

    [SkippableFact]
    public async Task RetrieveIndexAsync_WithParentFilter_ReturnsFilteredResultsAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
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

    [SkippableFact]
    public async Task CheckpointOperations_DifferentRuns_IsolatesDataAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
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

    [SkippableFact]
    public async Task CreateCheckpointAsync_WithNullRunId_ThrowsArgumentExceptionAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync(null!, checkpointValue).AsTask());
    }

    [SkippableFact]
    public async Task CreateCheckpointAsync_WithEmptyRunId_ThrowsArgumentExceptionAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync("", checkpointValue).AsTask());
    }

    [SkippableFact]
    public async Task RetrieveCheckpointAsync_WithNullCheckpointInfo_ThrowsArgumentNullExceptionAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        using var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
        var runId = Guid.NewGuid().ToString();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            store.RetrieveCheckpointAsync(runId, null!).AsTask());
    }

    #endregion

    #region Disposal Tests

    [SkippableFact]
    public async Task Dispose_AfterDisposal_ThrowsObjectDisposedExceptionAsync()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act
        store.Dispose();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            store.CreateCheckpointAsync("test-run", checkpointValue).AsTask());
    }

    [SkippableFact]
    public void Dispose_MultipleCalls_DoesNotThrow()
    {
        this.SkipIfEmulatorNotAvailable();

        // Arrange
        var store = new CosmosCheckpointStore(this._cosmosClient!, s_testDatabaseId, TestContainerId);

        // Act & Assert (should not throw)
        store.Dispose();
        store.Dispose();
        store.Dispose();
    }

    #endregion

    public void Dispose()
    {
        this.Dispose(true);
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
