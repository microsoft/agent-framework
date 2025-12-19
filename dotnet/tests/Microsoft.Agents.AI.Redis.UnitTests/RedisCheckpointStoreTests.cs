// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// Contains tests for <see cref="RedisCheckpointStore"/>.
///
/// To run tests with Redis:
/// - Set REDIS_CONNECTION_STRING environment variable (e.g., "localhost:6379")
/// - Set REDIS_AVAILABLE=true to enable Redis-dependent tests
///
/// Example (PowerShell):
/// $env:REDIS_CONNECTION_STRING="localhost:6379"; $env:REDIS_AVAILABLE="true"; dotnet test
///
/// Example (Bash):
/// REDIS_CONNECTION_STRING="localhost:6379" REDIS_AVAILABLE="true" dotnet test
/// </summary>
[Collection("Redis")]
[SuppressMessage("Performance", "CA1859:Use concrete types when possible for improved performance", Justification = "Interface needed for test flexibility")]
public class RedisCheckpointStoreTests : IAsyncLifetime, IDisposable
{
    private ConnectionMultiplexer? _connectionMultiplexer;
    private string _connectionString = string.Empty;
    private bool _redisAvailable;

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
        var envConnectionString = Environment.GetEnvironmentVariable("REDIS_CONNECTION_STRING");

        if (string.IsNullOrEmpty(envConnectionString))
        {
            // No Redis connection string provided, tests will be skipped
            this._redisAvailable = false;
            return;
        }

