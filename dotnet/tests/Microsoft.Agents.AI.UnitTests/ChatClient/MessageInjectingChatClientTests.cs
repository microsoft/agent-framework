// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // First call — simulate that something enqueues a message (e.g., a provider or background task)
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, "injected during first call")], ct);
                }

                // Return a plain text response (no FunctionCallContent) to trigger the internal loop
                return new ChatResponse([new(ChatRole.Assistant, $"response {serviceCallCount}")]);
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // Enqueue a message during the first call
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, "injected")], ct);
                    // Return a response with an actionable FunctionCallContent
                    return new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])]);
                }

                // Subsequent calls return plain text (the FCC loop will call back after tool execution)
                return new ChatResponse([new(ChatRole.Assistant, "final")]);
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
    /// Verifies that usage is aggregated when an actionable <see cref="FunctionCallContent"/> exits the
    /// injected-message loop on a later iteration.
    /// </summary>
    [Fact]
    public async Task RunAsync_ActionableFCCOnLaterIteration_AggregatesUsageAcrossInjectedLoopExitAsync()
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, "injected")], ct);
                    return new ChatResponse([new(ChatRole.Assistant, "queued")]) { Usage = CreateUsageForCall(serviceCallCount) };
                }

                if (serviceCallCount == 2)
                {
                    return new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])])
                    {
                        Usage = CreateUsageForCall(serviceCallCount)
                    };
                }

                return new ChatResponse([new(ChatRole.Assistant, "final")]) { Usage = CreateUsageForCall(serviceCallCount) };
            });

        var tool = AIFunctionFactory.Create(() => "tool result", "myTool", "A test tool");
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            RequirePerServiceCallChatHistoryPersistence = true,
            EnableMessageInjection = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        var response = await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert
        Assert.Equal(3, serviceCallCount);
        Assert.Equal("final", response.Text);
        Assert.NotNull(response.Usage);
        Assert.Equal(42, response.Usage!.InputTokenCount);
        Assert.Equal(15, response.Usage.OutputTokenCount);
        Assert.Equal(57, response.Usage.TotalTokenCount);
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // Enqueue a message during the first call
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, "injected")], ct);
                    // Return a response with InformationalOnly FCC (not actionable)
                    return new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>()) { InformationalOnly = true }])]);
                }

                return new ChatResponse([new(ChatRole.Assistant, "final")]);
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
            .Returns(async (IEnumerable<ChatMessage> _, ChatOptions? opts, CancellationToken ct) =>
            {
                serviceCallCount++;
                capturedConversationIds.Add(opts?.ConversationId);

                if (serviceCallCount == 1)
                {
                    // First call: inject a message and return a ConversationId
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, "injected")], ct);
                    return new ChatResponse([new(ChatRole.Assistant, "first response")])
                    {
                        ConversationId = "conv-123",
                    };
                }

                // Second call (from loop): should have the propagated ConversationId
                return new ChatResponse([new(ChatRole.Assistant, "second response")]);
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                if (runCount == 1)
                {
                    capturedMessagesFirstRun.AddRange(msgs);

                    // Inject a message during the first run — this will remain pending (not drained)
                    // because we return an actionable FCC that causes the parent loop to take over.
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, "injected before serialization")], ct);

                    // Return actionable FCC so the injection loop does NOT drain the message
                    return new ChatResponse([new(ChatRole.Assistant,
                        [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])]);
                }

                // Second run (after deserialization) — capture what messages come through
                capturedMessagesSecondRun.AddRange(msgs);
                return new ChatResponse([new(ChatRole.Assistant, "final response")]);
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

    /// <summary>
    /// Verifies that concurrent <see cref="MessageInjectingChatClient.EnqueueMessagesAsync"/> calls on the same
    /// session do not lose messages. This guards against the queue-creation race where two callers could
    /// each create a separate backing queue and one overwrites the other.
    /// </summary>
    [Fact]
    public async Task EnqueueMessages_ConcurrentEnqueues_DoesNotLoseMessagesAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        });

        var injector = agent.ChatClient.GetService<MessageInjectingChatClient>();
        Assert.NotNull(injector);

        var session = await agent.CreateSessionAsync();

        const int ThreadCount = 16;
        const int MessagesPerThread = 100;

        // Release all threads at once to maximize the chance of hitting the queue-creation race.
        using var barrier = new Barrier(ThreadCount);
        var tasks = new List<Task>(ThreadCount);
        for (int t = 0; t < ThreadCount; t++)
        {
            int threadIndex = t;
            tasks.Add(Task.Run(async () =>
            {
                barrier.SignalAndWait();
                for (int i = 0; i < MessagesPerThread; i++)
                {
                    await injector!.EnqueueMessagesAsync(session, [new ChatMessage(ChatRole.User, $"{threadIndex}-{i}")]);
                }
            }));
        }

        // Act
        await Task.WhenAll(tasks);

        // Assert — every enqueued message must be present (none lost to a creation race).
        IReadOnlyList<ChatMessage> pending = await injector!.GetPendingMessagesAsync(session);
        Assert.Equal(ThreadCount * MessagesPerThread, pending.Count);
    }

    /// <summary>
    /// Verifies that usage from every internal loop iteration is summed into the returned response,
    /// rather than only the final service call's usage being reported.
    /// </summary>
    [Fact]
    public async Task RunAsync_LoopsInternally_AggregatesUsageAcrossIterationsAsync()
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                if (serviceCallCount < 3)
                {
                    // Enqueue a message so the injection loop runs again.
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, $"injected {serviceCallCount}")], ct);
                }

                return new ChatResponse([new(ChatRole.Assistant, $"response {serviceCallCount}")])
                {
                    Usage = CreateUsageForCall(serviceCallCount),
                };
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        });

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        var response = await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert
        Assert.Equal(3, serviceCallCount);
        Assert.NotNull(response.Usage);
        Assert.Equal(42, response.Usage!.InputTokenCount);
        Assert.Equal(15, response.Usage.OutputTokenCount);
        Assert.Equal(57, response.Usage.TotalTokenCount);
    }

    /// <summary>
    /// Verifies that a derived <see cref="ChatResponse"/> returned by the underlying client survives the
    /// injection loop. Aggregated usage is reported by updating the client's own response rather than by
    /// building a replacement, so a subclass keeps its runtime type and the state it carries.
    /// </summary>
    [Fact]
    public async Task RunAsync_InnerClientReturnsDerivedResponse_PreservesRuntimeTypeWhileAggregatingUsageAsync()
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
            .Returns(async (IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                if (serviceCallCount < 3)
                {
                    // Enqueue a message so the injection loop runs again.
                    await injectorRef!.EnqueueMessagesAsync(sessionRef!, [new ChatMessage(ChatRole.User, $"injected {serviceCallCount}")], ct);
                }

                return new TestDerivedChatResponse([new(ChatRole.Assistant, $"response {serviceCallCount}")])
                {
                    DerivedState = $"call {serviceCallCount}",
                    Usage = new UsageDetails { InputTokenCount = serviceCallCount, OutputTokenCount = serviceCallCount * 10 },
                };
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        });

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        var response = await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert — the underlying response type reaches the caller intact, carrying the whole run's usage.
        Assert.Equal(3, serviceCallCount);
        var derived = Assert.IsType<TestDerivedChatResponse>(response.RawRepresentation);
        Assert.Equal("call 3", derived.DerivedState);
        Assert.Equal(1 + 2 + 3, derived.Usage!.InputTokenCount);
        Assert.Equal(10 + 20 + 30, derived.Usage.OutputTokenCount);
    }

    /// <summary>
    /// Verifies that a single service call surfaces its usage unchanged and that the underlying
    /// client's usage instance is not mutated.
    /// </summary>
    [Fact]
    public async Task RunAsync_SingleServiceCall_SurfacesUsageWithoutMutatingServiceUsageAsync()
    {
        // Arrange
        UsageDetails serviceUsage = new() { InputTokenCount = 12, OutputTokenCount = 3, TotalTokenCount = 15 };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "done")]) { Usage = serviceUsage });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var response = await agent.RunAsync([new(ChatRole.User, "original")], session);

        // Assert
        Assert.NotNull(response.Usage);
        Assert.NotSame(serviceUsage, response.Usage);
        Assert.Equal(12, response.Usage!.InputTokenCount);
        Assert.Equal(3, response.Usage.OutputTokenCount);
        Assert.Equal(15, response.Usage.TotalTokenCount);
        Assert.Equal(12, serviceUsage.InputTokenCount);
        Assert.Equal(3, serviceUsage.OutputTokenCount);
        Assert.Equal(15, serviceUsage.TotalTokenCount);
    }

    /// <summary>
    /// Verifies that the streaming path surfaces usage from every internal loop iteration so an
    /// aggregated response reports the usage of all service calls.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_LoopsInternally_SurfacesUsageFromEveryIterationAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        Mock<IChatClient> mockService = new();
        MessageInjectingChatClient? injectorRef = null;
        ChatClientAgentSession? sessionRef = null;

        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> msgs, ChatOptions? _, CancellationToken ct) =>
            {
                serviceCallCount++;
                int call = serviceCallCount;
                return StreamWithUsageAsync(call, injectorRef!, sessionRef!, ct);
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            EnableMessageInjection = true,
        });

        injectorRef = agent.ChatClient.GetService<MessageInjectingChatClient>()!;

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        sessionRef = session;
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync([new(ChatRole.User, "original")], session))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(3, serviceCallCount);
        var response = updates.ToAgentResponse();
        Assert.NotNull(response.Usage);
        Assert.Equal(42, response.Usage!.InputTokenCount);
        Assert.Equal(15, response.Usage.OutputTokenCount);
        Assert.Equal(57, response.Usage.TotalTokenCount);
    }

    /// <summary>
    /// Creates distinct usage values for a service call so aggregation tests cannot pass by multiplying
    /// the final usage by the call count.
    /// </summary>
    private static UsageDetails CreateUsageForCall(int call)
        => new()
        {
            InputTokenCount = call is 1 ? 2 : call is 2 ? 11 : 29,
            OutputTokenCount = call is 1 ? 3 : call is 2 ? 5 : 7,
            TotalTokenCount = call is 1 ? 5 : call is 2 ? 16 : 36,
        };

    /// <summary>
    /// Streams a text update followed by a usage update, enqueuing an injected message on the first two
    /// calls so the injection loop runs three times in total.
    /// </summary>
    private static async IAsyncEnumerable<ChatResponseUpdate> StreamWithUsageAsync(
        int call,
        MessageInjectingChatClient injector,
        ChatClientAgentSession session,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        if (call < 3)
        {
            await injector.EnqueueMessagesAsync(session, [new ChatMessage(ChatRole.User, $"injected {call}")], cancellationToken);
        }

        yield return new ChatResponseUpdate(ChatRole.Assistant, $"response {call}");
        yield return new ChatResponseUpdate(ChatRole.Assistant, [new UsageContent(CreateUsageForCall(call))]);
    }
}
