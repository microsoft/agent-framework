// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="ChatReducerCompactionStrategy"/> class.
/// </summary>
public class ChatReducerCompactionStrategyTests
{
    [Fact]
    public void ConstructorNullReducerThrows()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new ChatReducerCompactionStrategy(null!, CompactionTriggers.Always));
    }

    [Fact]
    public async Task CompactAsyncTriggerNotMetReturnsFalseAsync()
    {
        // Arrange — trigger never fires
        TestChatReducer reducer = new(messages => messages.Take(1));
        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Never);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(0, reducer.CallCount);
        Assert.Equal(2, index.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsyncReducerReturnsFewerMessagesRebuildsIndexAsync()
    {
        // Arrange — reducer keeps only the last message
        TestChatReducer reducer = new(messages => messages.Skip(messages.Count() - 1));
        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.True(result);
        Assert.Equal(1, reducer.CallCount);
        Assert.Equal(1, index.IncludedGroupCount);
        Assert.Equal("Second", index.Groups[0].Messages[0].Text);
    }

    [Fact]
    public async Task CompactAsyncReducerReturnsSameCountReturnsFalseAsync()
    {
        // Arrange — reducer returns all messages (no reduction)
        TestChatReducer reducer = new(messages => messages);
        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.Assistant, "Hi!"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(1, reducer.CallCount);
        Assert.Equal(2, index.IncludedGroupCount);
    }

    [Fact]
    public async Task CompactAsyncEmptyIndexReturnsFalseAsync()
    {
        // Arrange — no included messages
        TestChatReducer reducer = new(messages => messages);
        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create([]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.False(result);
        Assert.Equal(0, reducer.CallCount);
    }

    [Fact]
    public async Task CompactAsyncPreservesSystemMessagesWhenReducerKeepsThemAsync()
    {
        // Arrange — reducer keeps system + last user message
        TestChatReducer reducer = new(messages =>
        {
            var nonSystem = messages.Where(m => m.Role != ChatRole.System).ToList();
            return messages.Where(m => m.Role == ChatRole.System)
                .Concat(nonSystem.Skip(nonSystem.Count - 1));
        });

        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.System, "You are helpful."),
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.Assistant, "Response 1"),
            new ChatMessage(ChatRole.User, "Second"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.True(result);
        Assert.Equal(2, index.IncludedGroupCount);
        Assert.Equal(CompactionGroupKind.System, index.Groups[0].Kind);
        Assert.Equal("You are helpful.", index.Groups[0].Messages[0].Text);
        Assert.Equal(CompactionGroupKind.User, index.Groups[1].Kind);
        Assert.Equal("Second", index.Groups[1].Messages[0].Text);
    }

    [Fact]
    public async Task CompactAsyncRebuildsToolCallGroupsCorrectlyAsync()
    {
        // Arrange — reducer keeps last 3 messages (assistant tool call + tool result + user)
        TestChatReducer reducer = new(messages => messages.Skip(messages.Count() - 3));

        ChatMessage assistantToolCall = new(ChatRole.Assistant, [new FunctionCallContent("call1", "get_weather")]);
        ChatMessage toolResult = new(ChatRole.Tool, "Sunny");

        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Old question"),
            new ChatMessage(ChatRole.Assistant, "Old answer"),
            assistantToolCall,
            toolResult,
            new ChatMessage(ChatRole.User, "New question"),
        ]);

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert
        Assert.True(result);
        // Should have 2 groups: ToolCall group (assistant + tool result) + User group
        Assert.Equal(2, index.IncludedGroupCount);
        Assert.Equal(CompactionGroupKind.ToolCall, index.Groups[0].Kind);
        Assert.Equal(2, index.Groups[0].Messages.Count);
        Assert.Equal(CompactionGroupKind.User, index.Groups[1].Kind);
    }

    [Fact]
    public async Task CompactAsyncSkipsAlreadyExcludedGroupsAsync()
    {
        // Arrange — one group is pre-excluded, reducer keeps last message
        TestChatReducer reducer = new(messages => messages.Skip(messages.Count() - 1));
        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "Excluded"),
            new ChatMessage(ChatRole.User, "Included 1"),
            new ChatMessage(ChatRole.User, "Included 2"),
        ]);
        index.Groups[0].IsExcluded = true;

        // Act
        bool result = await strategy.CompactAsync(index);

        // Assert — reducer only saw 2 included messages, kept 1
        Assert.True(result);
        Assert.Equal(1, index.IncludedGroupCount);
        Assert.Equal("Included 2", index.Groups[0].Messages[0].Text);
    }

    [Fact]
    public async Task CompactAsyncExposesReducerPropertyAsync()
    {
        // Arrange
        TestChatReducer reducer = new(messages => messages);
        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);

        // Assert
        Assert.Same(reducer, strategy.ChatReducer);
        await Task.CompletedTask;
    }

    [Fact]
    public async Task CompactAsyncPassesCancellationTokenToReducerAsync()
    {
        // Arrange
        using CancellationTokenSource cancellationSource = new();
        CancellationToken capturedToken = default;
        TestChatReducer reducer = new((messages, cancellationToken) =>
        {
            capturedToken = cancellationToken;
            return Task.FromResult<IEnumerable<ChatMessage>>(messages.Skip(messages.Count() - 1).ToList());
        });

        ChatReducerCompactionStrategy strategy = new(reducer, CompactionTriggers.Always);
        CompactionMessageIndex index = CompactionMessageIndex.Create(
        [
            new ChatMessage(ChatRole.User, "First"),
            new ChatMessage(ChatRole.User, "Second"),
        ]);

        // Act
        await strategy.CompactAsync(index, logger: null, cancellationSource.Token);

        // Assert
        Assert.Equal(cancellationSource.Token, capturedToken);
    }

    /// <summary>
    /// A test implementation of <see cref="IChatReducer"/> that applies a configurable reduction function.
    /// </summary>
    private sealed class TestChatReducer : IChatReducer
    {
        private readonly Func<IEnumerable<ChatMessage>, CancellationToken, Task<IEnumerable<ChatMessage>>> _reduceFunc;

        public TestChatReducer(Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>> reduceFunc)
        {
            this._reduceFunc = (messages, _) => Task.FromResult(reduceFunc(messages));
        }

        public TestChatReducer(Func<IEnumerable<ChatMessage>, CancellationToken, Task<IEnumerable<ChatMessage>>> reduceFunc)
        {
            this._reduceFunc = reduceFunc;
        }

        public int CallCount { get; private set; }

        public async Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
        {
            this.CallCount++;
            return await this._reduceFunc(messages, cancellationToken).ConfigureAwait(false);
        }
    }
}