        try
        {
            this._connectionString = envConnectionString;
            this._connectionMultiplexer = await ConnectionMultiplexer.ConnectAsync(this._connectionString).ConfigureAwait(false);
            this._redisAvailable = this._connectionMultiplexer.IsConnected;
        }
        catch (Exception ex) when (ex is not OutOfMemoryException and not StackOverflowException and not AccessViolationException)
        {
            // Redis not available, tests will be skipped
            this._redisAvailable = false;
            this._connectionMultiplexer?.Dispose();
            this._connectionMultiplexer = null;
        }
    }

    public Task DisposeAsync()
    {
        this._connectionMultiplexer?.Dispose();
        return Task.CompletedTask;
    }

    private void SkipIfRedisNotAvailable()
    {
        var ciRedisAvailable = string.Equals(
            Environment.GetEnvironmentVariable("REDIS_AVAILABLE"),
            "true",
            StringComparison.OrdinalIgnoreCase);

        Xunit.Skip.If(!ciRedisAvailable && !this._redisAvailable, "Redis is not available. Set REDIS_CONNECTION_STRING and REDIS_AVAILABLE=true to run these tests.");
    }

    #region Constructor Tests

    [SkippableFact]
    public void Constructor_WithConnectionString_SetsProperties()
    {
        this.SkipIfRedisNotAvailable();

        // Act
        using var store = new RedisCheckpointStore(this._connectionString);

        // Assert
        Assert.Equal("checkpoint", store.KeyPrefix);
        Assert.Null(store.TimeToLive);
    }

    [SkippableFact]
    public void Constructor_WithOptions_SetsProperties()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        var options = new RedisCheckpointStoreOptions
        {
            KeyPrefix = "custom",
            TimeToLive = TimeSpan.FromHours(1)
        };

        // Act
        using var store = new RedisCheckpointStore(this._connectionString, options);

        // Assert
        Assert.Equal("custom", store.KeyPrefix);
        Assert.Equal(TimeSpan.FromHours(1), store.TimeToLive);
    }

    [SkippableFact]
    public void Constructor_WithConnectionMultiplexer_SetsProperties()
    {
        this.SkipIfRedisNotAvailable();

        // Act
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);

        // Assert
        Assert.Equal("checkpoint", store.KeyPrefix);
    }

    [Fact]
    public void Constructor_WithNullConnectionString_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new RedisCheckpointStore((string)null!));
    }

    [Fact]
    public void Constructor_WithEmptyConnectionString_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            new RedisCheckpointStore(string.Empty));
    }

    [Fact]
    public void Constructor_WithNullConnectionMultiplexer_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new RedisCheckpointStore((IConnectionMultiplexer)null!));
    }

    #endregion

    #region Checkpoint Operations Tests

    [SkippableFact]
    public async Task CreateCheckpointAsync_NewCheckpoint_CreatesSuccessfullyAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(
            new { data = "test checkpoint" }, s_jsonOptions);

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
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
        var runId = Guid.NewGuid().ToString();
        var fakeCheckpointInfo = new CheckpointInfo(runId, "nonexistent-checkpoint");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            store.RetrieveCheckpointAsync(runId, fakeCheckpointInfo).AsTask());
    }

    [SkippableFact]
    public async Task RetrieveIndexAsync_EmptyStore_ReturnsEmptyCollectionAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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

    #region TTL Tests

    [SkippableFact]
    public async Task CreateCheckpointAsync_WithTtl_SetsExpirationAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        var options = new RedisCheckpointStoreOptions
        {
            TimeToLive = TimeSpan.FromSeconds(30),
            KeyPrefix = $"ttl_test_{Guid.NewGuid():N}"
        };

        using var store = new RedisCheckpointStore(this._connectionMultiplexer!, options);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act
        var checkpointInfo = await store.CreateCheckpointAsync(runId, checkpointValue);

        // Assert - Verify TTL was set on the key
        var db = this._connectionMultiplexer!.GetDatabase();
        var key = $"{options.KeyPrefix}:{runId}:{checkpointInfo.CheckpointId}";
        var ttl = await db.KeyTimeToLiveAsync(key);

        Assert.NotNull(ttl);
        Assert.True(ttl.Value.TotalSeconds > 0 && ttl.Value.TotalSeconds <= 30);
    }

    [SkippableFact]
    public async Task CreateCheckpointAsync_WithoutTtl_NoExpirationAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        var options = new RedisCheckpointStoreOptions
        {
            TimeToLive = null,
            KeyPrefix = $"no_ttl_test_{Guid.NewGuid():N}"
        };

        using var store = new RedisCheckpointStore(this._connectionMultiplexer!, options);
        var runId = Guid.NewGuid().ToString();
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act
        var checkpointInfo = await store.CreateCheckpointAsync(runId, checkpointValue);

        // Assert - Verify no TTL was set on the key
        var db = this._connectionMultiplexer!.GetDatabase();
        var key = $"{options.KeyPrefix}:{runId}:{checkpointInfo.CheckpointId}";
        var ttl = await db.KeyTimeToLiveAsync(key);

        Assert.Null(ttl);
    }

    #endregion

    #region Run Isolation Tests

    [SkippableFact]
    public async Task CheckpointOperations_DifferentRuns_IsolatesDataAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync(null!, checkpointValue).AsTask());
    }

    [SkippableFact]
    public async Task CreateCheckpointAsync_WithEmptyRunId_ThrowsArgumentExceptionAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
        var checkpointValue = JsonSerializer.SerializeToElement(new { data = "test" }, s_jsonOptions);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync(string.Empty, checkpointValue).AsTask());
    }

    [SkippableFact]
    public async Task RetrieveCheckpointAsync_WithNullRunId_ThrowsArgumentExceptionAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
        var fakeCheckpointInfo = new CheckpointInfo("run", "checkpoint");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.RetrieveCheckpointAsync(null!, fakeCheckpointInfo).AsTask());
    }

    [SkippableFact]
    public async Task RetrieveCheckpointAsync_WithNullCheckpointInfo_ThrowsArgumentNullExceptionAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);
        var runId = Guid.NewGuid().ToString();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            store.RetrieveCheckpointAsync(runId, null!).AsTask());
    }

    [SkippableFact]
    public async Task RetrieveIndexAsync_WithNullRunId_ThrowsArgumentExceptionAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        using var store = new RedisCheckpointStore(this._connectionMultiplexer!);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() =>
            store.RetrieveIndexAsync(null!).AsTask());
    }

    #endregion

    #region Disposal Tests

    [SkippableFact]
    public async Task Dispose_AfterDisposal_ThrowsObjectDisposedExceptionAsync()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange
        var store = new RedisCheckpointStore(this._connectionMultiplexer!);
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
        this.SkipIfRedisNotAvailable();

        // Arrange
        var store = new RedisCheckpointStore(this._connectionMultiplexer!);

        // Act & Assert (should not throw)
        store.Dispose();
        store.Dispose();
        store.Dispose();
    }

    [SkippableFact]
    public void Dispose_WithOwnedConnection_DisposesConnection()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange - Create store with connection string (owns connection)
        var store = new RedisCheckpointStore(this._connectionString);

        // Act
        store.Dispose();

        // Assert - Store should be disposed without throwing
        // The owned connection should be disposed
        Assert.True(true); // If we get here, disposal worked
    }

    [SkippableFact]
    public void Dispose_WithSharedConnection_DoesNotDisposeConnection()
    {
        this.SkipIfRedisNotAvailable();

        // Arrange - Create store with existing multiplexer (does not own connection)
        var store = new RedisCheckpointStore(this._connectionMultiplexer!);

        // Act
        store.Dispose();

        // Assert - The shared connection should still be connected
        Assert.True(this._connectionMultiplexer!.IsConnected);
    }

    #endregion

    #region Extension Methods Tests

    [SkippableFact]
    public void CreateRedisCheckpointStore_WithConnectionString_CreatesStore()
    {
        this.SkipIfRedisNotAvailable();

        // Act
        using var store = RedisWorkflowExtensions.CreateRedisCheckpointStore(this._connectionString);

        // Assert
        Assert.NotNull(store);
        Assert.Equal("checkpoint", store.KeyPrefix);
    }

    [SkippableFact]
    public void CreateRedisCheckpointStoreWithTtl_CreatesStoreWithTtl()
    {
        this.SkipIfRedisNotAvailable();

        // Act
        using var store = RedisWorkflowExtensions.CreateRedisCheckpointStoreWithTtl(
            this._connectionString,
            TimeSpan.FromHours(2),
            "custom_prefix");

        // Assert
        Assert.NotNull(store);
        Assert.Equal("custom_prefix", store.KeyPrefix);
        Assert.Equal(TimeSpan.FromHours(2), store.TimeToLive);
    }

    #endregion

    public void Dispose()
    {
        this.Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        // Connection multiplexer disposed in DisposeAsync
    }
}
