// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Compaction;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.Compaction;

/// <summary>
/// Contains tests for the <see cref="CompactingChatClient"/> class.
/// </summary>
public sealed class CompactingChatClientTests : IDisposable
{
    /// <summary>
    /// Restores the static <see cref="AIAgent.CurrentRunContext"/> after each test.
    /// </summary>
    public void Dispose()
    {
        SetCurrentRunContext(null);
    }

    [Fact]
    public void ConstructorThrowsOnNullStrategyAsync()
    {
        Mock<IChatClient> mockInner = new();
        Assert.Throws<ArgumentNullException>(() => new CompactingChatClient(mockInner.Object, null!));
    }

    [Fact]
    public async Task GetResponseAsyncNoContextPassesThroughAsync()
    {
        // Arrange — no CurrentRunContext set → passthrough
        ChatResponse expectedResponse = new([new ChatMessage(ChatRole.Assistant, "Hi")]);
        Mock<IChatClient> mockInner = new();
        mockInner.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        // Act
        ChatResponse response = await client.GetResponseAsync(messages);

        // Assert
        Assert.Same(expectedResponse, response);
        mockInner.Verify(c => c.GetResponseAsync(
            messages,
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task GetResponseAsyncWithContextAppliesCompactionAsync()
    {
        // Arrange — set CurrentRunContext so compaction runs
        ChatResponse expectedResponse = new([new ChatMessage(ChatRole.Assistant, "Done")]);
        List<ChatMessage>? capturedMessages = null;
        Mock<IChatClient> mockInner = new();
        mockInner.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) =>
                capturedMessages = [.. msgs])
            .ReturnsAsync(expectedResponse);

        // Strategy that always triggers and keeps only 1 group
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreserved: 1);
        CompactingChatClient client = new(mockInner.Object, strategy);

        TestAgentSession session = new();
        SetRunContext(session);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // Act
        ChatResponse response = await client.GetResponseAsync(messages);

        // Assert — compaction should have removed oldest groups
        Assert.Same(expectedResponse, response);
        Assert.NotNull(capturedMessages);
        Assert.True(capturedMessages!.Count < messages.Count);
    }

