// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for <see cref="CompactionTrigger"/> and <see cref="CompactionTriggers"/>.
/// </summary>
public class CompactionTriggersTests
{
    [Fact]
    public void TokensExceed_ReturnsTrueWhenAboveThreshold()
    {
        // Arrange — use a long message to guarantee tokens > 0
        CompactionTrigger trigger = CompactionTriggers.TokensExceed(0);
        MessageIndex index = MessageIndex.Create([new ChatMessage(ChatRole.User, "Hello world")]);

        // Act & Assert
        Assert.True(trigger(index));
    }

    [Fact]
    public void TokensExceed_ReturnsFalseWhenBelowThreshold()
    {
        CompactionTrigger trigger = CompactionTriggers.TokensExceed(999_999);
        MessageIndex index = MessageIndex.Create([new ChatMessage(ChatRole.User, "Hi")]);

        Assert.False(trigger(index));
    }

    [Fact]
    public void MessagesExceed_ReturnsExpectedResult()
    {
        CompactionTrigger trigger = CompactionTriggers.MessagesExceed(2);
        MessageIndex small = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.User, "B"),
        ]);
        MessageIndex large = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.User, "B"),
            new ChatMessage(ChatRole.User, "C"),
        ]);

        Assert.False(trigger(small));
        Assert.True(trigger(large));
    }

    [Fact]
    public void TurnsExceed_ReturnsExpectedResult()
    {
        CompactionTrigger trigger = CompactionTriggers.TurnsExceed(1);
        MessageIndex oneTurn = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ]);
        MessageIndex twoTurns = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        Assert.False(trigger(oneTurn));
        Assert.True(trigger(twoTurns));
    }

    [Fact]
    public void GroupsExceed_ReturnsExpectedResult()
    {
        CompactionTrigger trigger = CompactionTriggers.GroupsExceed(2);
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
        ]);

        Assert.True(trigger(index));
    }

    [Fact]
    public void HasToolCalls_ReturnsTrueWhenToolCallGroupExists()
    {
        CompactionTrigger trigger = CompactionTriggers.HasToolCalls();
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, "result"),
        ]);

        Assert.True(trigger(index));
    }

    [Fact]
    public void HasToolCalls_ReturnsFalseWhenNoToolCallGroup()
    {
        CompactionTrigger trigger = CompactionTriggers.HasToolCalls();
        MessageIndex index = MessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        Assert.False(trigger(index));
    }

    [Fact]
    public void All_RequiresAllConditions()
    {
        CompactionTrigger trigger = CompactionTriggers.All(
            CompactionTriggers.TokensExceed(0),
            CompactionTriggers.MessagesExceed(5));

        MessageIndex small = MessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);

        // Tokens > 0 is true, but messages > 5 is false
        Assert.False(trigger(small));
    }

    [Fact]
    public void Any_RequiresAtLeastOneCondition()
    {
        CompactionTrigger trigger = CompactionTriggers.Any(
            CompactionTriggers.TokensExceed(999_999),
            CompactionTriggers.MessagesExceed(0));

        MessageIndex index = MessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);

        // Tokens not exceeded, but messages > 0 is true
        Assert.True(trigger(index));
    }

    [Fact]
    public void All_EmptyTriggers_ReturnsTrue()
    {
        CompactionTrigger trigger = CompactionTriggers.All();
        MessageIndex index = MessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);
        Assert.True(trigger(index));
    }

    [Fact]
    public void Any_EmptyTriggers_ReturnsFalse()
    {
        CompactionTrigger trigger = CompactionTriggers.Any();
        MessageIndex index = MessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);
        Assert.False(trigger(index));
    }
}
