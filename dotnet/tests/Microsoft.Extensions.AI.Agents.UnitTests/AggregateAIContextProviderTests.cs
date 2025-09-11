// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests;

public class AggregateAIContextProviderTests
{
    [Fact]
    public async Task MessagesAddingAsync_DelegatesToAllProvidersAsync()
    {
        // Arrange
        var aggregate = new AggregateAIContextProvider();

        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();

        mockProvider1.Setup(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();
        mockProvider2.Setup(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();

        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        await aggregate.MessagesAddingAsync(new List<ChatMessage>());

        // Assert
        mockProvider1.Verify(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider2.Verify(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InvokingAsync_AggregatesContextsFromProvidersAsync()
    {
        // Arrange
        var context1 = new AIContext
        {
            Instructions = "Instruction1",
            Messages = new List<ChatMessage> { new(ChatRole.System, "SystemMessage1") },
            Tools = [AIFunctionFactory.Create(() => { }, "AIFunction1")]
        };
        var context2 = new AIContext
        {
            Instructions = "Instruction2",
            Messages = new List<ChatMessage> { new(ChatRole.User, "UserMessage2") },
            Tools = [AIFunctionFactory.Create(() => { }, "AIFunction2")]
        };

        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();

        mockProvider1.Setup(p => p.InvokingAsync(It.Is<IEnumerable<ChatMessage>>(x => x.First().Text == "Hello"), It.IsAny<CancellationToken>()))
            .ReturnsAsync(context1);
        mockProvider2.Setup(p => p.InvokingAsync(It.Is<IEnumerable<ChatMessage>>(x => x.First().Text == "Hello"), It.IsAny<CancellationToken>()))
            .ReturnsAsync(context2);

        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        var result = await aggregate.InvokingAsync(new List<ChatMessage>() { new(ChatRole.User, "Hello") });

        // Assert
        Assert.Equal($"Instruction1{Environment.NewLine}Instruction2", result.Instructions);
        Assert.Equal(2, result.Messages?.Count);
        Assert.Equal("SystemMessage1", result.Messages?[0].Text);
        Assert.Equal("UserMessage2", result.Messages?[1].Text);
        Assert.Equal(2, result.Tools?.Count);
        Assert.Equal("AIFunction1", result.Tools?[0].Name);
        Assert.Equal("AIFunction2", result.Tools?[1].Name);
    }

    [Fact]
    public async Task InvokingAsync_WithNoProviders_ReturnsEmptyContextAsync()
    {
        // Arrange
        var aggregate = new AggregateAIContextProvider();

        // Act
        var result = await aggregate.InvokingAsync(new List<ChatMessage>());

        // Assert
        Assert.Null(result.Instructions);
        Assert.Null(result.Messages);
        Assert.Null(result.Tools);
    }

    [Fact]
    public async Task SerializeAsync_Serializes_SubProviderContextAsync()
    {
        // Arrange
        var provider1StateElement = JsonSerializer.SerializeToElement("CP1", TestJsonSerializerContext.Default.String);
        var provider2StateElement = JsonSerializer.SerializeToElement("CP2", TestJsonSerializerContext.Default.String);

        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();
        mockProvider1.Setup(p => p.SerializeAsync(It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(provider1StateElement);
        mockProvider2.Setup(p => p.SerializeAsync(It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(provider2StateElement);

        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        var result = await aggregate.SerializeAsync();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(JsonValueKind.Array, result?.ValueKind);
        Assert.Equal(2, result?.GetArrayLength());
        Assert.Equal("CP1", result?.EnumerateArray().ElementAt(0).GetString());
        Assert.Equal("CP2", result?.EnumerateArray().ElementAt(1).GetString());
    }

    [Fact]
    public async Task SerializeAsync_ReturnsNull_WhenEmptyAsync()
    {
        // Arrange
        var aggregate = new AggregateAIContextProvider();

        // Act
        var result = await aggregate.SerializeAsync();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task Deserialize_Deserializes_SubProviderContextAsync()
    {
        // Arrange
        var aggregateState = JsonSerializer.Deserialize("""
            ["CP1", "CP2"]
            """, TestJsonSerializerContext.Default.JsonElement);

        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();
        mockProvider1.Setup(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP1"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();
        mockProvider2.Setup(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP2"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();

        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        await aggregate.DeserializeAsync(aggregateState);

        // Assert
        mockProvider1.Verify(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP1"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider2.Verify(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP2"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task Deserialize_Deserializes_PartialStateAsync()
    {
        // Arrange
        var aggregateState = JsonSerializer.Deserialize("""
            ["CP1", "CP2"]
            """, TestJsonSerializerContext.Default.JsonElement);

        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();
        var mockProvider3 = new Mock<AIContextProvider>();
        mockProvider1.Setup(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP1"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();
        mockProvider2.Setup(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP2"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();
        mockProvider3.Setup(p => p.DeserializeAsync(It.IsAny<JsonElement>(), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();

        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);
        aggregate.Add(mockProvider3.Object);

        // Act
        await aggregate.DeserializeAsync(aggregateState);

        // Assert
        mockProvider1.Verify(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP1"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider2.Verify(p => p.DeserializeAsync(It.Is<JsonElement>(e => e.GetString() == "CP2"), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider3.Verify(p => p.DeserializeAsync(It.IsAny<JsonElement>(), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task Deserialize_Deserializes_NullStateAsync()
    {
        // Arrange
        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();
        mockProvider1.Setup(p => p.DeserializeAsync(It.IsAny<JsonElement>(), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();
        mockProvider1.Setup(p => p.DeserializeAsync(It.IsAny<JsonElement>(), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask))
            .Verifiable();

        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        await aggregate.DeserializeAsync(default);

        // Assert
        mockProvider1.Verify(p => p.DeserializeAsync(It.IsAny<JsonElement>(), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Never);
        mockProvider2.Verify(p => p.DeserializeAsync(It.IsAny<JsonElement>(), It.IsAny<JsonSerializerOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public void IList_Operations_WorkAsExpected()
    {
        // Arrange
        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();
        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        var providerAtIndex0 = aggregate[0];
        var containsProvider1 = aggregate.Contains(mockProvider1.Object);
        var indexProvider2 = aggregate.IndexOf(mockProvider2.Object);
        aggregate.RemoveAt(0);
        var countAfterRemoveAt = aggregate.Count;
        aggregate.Insert(0, mockProvider1.Object);
        var count = aggregate.Count;
        aggregate.Remove(mockProvider1.Object);
        var countAfterRemove = aggregate.Count;
        aggregate.Clear();
        var countAfterClear = aggregate.Count;

        // Assert
        Assert.Equal(2, count);
        Assert.Equal(1, countAfterRemove);
        Assert.True(containsProvider1);
        Assert.Equal(1, indexProvider2);
        Assert.Equal(1, countAfterRemoveAt);
        Assert.Equal(1, countAfterRemove);
        Assert.Equal(0, countAfterClear);
        Assert.False(aggregate.IsReadOnly);
        Assert.Same(mockProvider1.Object, providerAtIndex0);
    }
}