    [Fact]
    public async Task GetResponseAsyncNoCompactionNeededReturnsOriginalMessagesAsync()
    {
        // Arrange — trigger never fires → no compaction
        ChatResponse expectedResponse = new([new ChatMessage(ChatRole.Assistant, "Hi")]);
        List<ChatMessage>? capturedMessages = null;
        Mock<IChatClient> mockInner = new();
        mockInner.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) =>
                capturedMessages = [.. msgs])
            .ReturnsAsync(expectedResponse);

        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        TestAgentSession session = new();
        SetRunContext(session);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
        ];

        // Act
        await client.GetResponseAsync(messages);

        // Assert — original messages passed through
        Assert.NotNull(capturedMessages);
        Assert.Single(capturedMessages!);
        Assert.Equal("Hello", capturedMessages[0].Text);
    }

    [Fact]
    public async Task GetResponseAsyncWithExistingIndexUpdatesAsync()
    {
        // Arrange — call twice to exercise the "existing index" path (state.MessageIndex.Count > 0)
        Mock<IChatClient> mockInner = new();
        mockInner.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "OK")]));

        // Strategy that always triggers, keeping 1 group
        TruncationCompactionStrategy strategy = new(_ => true, minimumPreserved: 1);
        CompactingChatClient client = new(mockInner.Object, strategy);

        TestAgentSession session = new();
        SetRunContext(session);

        List<ChatMessage> messages1 =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // First call — initializes state
        await client.GetResponseAsync(messages1);

        List<ChatMessage> messages2 =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
            new ChatMessage(ChatRole.Assistant, "A2"),
            new ChatMessage(ChatRole.User, "Q3"),
        ];

        // Act — second call exercises the update path
        ChatResponse response = await client.GetResponseAsync(messages2);

        // Assert
        Assert.NotNull(response);
    }

    [Fact]
    public async Task GetResponseAsyncNullSessionReturnsOriginalAsync()
    {
        // Arrange — CurrentRunContext exists but Session is null
        ChatResponse expectedResponse = new([new ChatMessage(ChatRole.Assistant, "Hi")]);
        Mock<IChatClient> mockInner = new();
        mockInner.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        // Set context with null session
        SetRunContext(null);

        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        ChatResponse response = await client.GetResponseAsync(messages);

        // Assert
        Assert.Same(expectedResponse, response);
    }

    [Fact]
    public async Task GetStreamingResponseAsyncNoContextPassesThroughAsync()
    {
        // Arrange — no CurrentRunContext
        Mock<IChatClient> mockInner = new();
        ChatResponseUpdate[] updates = [new(ChatRole.Assistant, "Hi")];
        mockInner.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(updates));

        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        List<ChatResponseUpdate> results = [];
        await foreach (ChatResponseUpdate update in client.GetStreamingResponseAsync(messages))
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
        Assert.Equal("Hi", results[0].Text);
    }

    [Fact]
    public async Task GetStreamingResponseAsyncWithContextAppliesCompactionAsync()
    {
        // Arrange
        Mock<IChatClient> mockInner = new();
        ChatResponseUpdate[] updates = [new(ChatRole.Assistant, "Done")];
        mockInner.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(updates));

        TruncationCompactionStrategy strategy = new(_ => true, minimumPreserved: 1);
        CompactingChatClient client = new(mockInner.Object, strategy);

        TestAgentSession session = new();
        SetRunContext(session);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Q1"),
            new ChatMessage(ChatRole.Assistant, "A1"),
            new ChatMessage(ChatRole.User, "Q2"),
        ];

        // Act
        List<ChatResponseUpdate> results = [];
        await foreach (ChatResponseUpdate update in client.GetStreamingResponseAsync(messages))
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
        Assert.Equal("Done", results[0].Text);
    }

    [Fact]
    public void GetServiceReturnsStrategyForMatchingType()
    {
        // Arrange
        Mock<IChatClient> mockInner = new();
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(1000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        // Act — typeof(Type).IsInstanceOfType(typeof(CompactionStrategy)) is true
        object? result = client.GetService(typeof(Type));

        // Assert
        Assert.Same(strategy, result);
    }

    [Fact]
    public void GetServiceDelegatesToBaseForNonMatchingType()
    {
        // Arrange
        Mock<IChatClient> mockInner = new();
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(1000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        // Act — typeof(string) doesn't match
        object? result = client.GetService(typeof(string));

        // Assert — delegates to base (which returns null for unregistered types)
        Assert.Null(result);
    }

    [Fact]
    public void GetServiceThrowsOnNullType()
    {
        Mock<IChatClient> mockInner = new();
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(1000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        Assert.Throws<ArgumentNullException>(() => client.GetService(null!));
    }

    [Fact]
    public void GetServiceWithServiceKeyDelegatesToBase()
    {
        // Arrange — non-null serviceKey always delegates
        Mock<IChatClient> mockInner = new();
        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(1000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        // Act
        object? result = client.GetService(typeof(Type), serviceKey: "mykey");

        // Assert — delegates to base because serviceKey is non-null
        Assert.Null(result);
    }

    [Fact]
    public async Task GetResponseAsyncMessagesNotListCreatesListCopyAsync()
    {
        // Arrange — pass IEnumerable (not List<ChatMessage>) to exercise the list copy branch
        ChatResponse expectedResponse = new([new ChatMessage(ChatRole.Assistant, "Hi")]);
        Mock<IChatClient> mockInner = new();
        mockInner.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        TruncationCompactionStrategy strategy = new(CompactionTriggers.TokensExceed(100000));
        CompactingChatClient client = new(mockInner.Object, strategy);

        TestAgentSession session = new();
        SetRunContext(session);

        // Use an IEnumerable (not a List) to trigger the copy path
        IEnumerable<ChatMessage> messages = new ChatMessage[] { new(ChatRole.User, "Hello") };

        // Act
        ChatResponse response = await client.GetResponseAsync(messages);

        // Assert
        Assert.Same(expectedResponse, response);
    }

    /// <summary>
    /// Sets <see cref="AIAgent.CurrentRunContext"/> via reflection.
    /// </summary>
    private static void SetCurrentRunContext(AgentRunContext? context)
    {
        FieldInfo? field = typeof(AIAgent).GetField("s_currentContext", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.NotNull(field);
        object? asyncLocal = field!.GetValue(null);
        Assert.NotNull(asyncLocal);
        PropertyInfo? valueProp = asyncLocal!.GetType().GetProperty("Value");
        Assert.NotNull(valueProp);
        valueProp!.SetValue(asyncLocal, context);
    }

    /// <summary>
    /// Creates an <see cref="AgentRunContext"/> with the given session and sets it as the current context.
    /// </summary>
    private static void SetRunContext(AgentSession? session)
    {
        Mock<AIAgent> mockAgent = new() { CallBase = true };
        AgentRunContext context = new(
            mockAgent.Object,
            session,
            new List<ChatMessage> { new(ChatRole.User, "test") },
            null);
        SetCurrentRunContext(context);
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableAsync(
        ChatResponseUpdate[] updates, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (ChatResponseUpdate update in updates)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return update;
            await Task.CompletedTask;
        }
    }

    private sealed class TestAgentSession : AgentSession;
}
