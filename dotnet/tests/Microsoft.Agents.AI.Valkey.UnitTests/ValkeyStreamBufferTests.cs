// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;
using Valkey.Glide;

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
        mockConnection.Setup(c => c.GetDatabase()).Returns(dbMock.Object);
        return mockConnection;
    }

    // --- Constructor tests ---

    [Fact]
    public void Constructor_WithConnection_SetsProperties()
    {
        // Arrange & Act
        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection().Object,
            new ValkeyStreamBufferOptions { KeyPrefix = "test_stream" });

        // Assert
        Assert.NotNull(buffer);
    }

    [Fact]
    public void Constructor_NullConnection_Throws()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyStreamBuffer(null!));
    }

    // --- AppendAsync tests ---

    [Fact]
    public async Task AppendAsync_ReturnsEntryIdAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.StreamAddAsync(
                It.IsAny<ValkeyKey>(),
                It.IsAny<NameValueEntry[]>(),
                It.IsAny<ValkeyValue?>(),
                It.IsAny<int?>(),
                It.IsAny<bool>(),
                It.IsAny<CommandFlags>()))
            .Returns(Task.FromResult<ValkeyValue>("1234567890-0"));

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            new ValkeyStreamBufferOptions { KeyPrefix = "test" });

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
                It.IsAny<ValkeyKey>(),
                It.IsAny<ValkeyValue?>(),
                It.IsAny<ValkeyValue?>(),
                It.IsAny<int?>(),
                It.IsAny<Order>(),
                It.IsAny<CommandFlags>()))
            .ReturnsAsync(entries);

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            new ValkeyStreamBufferOptions { KeyPrefix = "test" });

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
                It.IsAny<ValkeyKey>(),
                It.IsAny<ValkeyValue?>(),
                It.IsAny<ValkeyValue?>(),
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
            It.IsAny<ValkeyKey>(),
            (ValkeyValue)"(5-3",
            (ValkeyValue)"+",
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
                It.IsAny<ValkeyKey>(),
                It.IsAny<ValkeyValue?>(),
                It.IsAny<ValkeyValue?>(),
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
                It.IsAny<ValkeyKey>(),
                It.IsAny<ValkeyValue?>(),
                It.IsAny<ValkeyValue?>(),
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

    // --- AppendAsync with MaxLength tests ---

    [Fact]
    public async Task AppendAsync_WithMaxLength_PassesThroughToStreamAddAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.StreamAddAsync(
                It.IsAny<ValkeyKey>(),
                It.IsAny<NameValueEntry[]>(),
                It.IsAny<ValkeyValue?>(),
                100,
                true,
                It.IsAny<CommandFlags>()))
            .Returns(Task.FromResult<ValkeyValue>("1-0"));

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            new ValkeyStreamBufferOptions { MaxLength = 100 });

        var update = new AgentResponseUpdate(Extensions.AI.ChatRole.Assistant, "hello");

        // Act
        await buffer.AppendAsync("resp-1", update);

        // Assert — verify maxLength=100 and useApproximateMaxLength=true were passed
        dbMock.Verify(d => d.StreamAddAsync(
            It.IsAny<ValkeyKey>(),
            It.IsAny<NameValueEntry[]>(),
            It.IsAny<ValkeyValue?>(),
            100,
            true,
            It.IsAny<CommandFlags>()), Times.Once);
    }

    // --- GetEntryCountAsync tests ---

    [Fact]
    public async Task GetEntryCountAsync_ReturnsStreamLengthAsync()
    {
        // Arrange
        var dbMock = new Mock<IDatabase>();
        dbMock.Setup(d => d.StreamLengthAsync(It.IsAny<ValkeyKey>()))
            .ReturnsAsync(42);

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            new ValkeyStreamBufferOptions { KeyPrefix = "test" });

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
        dbMock.Setup(d => d.KeyDeleteAsync(It.IsAny<ValkeyKey>(), It.IsAny<CommandFlags>()))
            .ReturnsAsync(true);

        var buffer = new ValkeyStreamBuffer(
            CreateMockConnection(dbMock).Object,
            new ValkeyStreamBufferOptions { KeyPrefix = "test" });

        // Act
        var deleted = await buffer.DeleteStreamAsync("resp-1");

        // Assert
        Assert.True(deleted);
        dbMock.Verify(d => d.KeyDeleteAsync((ValkeyKey)"test:resp-1", It.IsAny<CommandFlags>()), Times.Once);
    }
}
