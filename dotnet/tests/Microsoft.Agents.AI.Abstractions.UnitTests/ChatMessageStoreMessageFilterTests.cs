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
/// Contains tests for the <see cref="ChatMessageStoreMessageFilter"/> class.
/// </summary>
public sealed class ChatMessageStoreMessageFilterTests
{
    [Fact]
    public void Constructor_WithNullInnerStore_ThrowsArgumentNullException()
    {
        // Arrange, Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatMessageStoreMessageFilter(null!));
    }

    [Fact]
    public void Constructor_WithOnlyInnerStore_Throws()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new ChatMessageStoreMessageFilter(innerStoreMock.Object));
    }

    [Fact]
    public void Constructor_WithAllParameters_CreatesInstance()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();

        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) => msgs;
        ChatMessageStore.InvokedContext InvokedFilter(ChatMessageStore.InvokedContext ctx) => ctx;

        // Act
        var filter = new ChatMessageStoreMessageFilter(innerStoreMock.Object, InvokingFilter, InvokedFilter);

        // Assert
        Assert.NotNull(filter);
    }

    [Fact]
    public async Task InvokingAsync_WithNoOpFilters_ReturnsInnerStoreMessagesAsync()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();
        var expectedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new ChatMessageStore.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerStoreMock
            .Setup(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedMessages);

        var filter = new ChatMessageStoreMessageFilter(innerStoreMock.Object, x => x, x => x);

        // Act
        var result = (await filter.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("Hello", result[0].Text);
        Assert.Equal("Hi there!", result[1].Text);
        innerStoreMock.Verify(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InvokingAsync_WithInvokingFilter_AppliesFilterAsync()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!"),
            new(ChatRole.User, "How are you?")
        };
        var context = new ChatMessageStore.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerStoreMock
            .Setup(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerMessages);

        // Filter to only user messages
        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) => msgs.Where(m => m.Role == ChatRole.User);

        var filter = new ChatMessageStoreMessageFilter(innerStoreMock.Object, InvokingFilter);

        // Act
        var result = (await filter.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.All(result, msg => Assert.Equal(ChatRole.User, msg.Role));
        innerStoreMock.Verify(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task InvokingAsync_WithInvokingFilter_CanModifyMessagesAsync()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new ChatMessageStore.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerStoreMock
            .Setup(s => s.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerMessages);

        // Filter that transforms messages
        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) =>
            msgs.Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}"));

        var filter = new ChatMessageStoreMessageFilter(innerStoreMock.Object, InvokingFilter);

        // Act
        var result = (await filter.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("[FILTERED] Hello", result[0].Text);
        Assert.Equal("[FILTERED] Hi there!", result[1].Text);
    }

    [Fact]
    public async Task InvokedAsync_WithInvokedFilter_AppliesFilterAsync()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var chatMessageStoreMessages = new List<ChatMessage> { new(ChatRole.System, "System") };
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response") };
        var context = new ChatMessageStore.InvokedContext(requestMessages, chatMessageStoreMessages)
        {
            ResponseMessages = responseMessages
        };

        ChatMessageStore.InvokedContext? capturedContext = null;
        innerStoreMock
            .Setup(s => s.InvokedAsync(It.IsAny<ChatMessageStore.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Callback<ChatMessageStore.InvokedContext, CancellationToken>((ctx, ct) => capturedContext = ctx)
            .Returns(default(ValueTask));

        // Filter that modifies the context
        ChatMessageStore.InvokedContext InvokedFilter(ChatMessageStore.InvokedContext ctx)
        {
            var modifiedRequestMessages = ctx.RequestMessages.Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}")).ToList();
            return new ChatMessageStore.InvokedContext(modifiedRequestMessages, ctx.ChatMessageStoreMessages)
            {
                ResponseMessages = ctx.ResponseMessages,
                AIContextProviderMessages = ctx.AIContextProviderMessages,
                InvokeException = ctx.InvokeException
            };
        }

        var filter = new ChatMessageStoreMessageFilter(innerStoreMock.Object, invokedMessagesFilter: InvokedFilter);

        // Act
        await filter.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Single(capturedContext.RequestMessages);
        Assert.Equal("[FILTERED] Hello", capturedContext.RequestMessages.First().Text);
        innerStoreMock.Verify(s => s.InvokedAsync(It.IsAny<ChatMessageStore.InvokedContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public void Serialize_DelegatesToInnerStore()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();
        var expectedJson = JsonSerializer.SerializeToElement("data", TestJsonSerializerContext.Default.String);

        innerStoreMock
            .Setup(s => s.Serialize(It.IsAny<JsonSerializerOptions>()))
            .Returns(expectedJson);

        var filter = new ChatMessageStoreMessageFilter(innerStoreMock.Object, x => x, x => x);

        // Act
        var result = filter.Serialize();

        // Assert
        Assert.Equal(expectedJson.GetRawText(), result.GetRawText());
        innerStoreMock.Verify(s => s.Serialize(null), Times.Once);
    }
}
