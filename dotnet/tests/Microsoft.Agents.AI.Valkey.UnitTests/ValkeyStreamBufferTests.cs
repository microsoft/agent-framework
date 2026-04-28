// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey.UnitTests;

/// <summary>
/// Unit tests for <see cref="ValkeyStreamBuffer"/>.
/// </summary>
public sealed class ValkeyStreamBufferTests
{
    private static Mock<IConnectionMultiplexer> CreateMockConnection(Mock<IDatabase>? dbMock = null)
    {
        var mockConnection = new Mock<IConnectionMultiplexer>();
        dbMock ??= new Mock<IDatabase>();
        mockConnection.Setup(c => c.GetDatabase(It.IsAny<int>(), It.IsAny<object>())).Returns(dbMock.Object);
        return mockConnection;
    }

    // --- Constructor tests ---

    [Fact]
    public void Constructor_WithConnection_SetsProperties()
    {
        // Arrange & Act
        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection().Object,
            keyPrefix: "test_stream");

        // Assert
        Assert.NotNull(buffer);
        Assert.Null(buffer.MaxLength);
    }

    [Fact]
    public void Constructor_NullConnection_Throws()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyStreamBuffer((IConnectionMultiplexer)null!));
    }

    [Fact]
    public void MaxLength_CanBeSet()
    {
        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection().Object)
        {
            MaxLength = 500
        };

        Assert.Equal(500, buffer.MaxLength);
    }

    // --- AppendAsync tests ---

    [Fact]
    public async Task AppendAsync_ReturnsEntryIdAsync()
    {
        // Arrange — StreamAddAsync is on IDatabaseAsync which IDatabase extends.
        // We need to mock the exact overload: (RedisKey, NameValueEntry[], RedisValue?, int?, bool, CommandFlags)
        var dbMock = new Mock<IDatabase>();
        dbMock.As<IDatabaseAsync>()
            .Setup(d => d.StreamAddAsync(
                It.IsAny<RedisKey>(),
                It.IsAny<NameValueEntry[]>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<long?>(),
                It.IsAny<bool>(),
                It.IsAny<long?>(),
                It.IsAny<StreamTrimMode>(),
                It.IsAny<CommandFlags>()))
            .Returns(Task.FromResult<RedisValue>("1234567890-0"));

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            keyPrefix: "test");

        var update = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "hello");

        // Act
        var entryId = await buffer.AppendAsync("resp-1", update);

        // Assert
        Assert.Equal("1234567890-0", entryId);
    }

    [Fact]
    public async Task AppendAsync_NullResponseId_ThrowsAsync()
    {
        var buffer = new ValkeyStreamBuffer(CreateMockConnection().Object);
        var update = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "hello");

        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            buffer.AppendAsync(null!, update));
    }

    [Fact]
    public async Task AppendAsync_NullUpdate_ThrowsAsync()
    {
        var buffer = new ValkeyStreamBuffer(CreateMockConnection().Object);

        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            buffer.AppendAsync("resp-1", null!));
    }

    [Fact]
    public async Task AppendAsync_CancellationToken_ThrowsAsync()
    {
        var buffer = new ValkeyStreamBuffer(CreateMockConnection().Object);
        var cts = new CancellationTokenSource();
        cts.Cancel();

        var update = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "hello");

        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            buffer.AppendAsync("resp-1", update, cts.Token));
    }

    // --- ReadAsync tests ---

    [Fact]
    public async Task ReadAsync_ReturnsDeserializedEntriesAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        var update1 = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "chunk1");
        var update2 = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "chunk2");

        var entries = new StreamEntry[]
        {
            new("1-0", [new NameValueEntry("content", System.Text.Json.JsonSerializer.Serialize(update1))]),
            new("2-0", [new NameValueEntry("content", System.Text.Json.JsonSerializer.Serialize(update2))]),
        };

        dbMock.Setup(d => d.StreamRangeAsync(
                It.IsAny<RedisKey>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<int?>(),
                It.IsAny<Order>(),
                It.IsAny<CommandFlags>()))
            .ReturnsAsync(entries);

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            keyPrefix: "test");

        // Act
        var results = await buffer.ReadAsync("resp-1").ToListAsync();

        // Assert
        Assert.Equal(2, results.Count);
        Assert.Equal("1-0", results[0].EntryId);
        Assert.Equal("chunk1", results[0].Update.Text);
        Assert.Equal("2-0", results[1].EntryId);
        Assert.Equal("chunk2", results[1].Update.Text);
    }

    [Fact]
    public async Task ReadAsync_WithAfterEntryId_UsesExclusivePrefixAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.StreamRangeAsync(
                It.IsAny<RedisKey>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<int?>(),
                It.IsAny<Order>(),
                It.IsAny<CommandFlags>()))
            .ReturnsAsync([]);

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object);

        // Act — read after entry "5-3" should use "(5-3" as exclusive minId
        await buffer.ReadAsync("resp-1", afterEntryId: "5-3").ToListAsync();

        // Assert — Valkey's ( prefix means exclusive range start
        dbMock.Verify(d => d.StreamRangeAsync(
            It.IsAny<RedisKey>(),
            (RedisValue)"(5-3",
            (RedisValue)"+",
            It.IsAny<int?>(),
            It.IsAny<Order>(),
            It.IsAny<CommandFlags>()), Times.Once);
    }

    [Fact]
    public async Task ReadAsync_EmptyStream_ReturnsEmptyAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.StreamRangeAsync(
                It.IsAny<RedisKey>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<int?>(),
                It.IsAny<Order>(),
                It.IsAny<CommandFlags>()))
            .ReturnsAsync([]);

        var buffer = new ValkeyStreamBuffer(CreateMockConnection(dbMock).Object);

        // Act
        var results = await buffer.ReadAsync("resp-1").ToListAsync();

        // Assert
        Assert.Empty(results);
    }

    [Fact]
    public async Task ReadAsync_MalformedEntry_SkipsItAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        var entries = new StreamEntry[]
        {
            new("1-0", [new NameValueEntry("content", "not valid json")]),
            new("2-0", [new NameValueEntry("content", System.Text.Json.JsonSerializer.Serialize(
                new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "valid")))]),
        };

        dbMock.Setup(d => d.StreamRangeAsync(
                It.IsAny<RedisKey>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<RedisValue?>(),
                It.IsAny<int?>(),
                It.IsAny<Order>(),
                It.IsAny<CommandFlags>()))
            .ReturnsAsync(entries);

        var buffer = new ValkeyStreamBuffer(CreateMockConnection(dbMock).Object);

        // Act
        var results = await buffer.ReadAsync("resp-1").ToListAsync();

        // Assert — only the valid entry
        Assert.Single(results);
        Assert.Equal("valid", results[0].Update.Text);
    }

    // --- GetEntryCountAsync tests ---

    [Fact]
    public async Task AppendAsync_WithMaxLength_PassesThroughToStreamAddAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.As<IDatabaseAsync>()
            .Setup(d => d.StreamAddAsync(
                It.IsAny<RedisKey>(),
                It.IsAny<NameValueEntry[]>(),
                It.IsAny<RedisValue?>(),
                100L,
                true,
                It.IsAny<long?>(),
                It.IsAny<StreamTrimMode>(),
                It.IsAny<CommandFlags>()))
            .Returns(Task.FromResult<RedisValue>("1-0"));

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object)
        {
            MaxLength = 100
        };

        var update = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "hello");

        // Act
        await buffer.AppendAsync("resp-1", update);

        // Assert — verify maxLength=100 and useApproximateMaxLength=true were passed
        dbMock.As<IDatabaseAsync>().Verify(d => d.StreamAddAsync(
            It.IsAny<RedisKey>(),
            It.IsAny<NameValueEntry[]>(),
            It.IsAny<RedisValue?>(),
            100L,
            true,
            It.IsAny<long?>(),
            It.IsAny<StreamTrimMode>(),
            It.IsAny<CommandFlags>()), Times.Once);
    }

    [Fact]
    public async Task GetEntryCountAsync_ReturnsStreamLengthAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.StreamLengthAsync(It.IsAny<RedisKey>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(42);

        var buffer = new ValkeyStreamBuffer(CreateMockConnection(dbMock).Object, keyPrefix: "test");

        // Act
        var count = await buffer.GetEntryCountAsync("resp-1");

        // Assert
        Assert.Equal(42, count);
    }

    // --- DeleteStreamAsync tests ---

    [Fact]
    public async Task DeleteStreamAsync_DeletesKeyAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.KeyDeleteAsync(It.IsAny<RedisKey>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(true);

        var buffer = new ValkeyStreamBuffer(CreateMockConnection(dbMock).Object, keyPrefix: "test");

        // Act
        var deleted = await buffer.DeleteStreamAsync("resp-1");

        // Assert
        Assert.True(deleted);
        dbMock.Verify(d => d.KeyDeleteAsync((RedisKey)"test:resp-1", It.IsAny<CommandFlags>()), Times.Once);
    }

    // --- Dispose tests ---

    [Fact]
    public async Task DisposeAsync_CalledTwice_NoOpAsync()
    {
        var buffer = new ValkeyStreamBuffer(CreateMockConnection().Object);

        await buffer.DisposeAsync();
        await buffer.DisposeAsync();
    }

    [Fact]
    public async Task AppendAsync_AfterDispose_ThrowsAsync()
    {
        var buffer = new ValkeyStreamBuffer(CreateMockConnection().Object);
        await buffer.DisposeAsync();

        var update = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "hello");

        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            buffer.AppendAsync("resp-1", update));
    }

    [Fact]
    public async Task ReadAsync_AfterDispose_ThrowsAsync()
    {
        var buffer = new ValkeyStreamBuffer(CreateMockConnection().Object);
        await buffer.DisposeAsync();

        await Assert.ThrowsAsync<ObjectDisposedException>(async () =>
            await buffer.ReadAsync("resp-1").ToListAsync());
    }
}
