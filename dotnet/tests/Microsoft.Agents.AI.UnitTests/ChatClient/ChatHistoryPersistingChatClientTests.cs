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
/// Contains unit tests for the <see cref="ChatHistoryPersistingChatClient"/> decorator,
/// verifying that it persists messages via the <see cref="ChatHistoryProvider"/> after each
/// individual service call by default, or marks messages for end-of-run persistence when the
/// <see cref="ChatClientAgentOptions.PersistChatHistoryAtEndOfRun"/> option is enabled.
/// </summary>
public class ChatHistoryPersistingChatClientTests
{
    /// <summary>
    /// Verifies that by default (PersistChatHistoryAtEndOfRun is false),
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = true,
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
            PersistChatHistoryAtEndOfRun = false,
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
    /// Verifies that the decorator is injected in persist mode by default
    /// and can be discovered via GetService.
    /// </summary>
    [Fact]
    public void ChatClient_ContainsDecorator_InPersistMode_ByDefault()
    {
        // Arrange
        Mock<IChatClient> mockService = new();

        // Act
        ChatClientAgent agent = new(mockService.Object, options: new());

        // Assert
        var decorator = agent.ChatClient.GetService<ChatHistoryPersistingChatClient>();
        Assert.NotNull(decorator);
        Assert.False(decorator.MarkOnly);
    }

    /// <summary>
    /// Verifies that the decorator is injected in mark-only mode when PersistChatHistoryAtEndOfRun is true.
    /// </summary>
    [Fact]
    public void ChatClient_ContainsDecorator_InMarkOnlyMode_WhenPersistAtEndOfRun()
    {
        // Arrange
        Mock<IChatClient> mockService = new();

        // Act
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            PersistChatHistoryAtEndOfRun = true,
        });

        // Assert
        var decorator = agent.ChatClient.GetService<ChatHistoryPersistingChatClient>();
        Assert.NotNull(decorator);
        Assert.True(decorator.MarkOnly);
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
        var decorator = agent.ChatClient.GetService<ChatHistoryPersistingChatClient>();
        Assert.Null(decorator);
    }

    /// <summary>
    /// Verifies that the PersistChatHistoryAtEndOfRun option is included in Clone().
    /// </summary>
    [Fact]
    public void ChatClientAgentOptions_Clone_IncludesPersistChatHistoryAtEndOfRun()
    {
        // Arrange
        var options = new ChatClientAgentOptions
        {
            PersistChatHistoryAtEndOfRun = true,
        };

        // Act
        var cloned = options.Clone();

        // Assert
        Assert.True(cloned.PersistChatHistoryAtEndOfRun);
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = false,
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
            PersistChatHistoryAtEndOfRun = false,
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
    [Fact]
    public async Task RunAsync_MarksNotifiedMessages_WithPersistedMarkerAsync()
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

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = mockChatHistoryProvider.Object,
            PersistChatHistoryAtEndOfRun = false,
        });

        // Act
        var inputMessage = new ChatMessage(ChatRole.User, "test");
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync([inputMessage], session);

        // Assert — input message should be marked as persisted
        Assert.True(
            inputMessage.AdditionalProperties?.ContainsKey(ChatHistoryPersistingChatClient.PersistedMarkerKey) == true,
            "Input message should be marked as persisted after a successful run.");
    }

    /// <summary>
    /// Verifies that when per-service-call persistence is enabled and the inner client returns a
    /// conversation ID, the session's ConversationId is updated after the service call.
    /// </summary>
    [Fact]
    public async Task RunAsync_UpdatesSessionConversationId_WhenPerServiceCallPersistenceEnabledAsync()
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

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            PersistChatHistoryAtEndOfRun = false,
        });

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
}
