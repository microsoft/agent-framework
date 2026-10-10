// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Moq;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// Unit tests for <see cref="RedisCheckpointStore"/> that run against a mocked <see cref="IDatabase"/>.
/// Behavior against a real Redis server is covered by <see cref="RedisCheckpointStoreServerTests"/>.
/// </summary>
public sealed class RedisCheckpointStoreTests
{
    private readonly Mock<IDatabase> _database = new();
    private readonly Mock<IConnectionMultiplexer> _connection = new();

    public RedisCheckpointStoreTests()
    {
        this._connection
            .Setup(c => c.GetDatabase(It.IsAny<int>(), It.IsAny<object?>()))
            .Returns(this._database.Object);
    }

    #region Constructor

    [Fact]
    public void Constructor_NullConnection_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new RedisCheckpointStore(null!));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_EmptyKeyPrefix_Throws(string keyPrefix)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new RedisCheckpointStore(this._connection.Object, new() { KeyPrefix = keyPrefix }));
    }

    [Theory]
    [InlineData("{x}")]
    [InlineData("{}")]
    [InlineData("app{")]
    [InlineData("}app")]
    public void Constructor_KeyPrefixWithHashTagBraces_Throws(string keyPrefix)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new RedisCheckpointStore(this._connection.Object, new() { KeyPrefix = keyPrefix }));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void Constructor_NonPositiveTimeToLive_Throws(int seconds)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() =>
            new RedisCheckpointStore(this._connection.Object, new() { TimeToLive = TimeSpan.FromSeconds(seconds) }));
    }

    #endregion

    #region CreateCheckpointAsync

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public async Task CreateCheckpointAsync_InvalidSessionId_ThrowsAsync(string? sessionId)
    {
        // Arrange
        RedisCheckpointStore store = new(this._connection.Object);

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() =>
            store.CreateCheckpointAsync(sessionId!, JsonSerializer.SerializeToElement(1)).AsTask());
    }

    [Fact]
    public async Task CreateCheckpointAsync_WritesSessionKeysAtomicallyAsync()
    {
        // Arrange
        RedisKey[]? keys = null;
        RedisValue[]? values = null;
        this.SetupScriptEvaluate((k, v) => (keys, values) = (k, v));
        RedisCheckpointStore store = new(this._connection.Object, new() { KeyPrefix = "app", Database = 3, TimeToLive = TimeSpan.FromMinutes(5) });
        CheckpointInfo parent = new("session-1", "parent-id");

        // Act
        CheckpointInfo checkpoint = await store.CreateCheckpointAsync("session-1", JsonSerializer.SerializeToElement(new { step = 2 }), parent);

        // Assert
        Assert.Equal("session-1", checkpoint.SessionId);
        Assert.False(string.IsNullOrEmpty(checkpoint.CheckpointId));
        Assert.Equal(["app:{session-1}:seq", "app:{session-1}:index", "app:{session-1}:data", "app:{session-1}:parents"], keys!.Select(k => k.ToString()));
        Assert.Equal([checkpoint.CheckpointId, """{"step":2}""", "parent-id", "300000"], values!.Select(v => v.ToString()));
        this._connection.Verify(c => c.GetDatabase(3, It.IsAny<object?>()), Times.Once);
    }

    [Theory]
    [InlineData("checkpoints", "session-1")]
    [InlineData("checkpoints", "}abc")]
    [InlineData("checkpoints", "{x}")]
    [InlineData("checkpoints", "a{b}c")]
    [InlineData("checkpoints", "{}")]
    [InlineData("checkpoints", "}")]
    [InlineData("checkpoints", "a}b{c")]
    [InlineData("checkpoints", "%7B")]
    [InlineData("checkpoints", "İstanbul")]
    [InlineData("app:tenant-1", "}abc")]
    [InlineData("İzmir:checkpoints", "a{b}c")]
    public async Task CreateCheckpointAsync_SessionKeys_ShareOneClusterHashSlotAsync(string keyPrefix, string sessionId)
    {
        // Arrange
        RedisKey[]? keys = null;
        this.SetupScriptEvaluate((k, _) => keys = k);
        RedisCheckpointStore store = new(this._connection.Object, new() { KeyPrefix = keyPrefix });

        // Act
        await store.CreateCheckpointAsync(sessionId, JsonSerializer.SerializeToElement(1));

        // Assert: one script touches all four keys, so on Redis Cluster they must hash to the same slot.
        Assert.Equal(4, keys!.Length);
        Assert.All(keys, key => Assert.StartsWith($"{keyPrefix}:{{", key.ToString(), StringComparison.Ordinal));
        Assert.Single(keys.Select(key => RedisHashSlot.Calculate(key.ToString())).Distinct());
    }

    [Theory]
    [InlineData("{", "%7B")]
    [InlineData("}", "%7D")]
    [InlineData("%", "%25")]
    public async Task CreateCheckpointAsync_EscapedSessionIds_DoNotShareKeysAsync(string sessionId, string escapedLookalike)
    {
        // Arrange
        List<string> keys = [];
        this.SetupScriptEvaluate((k, _) => keys.Add(k![1].ToString()));
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        await store.CreateCheckpointAsync(sessionId, JsonSerializer.SerializeToElement(1));
        await store.CreateCheckpointAsync(escapedLookalike, JsonSerializer.SerializeToElement(2));

        // Assert
        Assert.Equal(2, keys.Distinct().Count());
    }

    [Theory]
    [InlineData("foo", 12182)]
    [InlineData("123456789", 12739)]
    [InlineData("{user1000}.following", 3443)]
    [InlineData("foo{}{bar}", 8363)]
    [InlineData("foo{{bar}}zap", 4015)]
    public void RedisHashSlot_MatchesRedisClusterSpecification(string key, int expectedSlot)
    {
        // Act & Assert: reference values from the Redis Cluster specification and CLUSTER KEYSLOT.
        Assert.Equal(expectedSlot, RedisHashSlot.Calculate(key));
    }

    [Fact]
    public async Task CreateCheckpointAsync_WithoutParentOrTimeToLive_PassesEmptyParentAndZeroTimeToLiveAsync()
    {
        // Arrange
        RedisValue[]? values = null;
        this.SetupScriptEvaluate((_, v) => values = v);
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        await store.CreateCheckpointAsync("session-1", JsonSerializer.SerializeToElement("value"));

        // Assert
        Assert.Equal(string.Empty, values![2].ToString());
        Assert.Equal(0, (long)values[3]);
    }

    [Fact]
    public async Task CreateCheckpointAsync_ReturnsUniqueCheckpointIdsAsync()
    {
        // Arrange
        this.SetupScriptEvaluate((_, _) => { });
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        CheckpointInfo first = await store.CreateCheckpointAsync("session-1", JsonSerializer.SerializeToElement(1));
        CheckpointInfo second = await store.CreateCheckpointAsync("session-1", JsonSerializer.SerializeToElement(2));

        // Assert
        Assert.NotEqual(first.CheckpointId, second.CheckpointId);
    }

    #endregion

    #region RetrieveCheckpointAsync

    [Fact]
    public async Task RetrieveCheckpointAsync_NullKey_ThrowsAsync()
    {
        // Arrange
        RedisCheckpointStore store = new(this._connection.Object);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => store.RetrieveCheckpointAsync("session-1", null!).AsTask());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_ReturnsStoredJsonAsync()
    {
        // Arrange
        const string Json = """{"$type":"state","value":42}""";
        this._database
            .Setup(db => db.HashGetAsync((RedisKey)"checkpoints:{session-1}:data", (RedisValue)"checkpoint-1", It.IsAny<CommandFlags>()))
            .ReturnsAsync((RedisValue)Encoding.UTF8.GetBytes(Json));
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        JsonElement value = await store.RetrieveCheckpointAsync("session-1", new CheckpointInfo("session-1", "checkpoint-1"));

        // Assert
        Assert.Equal(Json, value.GetRawText());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_MissingCheckpoint_ThrowsKeyNotFoundExceptionAsync()
    {
        // Arrange
        this._database
            .Setup(db => db.HashGetAsync(It.IsAny<RedisKey>(), It.IsAny<RedisValue>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(RedisValue.Null);
        RedisCheckpointStore store = new(this._connection.Object);

        // Act & Assert
        await Assert.ThrowsAsync<KeyNotFoundException>(() =>
            store.RetrieveCheckpointAsync("session-1", new CheckpointInfo("session-1", "missing")).AsTask());
    }

    #endregion

    #region RetrieveIndexAsync

    [Fact]
    public async Task RetrieveIndexAsync_ReturnsCheckpointsInSortedSetOrderAsync()
    {
        // Arrange
        this.SetupIndex("checkpoints:{session-1}:index", "c", "a", "b");
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        IEnumerable<CheckpointInfo> index = await store.RetrieveIndexAsync("session-1");

        // Assert
        Assert.Equal(["c", "a", "b"], index.Select(c => c.CheckpointId));
        Assert.All(index, c => Assert.Equal("session-1", c.SessionId));
    }

    [Fact]
    public async Task RetrieveIndexAsync_WithParent_ReturnsOnlyDirectChildrenAsync()
    {
        // Arrange
        this.SetupIndex("checkpoints:{session-1}:index", "root", "child-1", "grandchild", "child-2");
        this._database
            .Setup(db => db.HashGetAsync((RedisKey)"checkpoints:{session-1}:parents", It.IsAny<RedisValue[]>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync([RedisValue.Null, "root", "child-1", "root"]);
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        IEnumerable<CheckpointInfo> children = await store.RetrieveIndexAsync("session-1", new CheckpointInfo("session-1", "root"));

        // Assert
        Assert.Equal(["child-1", "child-2"], children.Select(c => c.CheckpointId));
    }

    [Fact]
    public async Task RetrieveIndexAsync_UnknownSession_ReturnsEmptyAsync()
    {
        // Arrange
        this.SetupIndex("checkpoints:{unknown}:index");
        RedisCheckpointStore store = new(this._connection.Object);

        // Act
        IEnumerable<CheckpointInfo> index = await store.RetrieveIndexAsync("unknown", new CheckpointInfo("unknown", "parent"));

        // Assert
        Assert.Empty(index);
    }

    #endregion

    private void SetupScriptEvaluate(Action<RedisKey[]?, RedisValue[]?> callback) =>
        this._database
            .Setup(db => db.ScriptEvaluateAsync(It.IsAny<string>(), It.IsAny<RedisKey[]?>(), It.IsAny<RedisValue[]?>(), It.IsAny<CommandFlags>()))
            .Callback<string, RedisKey[]?, RedisValue[]?, CommandFlags>((_, keys, values, _) => callback(keys, values))
            .ReturnsAsync(RedisResult.Create(1));

    private void SetupIndex(string indexKey, params string[] checkpointIds) =>
        this._database
            .Setup(db => db.SortedSetRangeByRankAsync((RedisKey)indexKey, 0, -1, Order.Ascending, It.IsAny<CommandFlags>()))
            .ReturnsAsync(checkpointIds.Select(id => (RedisValue)id).ToArray());
}
