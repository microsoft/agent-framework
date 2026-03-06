// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="MessageCompactionContextProvider"/> class.
/// </summary>
public sealed class MessageCompactionContextProviderTests
{
    [Fact]
    public void ConstructorThrowsOnNullStrategy()
    {
        Assert.Throws<ArgumentNullException>(() => new MessageCompactionContextProvider(null!));
    }

    [Fact]
    public void StateKeysReturnsExpectedKey()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy);

        // Act & Assert — default state key is the class name
        Assert.Single(provider.StateKeys);
        Assert.Equal(nameof(MessageCompactionContextProvider), provider.StateKeys[0]);
    }

    [Fact]
    public void StateKeysReturnsCustomKeyWhenProvided()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy, stateKey: "my-custom-key");

        // Act & Assert
        Assert.Single(provider.StateKeys);
        Assert.Equal("my-custom-key", provider.StateKeys[0]);
    }

    [Fact]
    public async Task InvokingAsyncNoSessionPassesThroughAsync()
    {
        // Arrange — no session → passthrough
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session: null,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — original context returned unchanged
        Assert.Same(messages, result.Messages);
    }

    [Fact]
    public async Task InvokingAsyncNullMessagesPassesThroughAsync()
    {
        // Arrange — messages is null → passthrough
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = null });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — original context returned unchanged
        Assert.Null(result.Messages);
    }

    [Fact]
    public async Task InvokingAsyncAppliesCompactionWhenTriggeredAsync()
    {
        // Arrange — strategy that always triggers and keeps only 1 group
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreserved: 1);
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — compaction should have reduced the message count
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultList = [.. result.Messages!];
        Assert.True(resultList.Count < messages.Count);
    }

    [Fact]
    public async Task InvokingAsyncNoCompactionNeededReturnsOriginalMessagesAsync()
    {
        // Arrange — trigger never fires → no compaction
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — original messages passed through
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultList = [.. result.Messages!];
        Assert.Single(resultList);
        Assert.Equal("Hello", resultList[0].Text);
    }

    [Fact]
    public async Task InvokingAsyncPreservesInstructionsAndToolsAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];
        AITool[] tools = [AIFunctionFactory.Create(() => "tool", "MyTool")];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext
            {
                Instructions = "Be helpful",
                Messages = messages,
                Tools = tools
            });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert — instructions and tools are preserved
        Assert.Equal("Be helpful", result.Instructions);
        Assert.Same(tools, result.Tools);
    }

    [Fact]
    public async Task InvokingAsyncWithExistingIndexUpdatesAsync()
    {
        // Arrange — call twice to exercise the "existing index" path
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreserved: 1);
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();

        List<ChatMessage> messages1 =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        AIContextProvider.InvokingContext context1 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages1 });

        // First call — initializes state
        await provider.InvokingAsync(context1);

        List<ChatMessage> messages2 =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ];

        AIContextProvider.InvokingContext context2 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages2 });

        // Act — second call exercises the update path
        AIContext result = await provider.InvokingAsync(context2);

        // Assert
        Assert.NotNull(result.Messages);
    }

    [Fact]
    public async Task InvokingAsyncWithNonListEnumerableCreatesListCopyAsync()
    {
        // Arrange — pass IEnumerable (not List<ChatMessage>) to exercise the list copy branch
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        MessageCompactionContextProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();

        // Use an IEnumerable (not a List) to trigger the copy path
        IEnumerable<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        AIContextProvider.InvokingContext context = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = messages });

        // Act
        AIContext result = await provider.InvokingAsync(context);

        // Assert
        Assert.NotNull(result.Messages);
        List<ChatMessage> resultList = [.. result.Messages!];
        Assert.Single(resultList);
        Assert.Equal("Hello", resultList[0].Text);
    }

    private sealed class TestAgentSession : AgentSession;
}
