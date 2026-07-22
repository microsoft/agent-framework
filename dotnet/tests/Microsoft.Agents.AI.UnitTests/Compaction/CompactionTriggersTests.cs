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
    public void TokensExceedReturnsTrueWhenAboveThreshold()
    {
        // Arrange — use a long message to guarantee tokens > 0
        CompactionTrigger trigger = CompactionTriggers.TokensExceed(0);
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hello world")]);

        // Act & Assert
        Assert.True(trigger(index));
    }

    [Fact]
    public void TokensExceedReturnsFalseWhenBelowThreshold()
    {
        CompactionTrigger trigger = CompactionTriggers.TokensExceed(999_999);
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hi")]);

        Assert.False(trigger(index));
    }

    [Fact]
    public void MessagesExceedReturnsExpectedResult()
    {
        CompactionTrigger trigger = CompactionTriggers.MessagesExceed(2);
        CompactionMessageIndex small = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.User, "B"),
        ]);
        CompactionMessageIndex large = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.User, "B"),
            new ChatMessage(ChatRole.User, "C"),
        ]);

        Assert.False(trigger(small));
        Assert.True(trigger(large));
    }

    [Fact]
    public void TurnsExceedReturnsExpectedResult()
    {
        CompactionTrigger trigger = CompactionTriggers.TurnsExceed(1);
        CompactionMessageIndex oneTurn = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
        ]);
        CompactionMessageIndex twoTurns = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ]);

        Assert.False(trigger(oneTurn));
        Assert.True(trigger(twoTurns));
    }

    [Fact]
    public void GroupsExceedReturnsExpectedResult()
    {
        CompactionTrigger trigger = CompactionTriggers.GroupsExceed(2);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "A"),
            new ChatMessage(ChatRole.Assistant, "B"),
            new ChatMessage(ChatRole.User, "C"),
        ]);

        Assert.True(trigger(index));
    }

    [Fact]
    public void HasToolCallsReturnsTrueWhenToolCallGroupExists()
    {
        CompactionTrigger trigger = CompactionTriggers.HasToolCalls();
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("c1", "fn")]),
            new ChatMessage(ChatRole.Tool, "result"),
        ]);

        Assert.True(trigger(index));
    }

    [Fact]
    public void HasToolCallsReturnsFalseWhenNoToolCallGroup()
    {
        CompactionTrigger trigger = CompactionTriggers.HasToolCalls();
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        Assert.False(trigger(index));
    }

    [Fact]
    public void AllRequiresAllConditions()
    {
        CompactionTrigger trigger = CompactionTriggers.All(
            CompactionTriggers.TokensExceed(0),
            CompactionTriggers.MessagesExceed(5));

        CompactionMessageIndex small = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);

        // Tokens > 0 is true, but messages > 5 is false
        Assert.False(trigger(small));
    }

    [Fact]
    public void AnyRequiresAtLeastOneCondition()
    {
        CompactionTrigger trigger = CompactionTriggers.Any(
            CompactionTriggers.TokensExceed(999_999),
            CompactionTriggers.MessagesExceed(0));

        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);

        // Tokens not exceeded, but messages > 0 is true
        Assert.True(trigger(index));
    }

    [Fact]
    public void AllEmptyTriggersReturnsTrue()
    {
        CompactionTrigger trigger = CompactionTriggers.All();
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);
        Assert.True(trigger(index));
    }

    [Fact]
    public void AnyEmptyTriggersReturnsFalse()
    {
        CompactionTrigger trigger = CompactionTriggers.Any();
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);
        Assert.False(trigger(index));
    }

    [Fact]
    public void TokensBelowReturnsTrueWhenBelowThreshold()
    {
        CompactionTrigger trigger = CompactionTriggers.TokensBelow(999_999);
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hi")]);

        Assert.True(trigger(index));
    }

    [Fact]
    public void TokensBelowReturnsFalseWhenAboveThreshold()
    {
        CompactionTrigger trigger = CompactionTriggers.TokensBelow(0);
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "Hello world")]);

        Assert.False(trigger(index));
    }

    [Fact]
    public void AlwaysReturnsTrue()
    {
        CompactionMessageIndex index = CompactionMessageIndex.Create([new ChatMessage(ChatRole.User, "A")]);
        Assert.True(CompactionTriggers.Always(index));
    }
}
