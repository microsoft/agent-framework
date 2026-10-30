// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// Contains unit tests for the <see cref="PerServiceCallChatHistoryPersistingChatClient"/> decorator,
/// verifying that it persists messages via the <see cref="ChatHistoryProvider"/> after each
/// individual service call by default, or marks messages for end-of-run persistence when the
/// <see cref="ChatClientAgentOptions.RequirePerServiceCallChatHistoryPersistence"/> option is enabled.
/// </summary>
public class PerServiceCallChatHistoryPersistingChatClientTests
{
    [Fact]
    public void PublicContract_ExposesLocalHistoryMarkerWithoutPublicConstructors()
    {
        // Arrange
        Type clientType = typeof(PerServiceCallChatHistoryPersistingChatClient);

        // Act
        var constructors = clientType.GetConstructors();
        var marker = clientType.GetField(nameof(PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId));

        // Assert
        Assert.True(clientType.IsPublic);
        Assert.Empty(constructors);
        Assert.NotNull(marker);
        Assert.True(marker.IsLiteral);
        Assert.Equal("_agent_local_chat_history", marker.GetRawConstantValue());
    }

    /// <summary>
    /// Verifies that by default (RequirePerServiceCallChatHistoryPersistence is false),
    /// the ChatHistoryProvider receives messages after a successful non-streaming call.
    /// </summary>
    [Fact]
    public async Task RunAsync_PersistsMessagesPerServiceCall_ByDefaultAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

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
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — InvokedCoreAsync should be called by the decorator (per service call)
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x =>
                    x.RequestMessages.Any(m => m.Text == "test") &&
                    x.ResponseMessages!.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default),
    /// the ChatHistoryProvider receives messages at the end of the run.
    /// </summary>
    [Fact]
    public async Task RunAsync_PersistsMessagesAtEndOfRun_WhenOptionEnabledAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

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
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — InvokedCoreAsync should be called once by the agent (end of run)
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x =>
                    x.RequestMessages.Any(m => m.Text == "test") &&
                    x.ResponseMessages!.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default) and the service call fails,
    /// the ChatHistoryProvider is notified with the exception.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesProviderOfFailure_WhenPerServiceCallPersistenceActiveAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Service failed");
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ThrowsAsync(expectedException);

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
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));

        // Assert — the decorator should have notified the provider of the failure
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x =>
                    x.InvokeException != null &&
                    x.InvokeException.Message == "Service failed"),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that the decorator is NOT injected by default (RequirePerServiceCallChatHistoryPersistence is false).
    /// </summary>
    [Fact]
    public void ChatClient_DoesNotContainDecorator_ByDefault()
    {
        // Arrange
        Mock<IChatClient> mockService = new();

        // Act
        ChatClientAgent agent = new(mockService.Object, options: new());

        // Assert
        var decorator = agent.ChatClient.GetService<PerServiceCallChatHistoryPersistingChatClient>();
        Assert.Null(decorator);
    }

    /// <summary>
    /// Verifies that the decorator is injected when RequirePerServiceCallChatHistoryPersistence is true.
    /// </summary>
    [Fact]
    public void ChatClient_ContainsDecorator_WhenRequirePerServiceCallChatHistoryPersistence()
    {
        // Arrange
        Mock<IChatClient> mockService = new();

        // Act
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Assert
        var decorator = agent.ChatClient.GetService<PerServiceCallChatHistoryPersistingChatClient>();
        Assert.NotNull(decorator);
    }

    /// <summary>
    /// Verifies that the decorator is NOT injected when UseProvidedChatClientAsIs is true.
    /// </summary>
    [Fact]
    public void ChatClient_DoesNotContainDecorator_WhenUseProvidedChatClientAsIs()
    {
        // Arrange
        Mock<IChatClient> mockService = new();

        // Act
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            UseProvidedChatClientAsIs = true,
        });

        // Assert
        var decorator = agent.ChatClient.GetService<PerServiceCallChatHistoryPersistingChatClient>();
        Assert.Null(decorator);
    }

    /// <summary>
    /// Verifies that the RequirePerServiceCallChatHistoryPersistence option is included in Clone().
    /// </summary>
    [Fact]
    public void ChatClientAgentOptions_Clone_IncludesRequirePerServiceCallChatHistoryPersistence()
    {
        // Arrange
        var options = new ChatClientAgentOptions
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        };

        // Act
        var cloned = options.Clone();

        // Assert
        Assert.True(cloned.RequirePerServiceCallChatHistoryPersistence);
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default) and the service call
    /// involves a function invocation loop, the ChatHistoryProvider is called after each individual
    /// service call (not just once at the end).
    /// </summary>
    [Fact]
    public async Task RunAsync_PersistsPerServiceCall_DuringFunctionInvocationLoopAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    // First call returns a tool call
                    return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])]));
                }

                // Second call returns a final response
                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "final response")]));
            });

        var invokedContexts = new List<ChatHistoryProvider.InvokedContext>();

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
            .Callback((ChatHistoryProvider.InvokedContext ctx, CancellationToken _) => invokedContexts.Add(ctx))
            .Returns(() => new ValueTask());

        // Define a simple tool
        var tool = AIFunctionFactory.Create(() => "tool result", "myTool", "A test tool");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        Exception? caughtException = null;
        try
        {
            await agent.RunAsync([new(ChatRole.User, "test")], session);
        }
        catch (Exception ex)
        {
            caughtException = ex;
        }

        // Diagnostic: check if there was an unexpected exception
        Assert.Null(caughtException);

        // Assert — the decorator should have been called twice (once per service call in the function invocation loop)
        Assert.Equal(2, serviceCallCount);
        Assert.Equal(2, invokedContexts.Count);

        // First invocation should have the user message as request and tool call response
        Assert.NotNull(invokedContexts[0].ResponseMessages);
        var firstRequestMessages = invokedContexts[0].RequestMessages.ToList();
        Assert.Contains(firstRequestMessages, m => m.Text == "test");
        Assert.Contains(invokedContexts[0].ResponseMessages!, m => m.Contents.OfType<FunctionCallContent>().Any());

        // Second invocation: request messages should NOT include the original user message (already notified).
        // It should only include messages added since the first call (assistant tool call + tool result).
        Assert.NotNull(invokedContexts[1].ResponseMessages);
        var secondRequestMessages = invokedContexts[1].RequestMessages.ToList();
        Assert.DoesNotContain(secondRequestMessages, m => m.Text == "test");
        Assert.Contains(invokedContexts[1].ResponseMessages!, m => m.Text == "final response");
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default) with streaming,
    /// the ChatHistoryProvider receives messages after the stream completes.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_PersistsMessagesPerServiceCall_ByDefaultAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(CreateAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "streaming "),
                new ChatResponseUpdate(ChatRole.Assistant, "response")));

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
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "test")], session))
        {
            // Consume stream
        }

        // Assert — InvokedCoreAsync should be called by the decorator
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x =>
                    x.RequestMessages.Any(m => m.Text == "test") &&
                    x.ResponseMessages != null),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default),
    /// AIContextProviders are also notified of new messages after a successful call.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesAIContextProviders_ByDefaultAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestAIContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AIContext>(new AIContext()));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            AIContextProviders = [mockContextProvider.Object],
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — InvokedCoreAsync should be called by the decorator for the AIContextProvider
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                    x.ResponseMessages != null &&
                    x.ResponseMessages.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default) and the service fails,
    /// AIContextProviders are notified of the failure.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesAIContextProvidersOfFailure_ByDefaultAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Service failed");
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ThrowsAsync(expectedException);

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestAIContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AIContext>(new AIContext()));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            AIContextProviders = [mockContextProvider.Object],
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));

        // Assert — the decorator should have notified the AIContextProvider of the failure
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                    x.InvokeException != null &&
                    x.InvokeException.Message == "Service failed"),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active (default),
    /// both ChatHistoryProvider and AIContextProviders are notified together.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesBothProviders_ByDefaultAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

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
            .Returns(() => new ValueTask());

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestAIContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AIContext>(new AIContext()));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            AIContextProviders = [mockContextProvider.Object],
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — both providers should have been notified
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x =>
                    x.ResponseMessages != null &&
                    x.ResponseMessages.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());

        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                    x.ResponseMessages != null &&
                    x.ResponseMessages.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that during a FIC loop, response messages from the first call are not
    /// re-notified as request messages on the second call.
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotReNotifyResponseMessagesAsRequestMessages_DuringFicLoopAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        var assistantToolCallMessage = new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())]);

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    return Task.FromResult(new ChatResponse([assistantToolCallMessage]));
                }

                return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, "final response")]));
            });

        var invokedContexts = new List<ChatHistoryProvider.InvokedContext>();

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
            .Callback((ChatHistoryProvider.InvokedContext ctx, CancellationToken _) => invokedContexts.Add(ctx))
            .Returns(() => new ValueTask());

        var tool = AIFunctionFactory.Create(() => "tool result", "myTool", "A test tool");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.Equal(2, invokedContexts.Count);

        // The assistant tool call message was a response in call 1
        Assert.Contains(invokedContexts[0].ResponseMessages!, m => ReferenceEquals(m, assistantToolCallMessage));

        // It should NOT appear as a request in call 2 (it was already notified as a response)
        var secondRequestMessages = invokedContexts[1].RequestMessages.ToList();
        Assert.DoesNotContain(secondRequestMessages, m => ReferenceEquals(m, assistantToolCallMessage));
    }

    /// <summary>
    /// Verifies that when a failure occurs on the second call in a FIC loop,
    /// only new request messages (not previously notified) are sent in the failure notification.
    /// </summary>
    [Fact]
    public async Task RunAsync_DeduplicatesRequestMessages_OnFailureDuringFicLoopAsync()
    {
        // Arrange
        int serviceCallCount = 0;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                serviceCallCount++;
                if (serviceCallCount == 1)
                {
                    return Task.FromResult(new ChatResponse([new(ChatRole.Assistant, [new FunctionCallContent("call1", "myTool", new Dictionary<string, object?>())])]));
                }

                throw new InvalidOperationException("Service failure on second call");
            });

        var invokedContexts = new List<ChatHistoryProvider.InvokedContext>();

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
            .Callback((ChatHistoryProvider.InvokedContext ctx, CancellationToken _) => invokedContexts.Add(ctx))
            .Returns(() => new ValueTask());

        var tool = AIFunctionFactory.Create(() => "tool result", "myTool", "A test tool");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Tools = [tool] },
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
        }, services: new ServiceCollection().BuildServiceProvider());

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            agent.RunAsync([new(ChatRole.User, "test")], session));

        // Assert — should have 2 notifications: success on call 1, failure on call 2
        Assert.Equal(2, invokedContexts.Count);

        // First notification: success, has user message as request
        Assert.Null(invokedContexts[0].InvokeException);
        Assert.Contains(invokedContexts[0].RequestMessages, m => m.Text == "test");

        // Second notification: failure, should NOT include the user message (already notified)
        Assert.NotNull(invokedContexts[1].InvokeException);
        var failureRequestMessages = invokedContexts[1].RequestMessages.ToList();
        Assert.DoesNotContain(failureRequestMessages, m => m.Text == "test");
    }

    /// <summary>
    /// Verifies that after a successful run with per-service-call persistence, the notified
    /// messages are stamped with the persisted marker so they are not re-notified.
    /// </summary>
    /// <summary>
    /// Verifies that when the inner client returns a real conversation ID,
    /// the session's ConversationId is updated after the run.
    /// </summary>
    [Fact]
    public async Task RunAsync_UpdatesSessionConversationId_WhenServiceReturnsOneAsync()
    {
        // Arrange
        const string ExpectedConversationId = "conv-123";

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")])
            {
                ConversationId = ExpectedConversationId,
            });

        ChatClientAgent agent = new(mockService.Object);

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — session should have the conversation ID returned by the inner client
        Assert.Equal(ExpectedConversationId, session!.ConversationId);
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> CreateAsyncEnumerableAsync(params ChatResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    /// <summary>
    /// Verifies that usage reported by the inner client is surfaced unchanged. This decorator makes
    /// exactly one inner call per invocation and must never drop usage.
    /// </summary>
    [Fact]
    public async Task RunAsync_PassesUsageThroughUnchangedAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")])
            {
                Usage = new UsageDetails { InputTokenCount = 21, OutputTokenCount = 9, TotalTokenCount = 30 },
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var response = await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert
        Assert.NotNull(response.Usage);
        Assert.Equal(21, response.Usage!.InputTokenCount);
        Assert.Equal(9, response.Usage.OutputTokenCount);
        Assert.Equal(30, response.Usage.TotalTokenCount);
    }

    /// <summary>
    /// Verifies that usage streamed by the inner client survives the decorator's streaming pipeline.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_PassesUsageThroughUnchangedAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(CreateAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "response"),
                new ChatResponseUpdate(ChatRole.Assistant, [new UsageContent(new UsageDetails { InputTokenCount = 21, OutputTokenCount = 9, TotalTokenCount = 30 })])));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync([new(ChatRole.User, "test")], session))
        {
            updates.Add(update);
        }

        // Assert
        var response = updates.ToAgentResponse();
        Assert.NotNull(response.Usage);
        Assert.Equal(21, response.Usage!.InputTokenCount);
        Assert.Equal(9, response.Usage.OutputTokenCount);
        Assert.Equal(30, response.Usage.TotalTokenCount);
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is active and no real conversation ID exists,
    /// <see cref="ChatClientAgent"/> sets the <see cref="PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId"/>
    /// sentinel on the chat options and <see cref="PerServiceCallChatHistoryPersistingChatClient"/> strips it before
    /// forwarding to the inner client.
    /// </summary>
    [Fact]
    public async Task RunAsync_SetsAndStripsSentinelConversationId_WhenPerServiceCallPersistenceActiveAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test" },
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")]);

        // Assert — the inner client should NOT see the sentinel conversation ID
        Assert.NotNull(capturedOptions);
        Assert.Null(capturedOptions!.ConversationId);
    }

    /// <summary>
    /// Verifies that the sentinel is NOT set when end-of-run persistence is enabled
    /// (mark-only mode), since the issue only applies to per-service-call persistence.
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotSetSentinel_WhenEndOfRunPersistenceEnabledAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test" },
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")]);

        // Assert — the inner client should see options but NOT the sentinel conversation ID
        Assert.NotNull(capturedOptions);
        Assert.Null(capturedOptions!.ConversationId);
    }

    /// <summary>
    /// Verifies that the sentinel is NOT set when a real conversation ID is already present
    /// on the session (indicating server-side history management).
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotSetSentinel_WhenRealConversationIdExistsAsync()
    {
        // Arrange
        const string RealConversationId = "real-conv-123";
        ChatOptions? capturedOptions = null;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")])
            {
                ConversationId = RealConversationId,
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Create a session with a real conversation ID.
        var session = await agent.CreateSessionAsync(RealConversationId);

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — the inner client should see the real conversation ID, not the sentinel
        Assert.NotNull(capturedOptions);
        Assert.Equal(RealConversationId, capturedOptions!.ConversationId);
    }

    /// <summary>
    /// Verifies that the sentinel is set and stripped correctly in the streaming path.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_SetsAndStripsSentinelConversationId_WhenPerServiceCallPersistenceActiveAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .Returns(CreateAsyncEnumerableAsync(new ChatResponseUpdate(role: ChatRole.Assistant, content: "response")));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test" },
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "test")]))
        {
            // Consume the stream.
        }

        // Assert — the inner client should NOT see the sentinel conversation ID
        Assert.NotNull(capturedOptions);
        Assert.Null(capturedOptions!.ConversationId);
    }

    /// <summary>
    /// Verifies that the session's conversation ID IS set to the sentinel after the run
    /// when simulating service-stored chat history. This allows subsequent runs to
    /// skip provider resolution in the agent (the decorator handles it).
    /// </summary>
    [Fact]
    public async Task RunAsync_SetsSentinelOnSession_WhenRequirePerServiceCallChatHistoryPersistenceActiveAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — session should have the sentinel conversation ID
        Assert.Equal(PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId, session!.ConversationId);
    }

    /// <summary>
    /// Verifies that when simulating service-stored chat history and the service returns
    /// a real <see cref="ChatResponse.ConversationId"/>, the conflict detection in
    /// <see cref="ChatClientAgent.UpdateSessionConversationId"/> throws because both a
    /// <see cref="ChatHistoryProvider"/> and a service-managed ConversationId are present.
    /// </summary>
    [Fact]
    public async Task RunAsync_Throws_WhenServiceReturnsRealConversationIdWithChatHistoryProviderAsync()
    {
        // Arrange
        const string RealConversationId = "service-conv-456";

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

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")])
            {
                ConversationId = RealConversationId,
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act & Assert — conflict detection should throw
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));
    }

    /// <summary>
    /// Verifies that when simulating service-stored chat history and the request carries a real
    /// <see cref="ChatOptions.ConversationId"/>, the decorator skips history loading but still
    /// notifies <see cref="AIContextProvider"/>s on success and updates the session ConversationId.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesProvidersAndUpdatesSession_WhenRequestHasRealConversationIdAsync()
    {
        // Arrange
        const string RealConversationId = "real-conv-request";
        const string ServiceConversationId = "real-conv-response";

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext { Messages = ctx.AIContext.Messages }));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")])
            {
                ConversationId = ServiceConversationId,
            });

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
            AIContextProviders = [mockContextProvider.Object],
        });

        // Create a session with a real conversation ID so it's on chatOptions.
        var session = await agent.CreateSessionAsync(RealConversationId);

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — AIContextProvider.InvokedAsync should have been called
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                    x.RequestMessages.Any(m => m.Text == "test") &&
                    x.ResponseMessages!.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());

        // Assert — session should have the service-returned ConversationId
        Assert.Equal(ServiceConversationId, (session as ChatClientAgentSession)!.ConversationId);
    }

    /// <summary>
    /// Verifies that when simulating service-stored chat history and the request carries a real
    /// <see cref="ChatOptions.ConversationId"/>, the decorator notifies providers of failure
    /// when the inner client throws.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesProvidersOfFailure_WhenRequestHasRealConversationIdAsync()
    {
        // Arrange
        const string RealConversationId = "real-conv-failure";

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext { Messages = ctx.AIContext.Messages }));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("Service error"));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
            AIContextProviders = [mockContextProvider.Object],
        });

        var session = await agent.CreateSessionAsync(RealConversationId);

        // Act & Assert — should throw
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], session));

        // Assert — AIContextProvider.InvokedAsync should have been called with the failure
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<AIContextProvider.InvokedContext>(x => x.InvokeException != null),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that in the streaming path, when the request carries a real
    /// <see cref="ChatOptions.ConversationId"/>, the decorator skips history loading but still
    /// notifies providers and updates the session ConversationId.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_NotifiesProvidersAndUpdatesSession_WhenRequestHasRealConversationIdAsync()
    {
        // Arrange
        const string RealConversationId = "real-conv-streaming";
        const string ServiceConversationId = "service-conv-streaming";

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext { Messages = ctx.AIContext.Messages }));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(CreateAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "streamed") { ConversationId = ServiceConversationId }));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
            AIContextProviders = [mockContextProvider.Object],
        });

        var session = await agent.CreateSessionAsync(RealConversationId);

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "test")], session))
        {
            // Consume all updates.
        }

        // Assert — AIContextProvider.InvokedAsync should have been called
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.IsAny<AIContextProvider.InvokedContext>(),
                ItExpr.IsAny<CancellationToken>());

        // Assert — session should have the service-returned ConversationId
        Assert.Equal(ServiceConversationId, (session as ChatClientAgentSession)!.ConversationId);
    }

    /// <summary>
    /// Verifies that when simulating and the service unexpectedly returns a real
    /// <see cref="ChatResponse.ConversationId"/> (no ConversationId on the request), the decorator
    /// notifies providers and updates the session ConversationId without setting the sentinel.
    /// </summary>
    [Fact]
    public async Task RunAsync_NotifiesProvidersAndUpdatesSession_WhenServiceReturnsUnexpectedConversationIdAsync()
    {
        // Arrange
        const string ServiceConversationId = "unexpected-conv-id";

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext { Messages = ctx.AIContext.Messages }));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")])
            {
                ConversationId = ServiceConversationId,
            });

        // No ChatHistoryProvider — so conflict detection won't throw.
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
            AIContextProviders = [mockContextProvider.Object],
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([new(ChatRole.User, "test")], session);

        // Assert — AIContextProvider.InvokedAsync should have been called
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                    x.ResponseMessages!.Any(m => m.Text == "response")),
                ItExpr.IsAny<CancellationToken>());

        // Assert — session should have the service ConversationId, not the sentinel
        Assert.Equal(ServiceConversationId, session!.ConversationId);
    }

    /// <summary>
    /// Verifies that in the streaming path, when the service returns a real ConversationId mid-stream
    /// (no ConversationId on the request), the decorator notifies providers and updates the session.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_NotifiesProvidersAndUpdatesSession_WhenServiceReturnsUnexpectedConversationIdAsync()
    {
        // Arrange
        const string ServiceConversationId = "unexpected-stream-conv";

        Mock<AIContextProvider> mockContextProvider = new(null, null, null);
        mockContextProvider.SetupGet(p => p.StateKeys).Returns(["TestContextProvider"]);
        mockContextProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext { Messages = ctx.AIContext.Messages }));
        mockContextProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(CreateAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "part1"),
                new ChatResponseUpdate(null, "part2") { ConversationId = ServiceConversationId }));

        // No ChatHistoryProvider — so conflict detection won't throw.
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
            AIContextProviders = [mockContextProvider.Object],
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "test")], session))
        {
            // Consume all updates.
        }

        // Assert — AIContextProvider.InvokedAsync should have been called
        mockContextProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.IsAny<AIContextProvider.InvokedContext>(),
                ItExpr.IsAny<CancellationToken>());

        // Assert — session should have the service ConversationId, not the sentinel
        Assert.Equal(ServiceConversationId, session!.ConversationId);
    }

    /// <summary>
    /// Verifies that when <see cref="ChatOptions.AllowBackgroundResponses"/> is true,
    /// the decorator skips history loading and sentinel setting, letting the agent's
    /// forced end-of-run path handle persistence.
    /// </summary>
    [Fact]
    public async Task RunAsync_SkipsSimulation_WhenAllowBackgroundResponsesAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) => capturedMessages = msgs)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        Mock<ChatHistoryProvider> mockChatHistoryProvider = new(null, null, null);
        mockChatHistoryProvider.SetupGet(p => p.StateKeys).Returns(["TestChatHistoryProvider"]);
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask<IEnumerable<ChatMessage>>>("InvokingCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((ChatHistoryProvider.InvokingContext ctx, CancellationToken _) =>
            {
                // Add a history message to verify it's NOT prepended in this scenario.
                var result = ctx.RequestMessages.ToList();
                result.Insert(0, new ChatMessage(ChatRole.Assistant, "history"));
                return new ValueTask<IEnumerable<ChatMessage>>(result);
            });
        mockChatHistoryProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<ChatHistoryProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync(
            [new(ChatRole.User, "test")],
            session,
            new AgentRunOptions { AllowBackgroundResponses = true });

        // Assert — the inner client should NOT have received history messages
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Single(messageList);
        Assert.Equal("test", messageList[0].Text);

        // Assert — session should NOT have the sentinel (agent handles ConversationId at end-of-run)
        Assert.NotEqual(PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId, session!.ConversationId);
    }

    /// <summary>
    /// Verifies that in the streaming path, when <see cref="ChatOptions.AllowBackgroundResponses"/> is true,
    /// the decorator skips history loading and sentinel setting.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_SkipsSimulation_WhenAllowBackgroundResponsesAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(CreateAsyncEnumerableAsync(new ChatResponseUpdate(ChatRole.Assistant, "response")));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync(
            [new(ChatRole.User, "test")],
            session,
            new AgentRunOptions { AllowBackgroundResponses = true }))
        {
            updates.Add(update);
        }

        // Assert — updates should NOT carry the sentinel ConversationId
        Assert.NotEmpty(updates);

        // Assert — session should NOT have the sentinel
        Assert.NotEqual(PerServiceCallChatHistoryPersistingChatClient.LocalHistoryConversationId, session!.ConversationId);
    }

    /// <summary>
    /// Verifies that when the consumer abandons enumeration early (the streaming enumerator is
    /// disposed before completing — e.g. <c>ToolApprovalAgent.RunStreamingAsync</c> doing a
    /// <c>yield break</c>), the decorator still persists the input messages via its <c>finally</c>
    /// block. This regression-guards the dropped-FunctionResultContent → HTTP 400 bug.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_PersistsInputMessages_WhenConsumerAbandonsEnumerationAsync()
    {
        // Arrange — emit multiple updates so the consumer can break after the first.
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(CreateAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "first "),
                new ChatResponseUpdate(ChatRole.Assistant, "second "),
                new ChatResponseUpdate(ChatRole.Assistant, "third")));

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
        });

        // Act — consumer breaks out after the first update, mirroring ToolApprovalAgent's
        // yield-break-on-approval-required path.
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "frc-input")], session))
        {
            break;
        }

        // Assert — even though the consumer abandoned the stream, the input messages
        // must still have been persisted (so we don't lose function-call/function-result
        // pairings).
        mockChatHistoryProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(),
                ItExpr.Is<ChatHistoryProvider.InvokedContext>(x =>
                    x.RequestMessages.Any(m => m.Text == "frc-input") &&
                    (x.ResponseMessages == null || !x.ResponseMessages.Any()) &&
                    x.InvokeException == null),
                ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verifies that a background run (<see cref="ChatOptions.AllowBackgroundResponses"/>) persists the same
    /// history as end-of-run persistence. The agent forces end-of-run persistence for these runs, so the
    /// decorator must not notify the providers per service call as well.
    /// See https://github.com/microsoft/agent-framework/issues/9793.
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotDuplicateMessages_WhenAllowBackgroundResponsesAsync()
    {
        await AssertSameHistoryAsEndOfRunPersistenceAsync(
            () => CreateNonStreamingService("done"),
            async (agent, session) =>
                await agent.RunAsync([new(ChatRole.User, "Hello")], session, new AgentRunOptions { AllowBackgroundResponses = true }));

        // The scenario itself must persist each message exactly once.
        await AssertHistoryAsync(
            () => CreateNonStreamingService("done"),
            async (agent, session) =>
                await agent.RunAsync([new(ChatRole.User, "Hello")], session, new AgentRunOptions { AllowBackgroundResponses = true }),
            (ChatRole.User, "Hello"),
            (ChatRole.Assistant, "done"));
    }

    /// <summary>
    /// Verifies that a streaming background run (<see cref="ChatOptions.AllowBackgroundResponses"/>) persists
    /// the same history as end-of-run persistence.
    /// See https://github.com/microsoft/agent-framework/issues/9793.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_DoesNotDuplicateMessages_WhenAllowBackgroundResponsesAsync()
    {
        await AssertSameHistoryAsEndOfRunPersistenceAsync(
            () => CreateStreamingService(("done", null)),
            async (agent, session) =>
            {
                await foreach (var _ in agent.RunStreamingAsync(
                    [new(ChatRole.User, "Hello")],
                    session,
                    new AgentRunOptions { AllowBackgroundResponses = true }))
                {
                    // Consume all updates.
                }
            });

        await AssertHistoryAsync(
            () => CreateStreamingService(("done", null)),
            async (agent, session) =>
            {
                await foreach (var _ in agent.RunStreamingAsync(
                    [new(ChatRole.User, "Hello")],
                    session,
                    new AgentRunOptions { AllowBackgroundResponses = true }))
                {
                    // Consume all updates.
                }
            },
            (ChatRole.User, "Hello"),
            (ChatRole.Assistant, "done"));
    }

    /// <summary>
    /// Verifies that a run resumed with a continuation token persists the same history as end-of-run
    /// persistence instead of persisting the input messages a second time.
    /// See https://github.com/microsoft/agent-framework/issues/9793.
    /// </summary>
    [Fact]
    public async Task RunAsync_DoesNotDuplicateMessages_WhenResumedWithContinuationTokenAsync()
    {
        await AssertSameHistoryAsEndOfRunPersistenceAsync(
            () => CreateNonStreamingService("done", ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })),
            async (agent, session) =>
            {
                var response = await agent.RunAsync([new(ChatRole.User, "Hello")], session, new AgentRunOptions { AllowBackgroundResponses = true });
                await agent.RunAsync(session, new AgentRunOptions { ContinuationToken = response.ContinuationToken });
            });
    }

    /// <summary>
    /// Verifies that stopping a stream on the update that carries a continuation token, and then resuming it,
    /// persists the same history as end-of-run persistence. Before the fix the input messages were persisted
    /// by the decorator on the abandoned run and again by the resumed run.
    /// See https://github.com/microsoft/agent-framework/issues/9793.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_DoesNotDuplicateMessages_WhenResumedWithContinuationTokenAsync()
    {
        await AssertSameHistoryAsEndOfRunPersistenceAsync(
            () => CreateStreamingService(("partial", ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })), (" rest", null)),
            ResumeStreamingAfterContinuationTokenAsync);

        await AssertHistoryAsync(
            () => CreateStreamingService(("partial", ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 })), (" rest", null)),
            ResumeStreamingAfterContinuationTokenAsync,
            (ChatRole.User, "Hello"),
            (ChatRole.Assistant, "partial rest"));
    }

    /// <summary>
    /// Verifies that a stream abandoned after an update carrying a continuation token does not persist the
    /// input messages: they are persisted by the resumed run instead, so persisting them here would
    /// duplicate them. See https://github.com/microsoft/agent-framework/issues/9793.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_DoesNotPersistInputMessages_WhenContinuationTokenWasEmittedAsync()
    {
        await AssertHistoryAsync(
            () => CreateStreamingService(("partial", ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }))),
            async (agent, session) =>
            {
                // Consumer abandons the stream right after the continuation-token update.
                await foreach (var _ in agent.RunStreamingAsync([new(ChatRole.User, "Hello")], session))
                {
                    break;
                }
            });
    }

    /// <summary>
    /// Stops a streaming run on the update carrying the continuation token and resumes it with that token.
    /// </summary>
    private static async Task ResumeStreamingAfterContinuationTokenAsync(ChatClientAgent agent, AgentSession session)
    {
        ResponseContinuationToken? continuationToken = null;
        await foreach (var update in agent.RunStreamingAsync([new(ChatRole.User, "Hello")], session))
        {
            continuationToken = update.ContinuationToken;
            break;
        }

        Assert.NotNull(continuationToken);

        await foreach (var _ in agent.RunStreamingAsync(session, new AgentRunOptions { ContinuationToken = continuationToken }))
        {
            // Consume all updates.
        }
    }

    /// <summary>
    /// Runs the same scenario with per-service-call persistence and with end-of-run persistence, and asserts
    /// that both configurations produce exactly the same chat history.
    /// </summary>
    private static async Task AssertSameHistoryAsEndOfRunPersistenceAsync(
        Func<IChatClient> createChatClient,
        Func<ChatClientAgent, AgentSession, Task> scenario)
    {
        string perServiceCallHistory = await RunAsync(requirePerServiceCallPersistence: true);
        string endOfRunHistory = await RunAsync(requirePerServiceCallPersistence: false);

        Assert.Equal(endOfRunHistory, perServiceCallHistory);

        async Task<string> RunAsync(bool requirePerServiceCallPersistence)
        {
            ChatClientAgent agent = new(createChatClient(), options: new()
            {
                RequirePerServiceCallChatHistoryPersistence = requirePerServiceCallPersistence,
            });

            var session = await agent.CreateSessionAsync();
            await scenario(agent, session);

            return DescribeHistory(agent, session);
        }
    }

    /// <summary>
    /// Asserts that the agent's chat history contains exactly the specified messages, in order.
    /// </summary>
    private static async Task AssertHistoryAsync(
        Func<IChatClient> createChatClient,
        Func<ChatClientAgent, AgentSession, Task> scenario,
        params (ChatRole Role, string Text)[] expected)
    {
        ChatClientAgent agent = new(createChatClient(), options: new()
        {
            RequirePerServiceCallChatHistoryPersistence = true,
        });

        var session = await agent.CreateSessionAsync();
        await scenario(agent, session);

        var expectedDescription = string.Join(", ", expected.Select(e => $"{e.Role}:\"{e.Text}\""));
        Assert.Equal(expectedDescription, DescribeHistory(agent, session));
    }

    private static string DescribeHistory(ChatClientAgent agent, AgentSession? session)
    {
        var provider = Assert.IsType<InMemoryChatHistoryProvider>(agent.ChatHistoryProvider);
        return string.Join(", ", provider.GetMessages(session).Select(m => $"{m.Role}:\"{m.Text}\""));
    }

    /// <summary>
    /// Creates a service that returns a single non-streaming response, optionally with a continuation token.
    /// </summary>
    private static IChatClient CreateNonStreamingService(string responseText, ResponseContinuationToken? continuationToken = null)
    {
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, responseText)])
            {
                ContinuationToken = continuationToken,
            });

        return mockService.Object;
    }

    /// <summary>
    /// Creates a service that streams one response per call, returning the specified text and continuation
    /// token for each successive call. All updates share the same message id so that resumed responses are
    /// coalesced into a single message.
    /// </summary>
    private static IChatClient CreateStreamingService(params (string Text, ResponseContinuationToken? ContinuationToken)[] responses)
    {
        int callCount = 0;
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                var (text, continuationToken) = responses[Math.Min(callCount++, responses.Length - 1)];
                return CreateAsyncEnumerableAsync(new ChatResponseUpdate(ChatRole.Assistant, text)
                {
                    MessageId = "m1",
                    ContinuationToken = continuationToken,
                });
            });

        return mockService.Object;
    }
}
