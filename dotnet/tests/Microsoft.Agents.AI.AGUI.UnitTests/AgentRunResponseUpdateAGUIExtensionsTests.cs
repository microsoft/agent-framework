// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunResponseUpdateAGUIExtensions"/> class.
/// </summary>
public sealed class AgentRunResponseUpdateAGUIExtensionsTests
{
    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsRunStartedEvent_ToRunStartedContentAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        RunStartedContent content = Assert.IsType<RunStartedContent>(updates[0].Contents[0]);
        Assert.Equal("thread1", content.ThreadId);
        Assert.Equal("run1", content.RunId);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsRunFinishedEvent_ToRunFinishedContentAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1", Result = "Success" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        RunFinishedContent content = Assert.IsType<RunFinishedContent>(updates[0].Contents[0]);
        Assert.Equal("thread1", content.ThreadId);
        Assert.Equal("run1", content.RunId);
        Assert.Equal("Success", content.Result);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsRunErrorEvent_ToRunErrorContentAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new RunErrorEvent { Message = "Error occurred", Code = "ERR001" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        RunErrorContent content = Assert.IsType<RunErrorContent>(updates[0].Contents[0]);
        Assert.Equal("Error occurred", content.Message);
        Assert.Equal("ERR001", content.Code);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_ConvertsTextMessageSequence_ToTextUpdatesWithCorrectRoleAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = " World" },
            new TextMessageEndEvent { MessageId = "msg1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.All(updates, u => Assert.Equal(ChatRole.Assistant, u.Role));
        Assert.Equal("Hello", ((TextContent)updates[0].Contents[0]).Text);
        Assert.Equal(" World", ((TextContent)updates[1].Contents[0]).Text);
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithTextMessageStartWhileMessageInProgress_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.User }
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
            {
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_WithTextMessageEndForWrongMessageId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg2" }
        ];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
            {
            }
        });
    }

    [Fact]
    public async Task AsAgentRunResponseUpdatesAsync_MaintainsMessageContext_AcrossMultipleContentEventsAsync()
    {
        // Arrange
        List<BaseEvent> events =
        [
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = " " },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "World" },
            new TextMessageEndEvent { MessageId = "msg1" }
        ];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in events.ToAsyncEnumerableAsync().AsAgentRunResponseUpdatesAsync())
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(3, updates.Count);
        Assert.All(updates, u => Assert.Equal(ChatRole.Assistant, u.Role));
        Assert.All(updates, u => Assert.Equal("msg1", u.MessageId));
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
