// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="MessageFilteringAIContextProvider"/> class.
/// </summary>
public sealed class MessageFilteringAIContextProviderTests
{
    [Fact]
    public void Constructor_WithNullInnerStore_ThrowsArgumentNullException()
    {
        // Arrange, Act & Assert
        Assert.Throws<ArgumentNullException>(() => new MessageFilteringAIContextProvider(null!));
    }

    [Fact]
    public void Constructor_WithOnlyInnerStore_Throws()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new MessageFilteringAIContextProvider(innerProviderMock.Object));
    }

    [Fact]
    public void Constructor_WithAllParameters_CreatesInstance()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();

        AIContext InvokingFilter(AIContext ctx) => ctx;
        AIContextProvider.InvokedContext InvokedFilter(AIContextProvider.InvokedContext ctx) => ctx;

        // Act
        var filter = new MessageFilteringAIContextProvider(innerProviderMock.Object, InvokingFilter, InvokedFilter);

        // Assert
        Assert.NotNull(filter);
    }

    [Fact]
    public async Task InvokingAsync_WithNoOpFilters_ReturnsInnerStoreMessagesAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();
        var expectedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerProviderMock
            .Setup(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext { Messages = expectedMessages });

        var filter = new MessageFilteringAIContextProvider(innerProviderMock.Object, x => x, x => x);

        // Act
        var aiContext = await filter.InvokingAsync(context, CancellationToken.None);
        var result = aiContext.Messages?.ToList() ?? [];

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("Hello", result[0].Text);
        Assert.Equal("Hi there!", result[1].Text);
        innerProviderMock.Verify(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InvokingAsync_WithInvokingFilter_AppliesFilterAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!"),
            new(ChatRole.User, "How are you?")
        };
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerProviderMock
            .Setup(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext { Messages = innerMessages });

        // Filter to only user messages
        AIContext InvokingFilter(AIContext ctx)
        {
            var filteredMessages = ctx.Messages?.Where(m => m.Role == ChatRole.User).ToList();
            return new AIContext { Messages = filteredMessages, Instructions = ctx.Instructions, Tools = ctx.Tools };
        }

        var filter = new MessageFilteringAIContextProvider(innerProviderMock.Object, InvokingFilter);

        // Act
        var aiContext = await filter.InvokingAsync(context, CancellationToken.None);
        var result = aiContext.Messages?.ToList() ?? [];

        // Assert
        Assert.Equal(2, result.Count);
        Assert.All(result, msg => Assert.Equal(ChatRole.User, msg.Role));
        innerProviderMock.Verify(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InvokingAsync_WithInvokingFilter_CanModifyMessagesAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new AIContextProvider.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerProviderMock
            .Setup(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext { Messages = innerMessages });

        // Filter that transforms messages
        AIContext InvokingFilter(AIContext ctx)
        {
            var transformedMessages = ctx.Messages?.Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}")).ToList();
            return new AIContext { Messages = transformedMessages, Instructions = ctx.Instructions, Tools = ctx.Tools };
        }

        var filter = new MessageFilteringAIContextProvider(innerProviderMock.Object, InvokingFilter);

        // Act
        var aiContext = await filter.InvokingAsync(context, CancellationToken.None);
        var result = aiContext.Messages?.ToList() ?? [];

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("[FILTERED] Hello", result[0].Text);
        Assert.Equal("[FILTERED] Hi there!", result[1].Text);
    }

    [Fact]
    public async Task InvokedAsync_WithInvokedFilter_AppliesFilterAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var aiContextProviderMessages = new List<ChatMessage> { new(ChatRole.System, "System") };
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response") };
        var context = new AIContextProvider.InvokedContext(requestMessages, aiContextProviderMessages)
        {
            ResponseMessages = responseMessages
        };

        AIContextProvider.InvokedContext? capturedContext = null;
        innerProviderMock
            .Setup(s => s.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Callback<AIContextProvider.InvokedContext, CancellationToken>((ctx, ct) => capturedContext = ctx)
            .Returns(default(ValueTask));

        // Filter that modifies the context
        AIContextProvider.InvokedContext InvokedFilter(AIContextProvider.InvokedContext ctx)
        {
            var modifiedRequestMessages = ctx.RequestMessages.Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}")).ToList();
            return new AIContextProvider.InvokedContext(modifiedRequestMessages, ctx.AIContextProviderMessages)
            {
                ResponseMessages = ctx.ResponseMessages,
                ChatHistoryMessages = ctx.ChatHistoryMessages,
                InvokeException = ctx.InvokeException
            };
        }

        var filter = new MessageFilteringAIContextProvider(innerProviderMock.Object, invokedContextFilter: InvokedFilter);

        // Act
        await filter.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Single(capturedContext.RequestMessages);
        Assert.Equal("[FILTERED] Hello", capturedContext.RequestMessages.First().Text);
        innerProviderMock.Verify(s => s.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public void Serialize_DelegatesToInnerStore()
    {
        // Arrange
        var innerProviderMock = new Mock<AIContextProvider>();
        var expectedJson = JsonSerializer.SerializeToElement("data", TestJsonSerializerContext.Default.String);

        innerProviderMock
            .Setup(s => s.Serialize(It.IsAny<JsonSerializerOptions>()))
            .Returns(expectedJson);

        var filter = new MessageFilteringAIContextProvider(innerProviderMock.Object, x => x, x => x);

        // Act
        var result = filter.Serialize();

        // Assert
        Assert.Equal(expectedJson.GetRawText(), result.GetRawText());
        innerProviderMock.Verify(s => s.Serialize(null), Times.Once);
    }
}
