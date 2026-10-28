// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests that verify the behavior of <see cref="ChatClientAgentOptions.PersistPartialMessagesOnCancellation"/>
/// and <see cref="ChatClientAgentRunOptions.PersistPartialMessagesOnCancellation"/> when a streaming run is cancelled.
/// </summary>
public class ChatClientAgent_PartialPersistenceOnCancellationTests
{
    [Fact]
    public async Task RunStreamingAsync_FlagDisabled_DoesNotPersistOnCancellationAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("partial", "m1")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new());
        var session = await agent.CreateSessionAsync();

        // Act
        var received = await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        Assert.Equal("partial", string.Concat(received.Select(u => u.Text)));
        Assert.Empty(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_PersistsRequestAndPartialResponseAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("par", "m1"), TextUpdate("tial", "m1")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        var received = await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        Assert.Equal("partial", string.Concat(received.Select(u => u.Text)));
        var history = GetHistory(agent, session);
        Assert.Equal(2, history.Count);
        Assert.Equal(ChatRole.User, history[0].Role);
        Assert.Equal("Hello", history[0].Text);
        Assert.False(IsMarkedAsPartial(history[0]));
        Assert.Equal(ChatRole.Assistant, history[1].Role);
        Assert.Equal("partial", history[1].Text);
        Assert.True(IsMarkedAsPartial(history[1]));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_CancelledBeforeFirstUpdate_PersistsOnlyRequestAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        var received = await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        Assert.Empty(received);
        var history = GetHistory(agent, session);
        var message = Assert.Single(history);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("Hello", message.Text);
    }

    [Fact]
    public async Task RunStreamingAsync_RunOptionsFalse_OverridesAgentLevelTrueAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("partial", "m1")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, new ChatClientAgentRunOptions { PersistPartialMessagesOnCancellation = false }, cts.Token);

        // Assert
        Assert.Empty(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_RunOptionsTrue_OverridesAgentLevelFalseAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("partial", "m1")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new());
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, new ChatClientAgentRunOptions { PersistPartialMessagesOnCancellation = true }, cts.Token);

        // Assert
        var history = GetHistory(agent, session);
        Assert.Equal(2, history.Count);
        Assert.Equal("partial", history[1].Text);
        Assert.True(IsMarkedAsPartial(history[1]));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_RemovesUnmatchedFunctionCallAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var tool = AIFunctionFactory.Create(() => "Sunny", "GetWeather");
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall(
            [
                TextUpdate("Let me check", "m1"),
                new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call1", "GetWeather")]) { MessageId = "m1" },
            ],
            CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { ChatOptions = new() { Tools = [tool] }, PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        var history = GetHistory(agent, session);
        Assert.Equal(2, history.Count);
        Assert.Equal(ChatRole.User, history[0].Role);
        Assert.Equal(ChatRole.Assistant, history[1].Role);
        Assert.Equal("Let me check", history[1].Text);
        Assert.DoesNotContain(history.SelectMany(m => m.Contents), c => c is FunctionCallContent);
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_KeepsMatchedFunctionCallAndResultAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var tool = AIFunctionFactory.Create(() => "Sunny", "GetWeather");
        var chatClient = new ScriptedStreamingChatClient(
            cts,
            new StreamingCall([new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call1", "GetWeather")]) { MessageId = "m1" }]),
            new StreamingCall([TextUpdate("It is sun", "m2")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { ChatOptions = new() { Tools = [tool] }, PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        AssertToolLoopPartialHistory(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_NonCallerCancellation_DoesNotPersistAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("partial", "m1")], CallEnd.NonCallerCancellation));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        Assert.False(cts.IsCancellationRequested);
        Assert.Empty(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_PersistenceFailure_RethrowsOriginalCancellationAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("partial", "m1")], CallEnd.CallerCancels));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) => new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Throws(new InvalidOperationException("Storage failure"));

        ChatClientAgent agent = new(chatClient, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            PersistPartialMessagesOnCancellation = true,
        });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x => x.InvokeException == null && x.ResponseMessages!.Count() == 1),
                ItExpr.IsAny<CancellationToken>());
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_PerServiceCallPersistence_PersistsEachMessageOnceAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var tool = AIFunctionFactory.Create(() => "Sunny", "GetWeather");
        var chatClient = new ScriptedStreamingChatClient(
            cts,
            new StreamingCall([new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call1", "GetWeather")]) { MessageId = "m1" }]),
            new StreamingCall([TextUpdate("It is sun", "m2")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            RequirePerServiceCallChatHistoryPersistence = true,
            PersistPartialMessagesOnCancellation = true,
        });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        AssertToolLoopPartialHistory(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagDisabled_PerServiceCallPersistence_DoesNotPersistCancelledCallAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var tool = AIFunctionFactory.Create(() => "Sunny", "GetWeather");
        var chatClient = new ScriptedStreamingChatClient(
            cts,
            new StreamingCall([new ChatResponseUpdate(ChatRole.Assistant, [new FunctionCallContent("call1", "GetWeather")]) { MessageId = "m1" }]),
            new StreamingCall([TextUpdate("It is sun", "m2")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            RequirePerServiceCallChatHistoryPersistence = true,
        });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        var history = GetHistory(agent, session);
        Assert.Equal(2, history.Count);
        Assert.Equal(ChatRole.User, history[0].Role);
        Assert.Contains(history[1].Contents, c => c is FunctionCallContent);
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_BackgroundResponses_DoesNotPersistAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([TextUpdate("partial", "m1")], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, new ChatClientAgentRunOptions { AllowBackgroundResponses = true }, cts.Token);

        // Assert
        Assert.Empty(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_ServiceManagedHistory_DoesNotPersistAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(cts, new StreamingCall([new ChatResponseUpdate(ChatRole.Assistant, "partial") { MessageId = "m1", ConversationId = "conv-1" }], CallEnd.CallerCancels));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Assert
        Assert.Null(session.ConversationId);
        Assert.Empty(GetHistory(agent, session));
    }

    [Fact]
    public async Task RunStreamingAsync_FlagEnabled_NextRunIncludesPersistedPartialInteractionAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        var chatClient = new ScriptedStreamingChatClient(
            cts,
            new StreamingCall([TextUpdate("partial", "m1")], CallEnd.CallerCancels),
            new StreamingCall([TextUpdate("complete", "m2")]));
        ChatClientAgent agent = new(chatClient, options: new() { PersistPartialMessagesOnCancellation = true });
        var session = await agent.CreateSessionAsync();
        await ConsumeUntilCancelledAsync(agent, session, null, cts.Token);

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "Continue")], session))
        {
        }

        // Assert
        var secondRequest = chatClient.Requests[1];
        Assert.Equal(["Hello", "partial", "Continue"], secondRequest.Select(m => m.Text));
        Assert.Equal(4, GetHistory(agent, session).Count);
    }

    private static void AssertToolLoopPartialHistory(List<ChatMessage> history)
    {
        Assert.Equal(4, history.Count);
        Assert.Equal(ChatRole.User, history[0].Role);
        Assert.Equal(ChatRole.Assistant, history[1].Role);
        Assert.Equal("call1", Assert.IsType<FunctionCallContent>(Assert.Single(history[1].Contents)).CallId);
        Assert.Equal(ChatRole.Tool, history[2].Role);
        Assert.Equal("call1", Assert.IsType<FunctionResultContent>(Assert.Single(history[2].Contents)).CallId);
        Assert.Equal(ChatRole.Assistant, history[3].Role);
        Assert.Equal("It is sun", history[3].Text);
        Assert.True(IsMarkedAsPartial(history[3]));
    }

    private static async Task<List<AgentResponseUpdate>> ConsumeUntilCancelledAsync(ChatClientAgent agent, AgentSession session, AgentRunOptions? options, CancellationToken cancellationToken)
    {
        List<AgentResponseUpdate> received = [];
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync([new(ChatRole.User, "Hello")], session, options, cancellationToken))
            {
                received.Add(update);
            }
        });

        return received;
    }

    private static List<ChatMessage> GetHistory(ChatClientAgent agent, AgentSession session) =>
        Assert.IsType<InMemoryChatHistoryProvider>(agent.ChatHistoryProvider).GetMessages(session).ToList();

    private static bool IsMarkedAsPartial(ChatMessage message) =>
        message.AdditionalProperties?.TryGetValue(ChatClientAgent.PartialResponseMarkerKey, out var value) is true && value is true;

    private static ChatResponseUpdate TextUpdate(string text, string messageId) =>
        new(ChatRole.Assistant, text) { MessageId = messageId };

    private enum CallEnd
    {
        Complete,
        CallerCancels,
        NonCallerCancellation,
    }

    private sealed record StreamingCall(ChatResponseUpdate[] Updates, CallEnd End = CallEnd.Complete);

    /// <summary>
    /// A chat client that streams scripted updates for each service call and optionally ends the stream
    /// with a cancellation, either triggered on the caller's token or independent of it.
    /// </summary>
    private sealed class ScriptedStreamingChatClient(CancellationTokenSource callerCancellation, params StreamingCall[] calls) : IChatClient
    {
        private int _callIndex;

        public List<List<ChatMessage>> Requests { get; } = [];

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.Requests.Add(messages.ToList());
            var call = calls[this._callIndex++];

            foreach (var update in call.Updates)
            {
                await Task.Yield();
                yield return update;
            }

            switch (call.End)
            {
                case CallEnd.CallerCancels:
                    callerCancellation.Cancel();
                    cancellationToken.ThrowIfCancellationRequested();
                    break;
                case CallEnd.NonCallerCancellation:
                    throw new OperationCanceledException("Cancelled independently of the caller's token.");
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;

        public void Dispose()
        {
        }
    }
}
