// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ChatMessageStoreExtensions"/> class.
/// </summary>
public class ChatMessageStoreExtensionsTests
{
    [Fact]
    public async Task WithMessageFilters_AppliesBothFiltersAsync()
    {
        // Arrange
        var innerStoreMock = new Mock<ChatMessageStore>();
        var innerMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, "Hi there!")
        };
        var invokingContext = new ChatMessageStore.InvokingContext([new ChatMessage(ChatRole.User, "Test")]);

        innerStoreMock
            .Setup(s => s.InvokingAsync(invokingContext, It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerMessages);

        IEnumerable<ChatMessage> InvokingFilter(IEnumerable<ChatMessage> msgs) =>
            msgs.Select(m => new ChatMessage(m.Role, $"[FILTERED] {m.Text}"));

        ChatMessageStore.InvokedContext InvokedFilter(ChatMessageStore.InvokedContext ctx)
        {
            ctx.AIContextProviderMessages = null;
            return ctx;
        }

        // Act
        ChatMessageStore filteredStore = innerStoreMock.Object.WithMessageFilters(InvokingFilter, InvokedFilter);
        IEnumerable<ChatMessage> result = await filteredStore.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(filteredStore);
        List<ChatMessage> resultList = result.ToList();
        Assert.Equal(2, resultList.Count);
        Assert.Equal("[FILTERED] Hello", resultList[0].Text);
        Assert.Equal("[FILTERED] Hi there!", resultList[1].Text);
    }

    [Fact]
    public async Task WithAIContextProviderMessageRemoval_RemovesAIContextProviderMessagesAsync()
    {
        // Arrange
        var innerStore = new InMemoryChatMessageStore();
        var requestMessages = new List<ChatMessage> { new(ChatRole.User, "Hello") };
        var chatMessageStoreMessages = new List<ChatMessage> { new(ChatRole.System, "System") };
        var aiContextProviderMessages = new List<ChatMessage> { new(ChatRole.System, "AI Context Provider Message") };
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response") };

        var context = new ChatMessageStore.InvokedContext(requestMessages, chatMessageStoreMessages)
        {
            AIContextProviderMessages = aiContextProviderMessages,
            ResponseMessages = responseMessages
        };

        // Act
        ChatMessageStore filteredStore = innerStore.WithAIContextProviderMessageRemoval();
        await filteredStore.InvokedAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(filteredStore);

        // Verify that AI context provider messages are not added to the store
        Assert.Equal(2, innerStore.Count);
        Assert.Equal("Hello", innerStore[0].Text);
        Assert.Equal("Response", innerStore[1].Text);
    }
}
