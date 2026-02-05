// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatHistoryProviderExtensions"/> class.
/// </summary>
public sealed class ChatHistoryProviderExtensionsTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    [Fact]
    public void WithMessageFilters_ReturnsChatHistoryProviderMessageFilter()
    {
        // Arrange
        Mock<ChatHistoryProvider> providerMock = new();

        // Act
        ChatHistoryProvider result = providerMock.Object.WithMessageFilters(
            invokingMessagesFilter: msgs => msgs,
            invokedMessagesFilter: ctx => ctx);

        // Assert
        Assert.IsType<ChatHistoryProviderMessageFilter>(result);
    }

    [Fact]
    public async Task WithMessageFilters_InvokingFilter_IsAppliedAsync()
    {
        // Arrange
        Mock<ChatHistoryProvider> providerMock = new();
        List<ChatMessage> innerMessages = [new(ChatRole.User, "Hello"), new(ChatRole.Assistant, "Hi")];
        ChatHistoryProvider.InvokingContext context = new(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Test")]);

        providerMock
            .Setup(p => p.InvokingAsync(context, It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerMessages);

        ChatHistoryProvider filtered = providerMock.Object.WithMessageFilters(
            invokingMessagesFilter: msgs => msgs.Where(m => m.Role == ChatRole.User));

        // Act
        List<ChatMessage> result = (await filtered.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal(ChatRole.User, result[0].Role);
    }

    [Fact]
    public async Task WithMessageFilters_InvokedFilter_IsAppliedAsync()
    {
        // Arrange
        Mock<ChatHistoryProvider> providerMock = new();
        List<ChatMessage> requestMessages = [new(ChatRole.User, "Hello")];
        List<ChatMessage> chatHistoryProviderMessages = [new(ChatRole.System, "System")];
        ChatHistoryProvider.InvokedContext context = new(s_mockAgent, s_mockSession, requestMessages, chatHistoryProviderMessages)
        {
            ResponseMessages = [new ChatMessage(ChatRole.Assistant, "Response")]
        };

        ChatHistoryProvider.InvokedContext? capturedContext = null;
        providerMock
            .Setup(p => p.InvokedAsync(It.IsAny<ChatHistoryProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Callback<ChatHistoryProvider.InvokedContext, CancellationToken>((ctx, _) => capturedContext = ctx)
            .Returns(default(ValueTask));

        ChatHistoryProvider filtered = providerMock.Object.WithMessageFilters(
            invokedMessagesFilter: ctx =>
            {
                ctx.ResponseMessages = null;
                return ctx;
            });

        // Act
        await filtered.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Null(capturedContext.ResponseMessages);
    }

    [Fact]
    public void WithAIContextProviderMessageRemoval_ReturnsChatHistoryProviderMessageFilter()
    {
        // Arrange
        Mock<ChatHistoryProvider> providerMock = new();

        // Act
        ChatHistoryProvider result = providerMock.Object.WithAIContextProviderMessageRemoval();

        // Assert
        Assert.IsType<ChatHistoryProviderMessageFilter>(result);
    }

    [Fact]
    public async Task WithAIContextProviderMessageRemoval_RemovesAIContextProviderMessagesAsync()
    {
        // Arrange
        Mock<ChatHistoryProvider> providerMock = new();
        List<ChatMessage> requestMessages = [new(ChatRole.User, "Hello")];
        List<ChatMessage> chatHistoryProviderMessages = [new(ChatRole.System, "System")];
        List<ChatMessage> aiContextProviderMessages = [new(ChatRole.System, "Context")];
        ChatHistoryProvider.InvokedContext context = new(s_mockAgent, s_mockSession, requestMessages, chatHistoryProviderMessages)
        {
            AIContextProviderMessages = aiContextProviderMessages
        };

        ChatHistoryProvider.InvokedContext? capturedContext = null;
        providerMock
            .Setup(p => p.InvokedAsync(It.IsAny<ChatHistoryProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Callback<ChatHistoryProvider.InvokedContext, CancellationToken>((ctx, _) => capturedContext = ctx)
            .Returns(default(ValueTask));

        ChatHistoryProvider filtered = providerMock.Object.WithAIContextProviderMessageRemoval();

        // Act
        await filtered.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Null(capturedContext.AIContextProviderMessages);
    }
}
