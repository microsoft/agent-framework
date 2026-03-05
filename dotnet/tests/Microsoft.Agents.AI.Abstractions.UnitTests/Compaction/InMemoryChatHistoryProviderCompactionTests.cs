// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction;

/// <summary>
/// Contains tests for the compaction integration with <see cref="InMemoryChatHistoryProvider"/>.
/// </summary>
public class InMemoryChatHistoryProviderCompactionTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private static AgentSession CreateMockSession() => new Mock<AgentSession>().Object;

    [Fact]
    public void Constructor_SetsCompactionStrategy_FromOptions()
    {
        // Arrange
        Mock<ICompactionStrategy> strategy = new();

        // Act
        InMemoryChatHistoryProvider provider = new(new InMemoryChatHistoryProviderOptions
        {
            CompactionStrategy = strategy.Object,
        });

        // Assert
        Assert.Same(strategy.Object, provider.CompactionStrategy);
    }

    [Fact]
    public void Constructor_CompactionStrategyIsNull_ByDefault()
    {
        // Arrange & Act
        InMemoryChatHistoryProvider provider = new();

        // Assert
        Assert.Null(provider.CompactionStrategy);
    }

    [Fact]
    public async Task StoreChatHistoryAsync_AppliesCompaction_WhenStrategyConfiguredAsync()
    {
        // Arrange — mock strategy that excludes the first included non-system group
        Mock<ICompactionStrategy> mockStrategy = new();
        mockStrategy.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                foreach (MessageGroup group in groups.Groups)
                {
                    if (!group.IsExcluded && group.Kind != MessageGroupKind.System)
                    {
                        group.IsExcluded = true;
                        group.ExcludeReason = "Mock compaction";
                        break;
                    }
                }
            })
            .ReturnsAsync(true);

        InMemoryChatHistoryProvider provider = new(new InMemoryChatHistoryProviderOptions
        {
            CompactionStrategy = mockStrategy.Object,
        });

        AgentSession session = CreateMockSession();

        // Pre-populate with some messages
        List<ChatMessage> existingMessages =
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
        ];
        provider.SetMessages(session, existingMessages);

        // Invoke the store flow with additional messages
        List<ChatMessage> requestMessages =
        [
            new ChatMessage(ChatRole.User, "Second"),
        ];
        List<ChatMessage> responseMessages =
        [
            new ChatMessage(ChatRole.Assistant, "Response 2"),
        ];

        ChatHistoryProvider.InvokedContext context = new(s_mockAgent, session, requestMessages, responseMessages);

        // Act
        await provider.InvokedAsync(context);

        // Assert - compaction should have removed one group
        List<ChatMessage> storedMessages = provider.GetMessages(session);
        Assert.Equal(3, storedMessages.Count);
        mockStrategy.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task StoreChatHistoryAsync_DoesNotCompact_WhenNoStrategyAsync()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        AgentSession session = CreateMockSession();

        List<ChatMessage> requestMessages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];
        List<ChatMessage> responseMessages =
        [
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ];

        ChatHistoryProvider.InvokedContext context = new(s_mockAgent, session, requestMessages, responseMessages);

        // Act
        await provider.InvokedAsync(context);

        // Assert - all messages should be stored
        List<ChatMessage> storedMessages = provider.GetMessages(session);
        Assert.Equal(2, storedMessages.Count);
    }

    [Fact]
    public async Task CompactStorageAsync_CompactsStoredMessagesAsync()
    {
        // Arrange — mock strategy that excludes the two oldest non-system groups
        Mock<ICompactionStrategy> mockStrategy = new();
        mockStrategy.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                int excluded = 0;
                foreach (MessageGroup group in groups.Groups)
                {
                    if (!group.IsExcluded && group.Kind != MessageGroupKind.System && excluded < 2)
                    {
                        group.IsExcluded = true;
                        excluded++;
                    }
                }
            })
            .ReturnsAsync(true);

        InMemoryChatHistoryProvider provider = new(new InMemoryChatHistoryProviderOptions
        {
            CompactionStrategy = mockStrategy.Object,
        });

        AgentSession session = CreateMockSession();
        provider.SetMessages(session,
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
            new ChatMessage(ChatRole.Assistant, "Response 2"),
        ]);

        // Act
        bool result = await provider.CompactStorageAsync(session);

        // Assert
        Assert.True(result);
        List<ChatMessage> messages = provider.GetMessages(session);
        Assert.Equal(2, messages.Count);
        mockStrategy.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CompactStorageAsync_UsesProvidedStrategy_OverDefaultAsync()
    {
        // Arrange
        Mock<ICompactionStrategy> defaultStrategy = new();
        Mock<ICompactionStrategy> overrideStrategy = new();

        overrideStrategy.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                // Exclude all but the last group
                for (int i = 0; i < groups.Groups.Count - 1; i++)
                {
                    groups.Groups[i].IsExcluded = true;
                }
            })
            .ReturnsAsync(true);

        InMemoryChatHistoryProvider provider = new(new InMemoryChatHistoryProviderOptions
        {
            CompactionStrategy = defaultStrategy.Object,
        });

        AgentSession session = CreateMockSession();
        provider.SetMessages(session,
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.User, "Second"),
            new ChatMessage(ChatRole.User, "Third"),
        ]);

        // Act
        bool result = await provider.CompactStorageAsync(session, overrideStrategy.Object);

        // Assert
        Assert.True(result);
        List<ChatMessage> messages = provider.GetMessages(session);
        Assert.Single(messages);
        Assert.Equal("Third", messages[0].Text);

        // Verify the override was used, not the default
        overrideStrategy.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Once);
        defaultStrategy.Verify(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task CompactStorageAsync_Throws_WhenNoStrategyAvailableAsync()
    {
        // Arrange
        InMemoryChatHistoryProvider provider = new();
        AgentSession session = CreateMockSession();

        // Act & Assert
        await Assert.ThrowsAsync<System.InvalidOperationException>(
            () => provider.CompactStorageAsync(session));
    }

    [Fact]
    public async Task CompactStorageAsync_WithCustomStrategy_AppliesCustomLogicAsync()
    {
        // Arrange
        Mock<ICompactionStrategy> mockStrategy = new();
        mockStrategy.Setup(s => s.CompactAsync(It.IsAny<MessageGroups>(), It.IsAny<CancellationToken>()))
            .Callback<MessageGroups, CancellationToken>((groups, _) =>
            {
                // Exclude all user groups
                foreach (MessageGroup group in groups.Groups)
                {
                    if (group.Kind == MessageGroupKind.User)
                    {
                        group.IsExcluded = true;
                    }
                }
            })
            .ReturnsAsync(true);

        InMemoryChatHistoryProvider provider = new();
        AgentSession session = CreateMockSession();
        provider.SetMessages(session,
        [
            new ChatMessage(ChatRole.System, "System"),
            new ChatMessage(ChatRole.User, "User message"),
            new ChatMessage(ChatRole.Assistant, "Response"),
        ]);

        // Act
        bool result = await provider.CompactStorageAsync(session, mockStrategy.Object);

        // Assert
        Assert.True(result);
        List<ChatMessage> messages = provider.GetMessages(session);
        Assert.Equal(2, messages.Count);
        Assert.Equal(ChatRole.System, messages[0].Role);
        Assert.Equal(ChatRole.Assistant, messages[1].Role);
    }
}
