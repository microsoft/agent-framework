// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="CompactionProvider"/> class.
/// </summary>
public sealed class CompactionProviderTests
{
    [Fact]
    public void ConstructorThrowsOnNullStrategy()
    {
        Assert.Throws<ArgumentNullException>(() => new CompactionProvider(null!));
    }

    [Fact]
    public void StateKeysReturnsExpectedKey()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        // Act & Assert — default state key is the strategy type name
        Assert.Single(provider.StateKeys);
        Assert.Equal(nameof(TruncationCompactionStrategy), provider.StateKeys[0]);
    }

    [Fact]
    public void StateKeysAreStableAcrossEquivalentInstances()
    {
        // Arrange — two providers with equivalent (but distinct) strategies
        CompactionProvider provider1 = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));
        CompactionProvider provider2 = new(new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(100000)));

        // Act & Assert — default keys must be identical for session state stability
        Assert.Equal(provider1.StateKeys[0], provider2.StateKeys[0]);
    }

    [Fact]
    public void StateKeysReturnsCustomKeyWhenProvided()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy, stateKey: "my-custom-key");

        // Act & Assert
        Assert.Single(provider.StateKeys);
        Assert.Equal("my-custom-key", provider.StateKeys[0]);
    }

    [Fact]
    public async Task InvokingAsyncNoSessionPassesThroughAsync()
    {
        // Arrange — no session → passthrough
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

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
        CompactionProvider provider = new(strategy);

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
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreservedGroups: 1);
        CompactionProvider provider = new(strategy);

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
        CompactionProvider provider = new(strategy);

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
        CompactionProvider provider = new(strategy);

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
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreservedGroups: 1);
        CompactionProvider provider = new(strategy);

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
        CompactionProvider provider = new(strategy);

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

    [Fact]
    public async Task CompactAsyncThrowsOnNullStrategyAsync()
    {
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        await Assert.ThrowsAsync<ArgumentNullException>(() => CompactionProvider.CompactAsync(null!, messages));
    }

    [Fact]
    public async Task CompactAsyncReturnsAllMessagesWhenTriggerDoesNotFireAsync()
    {
        // Arrange — trigger never fires → no compaction
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert — all messages preserved
        List<ChatMessage> resultList = [.. result];
        Assert.Equal(messages.Count, resultList.Count);
        Assert.Equal("Q1", resultList[0].Text);
        Assert.Equal("A1", resultList[1].Text);
        Assert.Equal("Q2", resultList[2].Text);
    }

    [Fact]
    public async Task CompactAsyncReducesMessagesWhenTriggeredAsync()
    {
        // Arrange — strategy that always triggers and keeps only 1 group
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert — compaction should have reduced the message count
        List<ChatMessage> resultList = [.. result];
        Assert.True(resultList.Count < messages.Count);
    }

    [Fact]
    public async Task CompactAsyncHandlesEmptyMessageListAsync()
    {
        // Arrange
        TruncationCompactionStrategy strategy = new(CompactionTriggers.Always, minimumPreservedGroups: 1);
        List<ChatMessage> messages = [];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public async Task CompactAsyncWorksWithNonListEnumerableAsync()
    {
        // Arrange — IEnumerable (not a List<ChatMessage>) to exercise the list copy branch
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        IEnumerable<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        IEnumerable<ChatMessage> result = await CompactionProvider.CompactAsync(strategy, messages);

        // Assert
        List<ChatMessage> resultList = [.. result];
        Assert.Single(resultList);
        Assert.Equal("Hello", resultList[0].Text);
    }

    [Fact]
    public void CompactionStateAssignment()
    {
        // Arrange
        CompactionProvider.State state = new();

        // Assert
        Assert.NotNull(state.MessageGroups);
        Assert.Empty(state.MessageGroups);

        // Act
        state.MessageGroups = [new CompactionMessageGroup(CompactionGroupKind.User, [], 0, 0, 0)];

        // Assert
        Assert.Single(state.MessageGroups);
    }

    [Fact]
    public async Task InvokingAsyncMarksOnlyPreviouslySeenMessagesAsChatHistoryAsync()
    {
        // Arrange — no-compaction strategy so we can observe marking behavior only
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactionProvider provider = new(strategy);

        Mock<AIAgent> mockAgent = new() { CallBase = true };
        TestAgentSession session = new();

        // --- First invocation: [Q1, A1, Q2] ---
        ChatMessage q1 = new(ChatRole.User, "Q1");
        ChatMessage a1 = new(ChatRole.Assistant, "A1");
        ChatMessage q2 = new(ChatRole.User, "Q2");

        AIContextProvider.InvokingContext context1 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = new List<ChatMessage> { q1, a1, q2 } });

        AIContext result1 = await provider.InvokingAsync(context1);

        // Assert — on first invocation, no messages should be marked as ChatHistory
        List<ChatMessage> resultList1 = [.. result1.Messages!];
        Assert.Equal(3, resultList1.Count);
        foreach (ChatMessage message in resultList1)
        {
            Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, message.GetAgentRequestMessageSourceType());
        }

        // --- Second invocation: [Q1, A1, Q2, A2, Q3] ---
        ChatMessage a2 = new(ChatRole.Assistant, "A2");
        ChatMessage q3 = new(ChatRole.User, "Q3");

        AIContextProvider.InvokingContext context2 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = new List<ChatMessage> { q1, a1, q2, a2, q3 } });

        AIContext result2 = await provider.InvokingAsync(context2);

        // Assert — messages from the first invocation should be marked as ChatHistory,
        // while new messages should not.
        List<ChatMessage> resultList2 = [.. result2.Messages!];
        Assert.Equal(5, resultList2.Count);

        // Q1, A1, Q2 were already in the provider state — they should be ChatHistory
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList2[0].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList2[1].GetAgentRequestMessageSourceType());
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList2[2].GetAgentRequestMessageSourceType());

        // A2, Q3 are new to the provider — they should NOT be ChatHistory
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList2[3].GetAgentRequestMessageSourceType());
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList2[4].GetAgentRequestMessageSourceType());

        // --- Third invocation: [Q1, A1, Q2, A2, Q3, A3, Q4] ---
        ChatMessage a3 = new(ChatRole.Assistant, "A3");
        ChatMessage q4 = new(ChatRole.User, "Q4");

        AIContextProvider.InvokingContext context3 = new(
            mockAgent.Object,
            session,
            new AIContext { Messages = new List<ChatMessage> { q1, a1, q2, a2, q3, a3, q4 } });

        AIContext result3 = await provider.InvokingAsync(context3);

        // Assert — all previously seen messages should be ChatHistory, only brand-new ones should not
        List<ChatMessage> resultList3 = [.. result3.Messages!];
        Assert.Equal(7, resultList3.Count);

        // Q1, A1, Q2, A2, Q3 were already in the provider state — they should be ChatHistory
        for (int i = 0; i < 5; i++)
        {
            Assert.Equal(AgentRequestMessageSourceType.ChatHistory, resultList3[i].GetAgentRequestMessageSourceType());
        }

        // A3, Q4 are new — they should NOT be ChatHistory
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList3[5].GetAgentRequestMessageSourceType());
        Assert.NotEqual(AgentRequestMessageSourceType.ChatHistory, resultList3[6].GetAgentRequestMessageSourceType());
    }

    private sealed class TestAgentSession : AgentSession;
}
