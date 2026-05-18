// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for <see cref="MessageInjectingChatClient"/>.
/// </summary>
public class MessageInjectingChatClientTests
{
    /// <summary>
    /// Verifies that <see cref="MessageInjectingChatClient"/> is resolvable via GetService when the decorator is active.
    /// </summary>
    [Fact]
    public void GetService_ReturnsMessageInjectingChatClient_WhenDecoratorActive()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        });

        // Act
        var injector = agent.ChatClient.GetService<MessageInjectingChatClient>();

        // Assert
        Assert.NotNull(injector);
    }

    /// <summary>
    /// Verifies that <see cref="MessageInjectingChatClient"/> is null when the decorator is not active.
    /// </summary>
    [Fact]
    public void GetService_ReturnsNull_WhenDecoratorNotActive()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatClientAgent agent = new(mockService.Object, options: new());

        // Act
        var injector = agent.ChatClient.GetService<MessageInjectingChatClient>();

        // Assert
        Assert.Null(injector);
    }

    /// <summary>
    /// Verifies that messages enqueued on the session before RunAsync are included in the service call messages.
    /// </summary>
    [Fact]
    public async Task RunAsync_IncludesInjectedMessages_WhenEnqueuedBeforeCallAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken _) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        });

        // Create session and enqueue a message directly onto the session's StateBag queue before calling RunAsync
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var queue = new List<ChatMessage>();
        queue.Add(new ChatMessage(ChatRole.User, "injected message"));
        session!.StateBag.SetValue("MessageInjectingChatClient.PendingInjectedMessages", queue);

        // Act
        await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert — the service should have received both the original and injected messages
        Assert.Contains(capturedMessages, m => m.Text == "original");
        Assert.Contains(capturedMessages, m => m.Text == "injected message");
    }

    /// <summary>
    /// Verifies that the queue is drained after a call (messages are not re-delivered on subsequent calls).
    /// </summary>
    [Fact]
    public async Task RunAsync_DrainsQueue_MessagesNotRedeliveredAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken _) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        });

        // Create session and enqueue a message directly onto the session's StateBag queue
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var queue = new List<ChatMessage>();
        queue.Add(new ChatMessage(ChatRole.User, "injected once"));
        session!.StateBag.SetValue("MessageInjectingChatClient.PendingInjectedMessages", queue);

        // Act
        await agent.RunAsync([new(ChatRole.User, "first call")], session);

        // Assert — the injected message was included in the service call
        Assert.Contains(capturedMessages, m => m.Text == "injected once");

        // Assert — the session's queue is now empty (drained)
        Assert.Empty(queue);
    }

    /// <summary>
    /// Verifies that the internal loop fires when no actionable FunctionCallContent is returned
    /// but there are pending injected messages in the queue.
    /// </summary>
    [Fact]
    public async Task RunAsync_LoopsInternally_WhenNoActionableFCCButPendingMessagesAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        Mock<IChatClient> mockService = new();
        MessageInjectingChatClient? injectorRef = null;
        ChatClientAgentSession? sessionRef = null;

        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken _) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // First call — simulate that something enqueues a message (e.g., a provider or background task)
                    injectorRef!.EnqueueMessages(sessionRef!, [new ChatMessage(ChatRole.User, "injected during first call")]);
                }

                // Return a plain text response (no FunctionCallContent) to trigger the internal loop
                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, $"response {serviceCallCount}")]));
            });

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        });

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert — should have made 2 service calls (internal loop triggered by the injected message)
        Assert.Equal(2, serviceCallCount);
    }

    /// <summary>
    /// Verifies that the internal loop does NOT fire when the response contains actionable
    /// FunctionCallContent, even if there are pending injected messages.
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotLoopInternally_WhenActionableFCCPresentAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        Mock<IChatClient> mockService = new();
        MessageInjectingChatClient? injectorRef = null;
        ChatClientAgentSession? sessionRef = null;

        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken _) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // Enqueue a message during the first call
                    injectorRef!.EnqueueMessages(sessionRef!, [new ChatMessage(ChatRole.User, "injected")]);
                    // Return a response with an actionable FunctionCallContent
                    return Task.FromResult(new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])]));
                }

                // Subsequent calls return plain text (the FCC loop will call back after tool execution)
                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "final")]));
            });

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        var tool = AIFunctionFactory.Create(() => "tool result", "myTool", "A test tool");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert — The first service call returned actionable FCC, so no internal injected-message loop
        // occurred there. The FCC loop invokes the tool and calls the service again (second call).
        // The injected message should be picked up by the second service call (drained at start of
        // GetResponseAsync), but no extra internal loop should fire. Exactly 2 service calls expected.
        Assert.Equal(2, serviceCallCount);
    }

    /// <summary>
    /// Verifies that the internal loop fires when the response contains only InformationalOnly
    /// FunctionCallContent (which are not actionable) and there are pending injected messages.
    /// </summary>
    [Fact]
    public async Task RunAsync_LoopsInternally_WhenOnlyInformationalOnlyFCCAndPendingMessagesAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        Mock<IChatClient> mockService = new();
        MessageInjectingChatClient? injectorRef = null;
        ChatClientAgentSession? sessionRef = null;

        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken _) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // Enqueue a message during the first call
                    injectorRef!.EnqueueMessages(sessionRef!, [new ChatMessage(ChatRole.User, "injected")]);
                    // Return a response with InformationalOnly FCC (not actionable)
                    return Task.FromResult(new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>()) { InformationalOnly = true }])]));
                }

                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "final")]));
            });

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        });

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert — InformationalOnly FCC is NOT actionable, so internal loop should trigger
        Assert.Equal(2, serviceCallCount);
    }

    /// <summary>
    /// Verifies that when the inner client returns a ConversationId on the first call, the
    /// MessageInjectingChatClient propagates it to options on subsequent loop iterations.
    /// </summary>
    [Fact]
    public async Task RunAsync_PropagatesConversationId_AcrossInternalLoopIterationsAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        List<string?> capturedConversationIds = [];
        MessageInjectingChatClient? injectorRef = null;
        ChatClientAgentSession? sessionRef = null;

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> _, ChatOptions? opts, CancellationToken _) =>
            {
                serviceCallCount++;
                capturedConversationIds.Add(opts?.ConversationId);

                if (serviceCallCount == 1)
                {
                    // First call: inject a message and return a ConversationId
                    injectorRef!.EnqueueMessages(sessionRef!, [new ChatMessage(ChatRole.User, "injected")]);
                    return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "first response")])
                    {
                        ConversationId = "conv-123",
                    });
                }

                // Second call (from loop): should have the propagated ConversationId
                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "second response")]));
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        await agent.RunAsync([new(ChatRole.User, "hello")], session);

        // Assert — The second call should have received the ConversationId propagated from the first response
        Assert.Equal(2, serviceCallCount);
        Assert.Null(capturedConversationIds[0]); // First call: no ConversationId yet
        Assert.Equal("conv-123", capturedConversationIds[1]); // Second call: propagated from first response
    }

    /// <summary>
    /// Verifies that a session with pending injected messages can be serialized and deserialized,
    /// and that the deserialized session correctly delivers the injected messages on the next run.
    /// </summary>
    [Fact]
    public async Task RunAsync_DeliversInjectedMessages_AfterSessionSerializationRoundTripAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessagesFirstRun = [];
        List<ChatMessage> capturedMessagesSecondRun = [];
        int runCount = 0;
        Mock<IChatClient> mockService = new();
        MessageInjectingChatClient? injectorRef = null;
        ChatClientAgentSession? sessionRef = null;

        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken _) =>
            {
                if (runCount == 1)
                {
                    capturedMessagesFirstRun.AddRange(msgs);

                    // Inject a message during the first run — this will remain pending (not drained)
                    // because we return an actionable FCC that causes the parent loop to take over.
                    injectorRef!.EnqueueMessages(sessionRef!, [new ChatMessage(ChatRole.User, "injected before serialization")]);

                    // Return actionable FCC so the injection loop does NOT drain the message
                    return Task.FromResult(new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])]));
                }

                // Second run (after deserialization) — capture what messages come through
                capturedMessagesSecondRun.AddRange(msgs);
                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "final response")]));
            });

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<IEnumerable<ChatMessage>>(ctx.RequestMessages.ToList()));
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        var tool = AIFunctionFactory.Create(() => "tool result", "myTool", "A test tool");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act — First run: inject a message that stays pending
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        runCount = 1;
        await agent.RunAsync([new(ChatRole.User, "first run message")], session);

        // Serialize the session and deserialize into a new instance
        var serialized = await agent.SerializeSessionAsync(session!);
        var deserializedSession = await agent.DeserializeSessionAsync(serialized) as ChatClientAgentSession;

        // Second run on the deserialized session — the injected message should be delivered
        runCount = 2;
        sessionRef = deserializedSession;
        await agent.RunAsync([new(ChatRole.User, "second run message")], deserializedSession);

        // Assert — the second run should include the injected message from before serialization
        Assert.Contains(capturedMessagesSecondRun, m => m.Text == "injected before serialization");
        Assert.Contains(capturedMessagesSecondRun, m => m.Text == "second run message");
    }
}
