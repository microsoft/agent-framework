// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatHistoryProviderMessageFilter"/> class.
/// </summary>
public sealed class ChatHistoryProviderMessageFilterTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    [Fact]
    public void Constructor_WithNullInnerProvider_ThrowsArgumentNullException()
    {
        // Arrange, Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatHistoryProviderMessageFilter(null!));
    }

    [Fact]
    public void Constructor_WithOnlyInnerProvider_Throws()
    {
        // Arrange
        var innerProviderMock = new Mock<ChatHistoryProvider>();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new ChatHistoryProviderMessageFilter(innerProviderMock.Object));
    }

    [Fact]
    public void Constructor_WithAllParameters_CreatesInstance()
    {
        // Arrange
        var innerProviderMock = new Mock<ChatHistoryProvider>();

        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) => msgs;
        ChatHistoryProvider.InvokedContext InvokedFilter(ChatHistoryProvider.InvokedContext ctx) => ctx;

        // Act
        var filter = new ChatHistoryProviderMessageFilter(innerProviderMock.Object, InvokingFilter, InvokedFilter);

        // Assert
        Assert.NotNull(filter);
    }

    [Fact]
    public async Task InvokingAsync_WithNoOpFilters_ReturnsInnerProviderMessagesAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<ChatHistoryProvider>();
        var expectedMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Test")]);

        innerProviderMock
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(expectedMessages);

        var filter = new ChatHistoryProviderMessageFilter(innerProviderMock.Object, x => x, x => x);

        // Act
        var result = (await filter.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("Hello", result[0].Text);
        Assert.Equal("Hi there!", result[1].Text);
        innerProviderMock
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task InvokingAsync_WithInvokingFilter_AppliesFilterAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<ChatHistoryProvider>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!"),
            new(ChatRole.User, "How are you?")
        };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Test")]);

        innerProviderMock
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(innerMessages);

        // Filter to only user messages
        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) => msgs.Where(m => m.Role == ChatRole.User);

        var filter = new ChatHistoryProviderMessageFilter(innerProviderMock.Object, InvokingFilter);

        // Act
        var result = (await filter.InvokingAsync(context, CancellationToken.None)).ToList();

        // Assert
        Assert.Equal(2, result.Count);
        Assert.All(result, msg => Assert.Equal(ChatRole.User, msg.Role));
        innerProviderMock
            .Protected()
            .Verify<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task InvokingAsync_WithInvokingFilter_CanModifyMessagesAsync()
    {
        // Arrange
        var innerProviderMock = new Mock<ChatHistoryProvider>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var context = new ChatHistoryProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Test")]);

        innerProviderMock
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(innerMessages);

        // Filter that transforms messages
        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) =>
            msgs.Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}"));

        var filter = new ChatHistoryProviderMessageFilter(innerProviderMock.Object, InvokingFilter);

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
        var innerProviderMock = new Mock<ChatHistoryProvider>();
        List<ChatMessage> requestMessages =
        [
            new(ChatRole.System, "System") { AdditionalProperties = new() { { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "TestSource") } } },
            new(ChatRole.User, "Hello"),
        ];
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response") };
        var context = new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages)
        {
            ResponseMessages = responseMessages
        };

        ChatHistoryProvider.InvokedContext? capturedContext = null;
        innerProviderMock
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<ChatHistoryProvider.InvokedContext, CancellationToken>((ctx, ct) => capturedContext = ctx)
            .Returns(default(ValueTask));

        // Filter that modifies the context
        ChatHistoryProvider.InvokedContext InvokedFilter(ChatHistoryProvider.InvokedContext ctx)
        {
            var modifiedRequestMessages = ctx.RequestMessages.Where(x => x.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.External).Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}")).ToList();
            return new ChatHistoryProvider.InvokedContext(s_mockAgent, s_mockSession, modifiedRequestMessages)
            {
                ResponseMessages = ctx.ResponseMessages,
                InvokeException = ctx.InvokeException
            };
        }

        var filter = new ChatHistoryProviderMessageFilter(innerProviderMock.Object, invokedMessagesFilter: InvokedFilter);

        // Act
        await filter.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Single(capturedContext.RequestMessages);
        Assert.Equal("[FILTERED] Hello", capturedContext.RequestMessages.First().Text);
        innerProviderMock
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public void Serialize_DelegatesToInnerProvider()
    {
        // Arrange
        var innerProviderMock = new Mock<ChatHistoryProvider>();
        var expectedJson = JsonSerializer.SerializeToElement("data", TestJsonSerializerContext.Default.String);

        innerProviderMock
            .Setup(s => s.Serialize(It.IsAny<JsonSerializerOptions>()))
            .Returns(expectedJson);

        var filter = new ChatHistoryProviderMessageFilter(innerProviderMock.Object, x => x, x => x);

        // Act
        var result = filter.Serialize();

        // Assert
        Assert.Equal(expectedJson.GetRawText(), result.GetRawText());
        innerProviderMock.Verify(s => s.Serialize(null), Times.Once);
    }
}
