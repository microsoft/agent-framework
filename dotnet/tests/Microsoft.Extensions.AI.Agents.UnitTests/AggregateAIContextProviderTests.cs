// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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

        mockProvider1.Setup(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask)
            .Verifiable();
        mockProvider2.Setup(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask)
            .Verifiable();

        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        await aggregate.MessagesAddingAsync(new List<ChatMessage>(), null);

        // Assert
        mockProvider1.Verify(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<string>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider2.Verify(p => p.MessagesAddingAsync(It.IsAny<IReadOnlyCollection<ChatMessage>>(), It.IsAny<string>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task ModelInvokingAsync_AggregatesContextsFromProvidersAsync()
    {
        // Arrange
        var context1 = new AIContext
        {
            Instructions = "Instruction1",
            Messages = new List<ChatMessage> { new(ChatRole.System, "SystemMessage1") },
            AIFunctions = new List<AIFunction> { AIFunctionFactory.Create(() => { }, "AIFunction1") }
        };
        var context2 = new AIContext
        {
            Instructions = "Instruction2",
            Messages = new List<ChatMessage> { new(ChatRole.User, "UserMessage2") },
            AIFunctions = new List<AIFunction> { AIFunctionFactory.Create(() => { }, "AIFunction2") }
        };

        var mockProvider1 = new Mock<AIContextProvider>();
        var mockProvider2 = new Mock<AIContextProvider>();

        mockProvider1.Setup(p => p.ModelInvokingAsync(It.Is<IEnumerable<ChatMessage>>(x => x.First().Text == "Hello"), "thread-1234", It.IsAny<CancellationToken>()))
            .ReturnsAsync(context1);
        mockProvider2.Setup(p => p.ModelInvokingAsync(It.Is<IEnumerable<ChatMessage>>(x => x.First().Text == "Hello"), "thread-1234", It.IsAny<CancellationToken>()))
            .ReturnsAsync(context2);

        var aggregate = new AggregateAIContextProvider();
        aggregate.Add(mockProvider1.Object);
        aggregate.Add(mockProvider2.Object);

        // Act
        var result = await aggregate.ModelInvokingAsync(new List<ChatMessage>() { new(ChatRole.User, "Hello") }, "thread-1234");

        // Assert
        Assert.Equal($"Instruction1{Environment.NewLine}Instruction2", result.Instructions);
        Assert.Equal(2, result.Messages?.Count);
        Assert.Equal("SystemMessage1", result.Messages?[0].Text);
        Assert.Equal("UserMessage2", result.Messages?[1].Text);
        Assert.Equal(2, result.AIFunctions?.Count);
        Assert.Equal("AIFunction1", result.AIFunctions?[0].Name);
        Assert.Equal("AIFunction2", result.AIFunctions?[1].Name);
    }

    [Fact]
    public async Task ModelInvokingAsync_WithNoProviders_ReturnsEmptyContextAsync()
    {
        // Arrange
        var aggregate = new AggregateAIContextProvider();

        // Act
        var result = await aggregate.ModelInvokingAsync(new List<ChatMessage>(), null);

        // Assert
        Assert.Null(result.Instructions);
        Assert.Null(result.Messages);
        Assert.Null(result.AIFunctions);
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
