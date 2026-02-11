// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

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
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
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
        List<ChatMessage> requestMessages =
        [
            new(ChatRole.System, "System") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "TestSource") } } },
            new(ChatRole.User, "Hello")
        ];
        ChatHistoryProvider.InvokedContext context = new(s_mockAgent, s_mockSession, requestMessages)
        {
            ResponseMessages = [new ChatMessage(ChatRole.Assistant, "Response")]
        };

        ChatHistoryProvider.InvokedContext? capturedContext = null;
        providerMock
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
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
        List<ChatMessage> requestMessages =
        [
            new(ChatRole.System, "System") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "TestSource") } } },
            new(ChatRole.User, "Hello"),
            new(ChatRole.System, "Context") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "TestContextSource") } } }
        ];
        ChatHistoryProvider.InvokedContext context = new(s_mockAgent, s_mockSession, requestMessages);

        ChatHistoryProvider.InvokedContext? capturedContext = null;
        providerMock
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<ChatHistoryProvider.InvokedContext, CancellationToken>((ctx, _) => capturedContext = ctx)
            .Returns(default(ValueTask));

        ChatHistoryProvider filtered = providerMock.Object.WithAIContextProviderMessageRemoval();

        // Act
        await filtered.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Equal(2, capturedContext.RequestMessages.Count());
        Assert.Contains("System", capturedContext.RequestMessages.Select(x => x.Text));
        Assert.Contains("Hello", capturedContext.RequestMessages.Select(x => x.Text));
    }
}
