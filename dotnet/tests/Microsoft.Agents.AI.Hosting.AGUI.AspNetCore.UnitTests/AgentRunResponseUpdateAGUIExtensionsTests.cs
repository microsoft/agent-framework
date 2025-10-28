// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunResponseUpdateAGUIExtensions"/> class.
/// </summary>
public sealed class AgentRunResponseUpdateAGUIExtensionsTests
{
    [Fact]
    public async Task AsAGUIEventStreamAsync_YieldsRunStartedEvent_AtBeginningWithCorrectIds()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<AgentRunResponseUpdate> updates = [];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);
        RunStartedEvent startEvent = Assert.IsType<RunStartedEvent>(events.First());
        Assert.Equal(ThreadId, startEvent.ThreadId);
        Assert.Equal(RunId, startEvent.RunId);
        Assert.Equal(AGUIEventTypes.RunStarted, startEvent.Type);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_YieldsRunFinishedEvent_AtEndWithCorrectIds()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<AgentRunResponseUpdate> updates = [];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.NotEmpty(events);
        RunFinishedEvent finishEvent = Assert.IsType<RunFinishedEvent>(events.Last());
        Assert.Equal(ThreadId, finishEvent.ThreadId);
        Assert.Equal(RunId, finishEvent.RunId);
        Assert.Equal(AGUIEventTypes.RunFinished, finishEvent.Type);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_ConvertsTextContentUpdates_ToTextMessageEvents()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<AgentRunResponseUpdate> updates =
        [
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = "msg1" }),
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, " World") { MessageId = "msg1" })
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        Assert.Contains(events, e => e is TextMessageStartEvent);
        Assert.Contains(events, e => e is TextMessageContentEvent);
        Assert.Contains(events, e => e is TextMessageEndEvent);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_GroupsConsecutiveUpdates_WithSameMessageId()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        const string MessageId = "msg1";
        List<AgentRunResponseUpdate> updates =
        [
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = MessageId }),
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, " ") { MessageId = MessageId }),
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "World") { MessageId = MessageId })
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<TextMessageStartEvent> startEvents = events.OfType<TextMessageStartEvent>().ToList();
        List<TextMessageEndEvent> endEvents = events.OfType<TextMessageEndEvent>().ToList();
        Assert.Single(startEvents);
        Assert.Single(endEvents);
        Assert.Equal(MessageId, startEvents[0].MessageId);
        Assert.Equal(MessageId, endEvents[0].MessageId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_WithRoleChanges_EmitsProperTextMessageStartEvents()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<AgentRunResponseUpdate> updates =
        [
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Hello") { MessageId = "msg1" }),
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.User, "Hi") { MessageId = "msg2" })
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<TextMessageStartEvent> startEvents = events.OfType<TextMessageStartEvent>().ToList();
        Assert.Equal(2, startEvents.Count);
        Assert.Equal("msg1", startEvents[0].MessageId);
        Assert.Equal("msg2", startEvents[1].MessageId);
    }

    [Fact]
    public async Task AsAGUIEventStreamAsync_EmitsTextMessageEndEvent_WhenMessageIdChanges()
    {
        // Arrange
        const string ThreadId = "thread1";
        const string RunId = "run1";
        List<AgentRunResponseUpdate> updates =
        [
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "First") { MessageId = "msg1" }),
            new AgentRunResponseUpdate(new ChatResponseUpdate(ChatRole.Assistant, "Second") { MessageId = "msg2" })
        ];

        // Act
        List<BaseEvent> events = [];
        await foreach (BaseEvent evt in updates.ToAsyncEnumerableAsync().AsAGUIEventStreamAsync(ThreadId, RunId, CancellationToken.None))
        {
            events.Add(evt);
        }

        // Assert
        List<TextMessageEndEvent> endEvents = events.OfType<TextMessageEndEvent>().ToList();
        Assert.NotEmpty(endEvents);
        Assert.Contains(endEvents, e => e.MessageId == "msg1");
    }
}

internal static class AsyncEnumerableExtensions
{
    public static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(this IEnumerable<T> source)
    {
        foreach (T item in source)
        {
            yield return item;
            await Task.CompletedTask;
        }
    }
}
