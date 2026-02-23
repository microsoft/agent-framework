// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIContextProviderChatClient"/> class and
/// the <see cref="AIContextProviderChatClientBuilderExtensions.UseAIContextProviders(ChatClientBuilder, AIContextProvider[])"/> builder extension.
/// </summary>
public class AIContextProviderChatClientTests
{
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region Constructor Tests

    [Fact]
    public void Constructor_NullInnerClient_ThrowsArgumentNullException()
    {
        // Arrange
        var provider = new TestAIContextProvider("key1");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProviderChatClient(null!, [provider]));
    }

    [Fact]
    public void Constructor_NullProviders_ThrowsArgumentNullException()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProviderChatClient(innerClient, null!));
    }

    [Fact]
    public void Constructor_EmptyProviders_ThrowsArgumentException()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AIContextProviderChatClient(innerClient, []));
    }

    #endregion

    #region GetResponseAsync Tests

    [Fact]
    public async Task GetResponseAsync_NoRunContext_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>();
        var provider = new TestAIContextProvider("key1");
        var chatClient = new AIContextProviderChatClient(innerClient.Object, [provider]);

        // Act & Assert — no AIAgent.CurrentRunContext is set
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hello")]));
    }

    [Fact]
    public async Task GetResponseAsync_SingleProvider_EnrichesMessagesAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockChatClient(
            onGetResponse: (messages, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var provider = new TestAIContextProvider("key1", provideMessages: [new ChatMessage(ChatRole.System, "Extra context")]);
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act — run through an agent so CurrentRunContext is set
        await RunWithAgentContextAsync(chatClient);

        // Assert
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(2, messageList.Count);
        Assert.Equal("Hello", messageList[0].Text);
        Assert.Contains("Extra context", messageList[1].Text);
    }

    [Fact]
    public async Task GetResponseAsync_MultipleProviders_CalledInSequenceAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockChatClient(
            onGetResponse: (messages, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var provider1 = new TestAIContextProvider("key1", provideMessages: [new ChatMessage(ChatRole.System, "From P1")]);
        var provider2 = new TestAIContextProvider("key2", provideMessages: [new ChatMessage(ChatRole.System, "From P2")]);
        var chatClient = new AIContextProviderChatClient(innerClient, [provider1, provider2]);

        // Act
        await RunWithAgentContextAsync(chatClient);

        // Assert
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(3, messageList.Count);
    }

    [Fact]
    public async Task GetResponseAsync_Provider_EnrichesToolsAndInstructionsAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        var innerClient = CreateMockChatClient(
            onGetResponse: (_, options, _) =>
            {
                capturedOptions = options;
                return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var provider = new TestAIContextProvider("key1", provideInstructions: "Extra instructions", provideTools: [new TestAITool()]);
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act
        await RunWithAgentContextAsync(chatClient);

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.Equal("Extra instructions", capturedOptions!.Instructions);
        Assert.Single(capturedOptions.Tools!);
    }

    [Fact]
    public async Task GetResponseAsync_OnSuccess_InvokedAsyncCalledAsync()
    {
        // Arrange
        var innerClient = CreateMockChatClient(
            onGetResponse: (_, _, _) => Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response")])));

        var provider = new TestAIContextProvider("key1");
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act
        await RunWithAgentContextAsync(chatClient);

        // Assert
        Assert.True(provider.InvokedAsyncCalled);
        Assert.Null(provider.LastInvokedContext!.InvokeException);
        Assert.NotNull(provider.LastInvokedContext.ResponseMessages);
    }

    [Fact]
    public async Task GetResponseAsync_OnFailure_InvokedAsyncCalledWithExceptionAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Chat failed");
        var innerClient = CreateMockChatClient(
            onGetResponse: (_, _, _) => throw expectedException);

        var provider = new TestAIContextProvider("key1");
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => RunWithAgentContextAsync(chatClient));

        Assert.True(provider.InvokedAsyncCalled);
        Assert.Same(expectedException, provider.LastInvokedContext!.InvokeException);
    }

    #endregion

    #region GetStreamingResponseAsync Tests

    [Fact]
    public async Task GetStreamingResponseAsync_SingleProvider_EnrichesAndStreamsAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockStreamingChatClient(
            onGetStreamingResponse: (messages, _, _) =>
            {
                capturedMessages = messages;
                return ToAsyncEnumerableAsync(
                    new ChatResponseUpdate(ChatRole.Assistant, "Part1"),
                    new ChatResponseUpdate(ChatRole.Assistant, "Part2"));
            });

        var provider = new TestAIContextProvider("key1", provideMessages: [new ChatMessage(ChatRole.System, "Extra context")]);
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(chatClient, updates);

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.NotNull(capturedMessages);
        Assert.Equal(2, capturedMessages!.ToList().Count);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_OnSuccess_InvokedAsyncCalledAsync()
    {
        // Arrange
        var innerClient = CreateMockStreamingChatClient(
            onGetStreamingResponse: (_, _, _) => ToAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "Response")));

        var provider = new TestAIContextProvider("key1");
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act
        await RunStreamingWithAgentContextAsync(chatClient, []);

        // Assert
        Assert.True(provider.InvokedAsyncCalled);
        Assert.Null(provider.LastInvokedContext!.InvokeException);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_OnFailure_InvokedAsyncCalledWithExceptionAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Stream failed");
        var innerClient = CreateMockStreamingChatClient(
            onGetStreamingResponse: (_, _, _) => throw expectedException);

        var provider = new TestAIContextProvider("key1");
        var chatClient = new AIContextProviderChatClient(innerClient, [provider]);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => RunStreamingWithAgentContextAsync(chatClient, []));

        Assert.True(provider.InvokedAsyncCalled);
        Assert.Same(expectedException, provider.LastInvokedContext!.InvokeException);
    }

    #endregion

    #region Builder Extension Tests

    [Fact]
    public void UseExtension_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        var provider = new TestAIContextProvider("key1");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            AIContextProviderChatClientBuilderExtensions.UseAIContextProviders(null!, provider));
    }

    [Fact]
    public async Task UseExtension_CreatesWorkingPipelineAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockChatClient(
            onGetResponse: (messages, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var provider = new TestAIContextProvider("key1", provideMessages: [new ChatMessage(ChatRole.System, "Pipeline context")]);

        var pipeline = new ChatClientBuilder(innerClient)
            .UseAIContextProviders(provider)
            .Build();

        // Act — wrap in an agent to set CurrentRunContext
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, session, options, ct) =>
            {
                var response = await pipeline.GetResponseAsync(messages, cancellationToken: ct);
                return new AgentResponse(response);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(2, messageList.Count);
    }

    #endregion

    #region Helpers

    /// <summary>
    /// Runs a chat client within an agent context so that AIAgent.CurrentRunContext is set.
    /// </summary>
    private static async Task RunWithAgentContextAsync(AIContextProviderChatClient chatClient)
    {
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, session, options, ct) =>
            {
                var response = await chatClient.GetResponseAsync(messages, cancellationToken: ct);
                return new AgentResponse(response);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);
    }

    /// <summary>
    /// Runs a streaming chat client within an agent context so that AIAgent.CurrentRunContext is set.
    /// </summary>
    private static async Task RunStreamingWithAgentContextAsync(AIContextProviderChatClient chatClient, List<ChatResponseUpdate> updates)
    {
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, session, options, ct) =>
            {
                await foreach (var update in chatClient.GetStreamingResponseAsync(messages, cancellationToken: ct))
                {
                    updates.Add(update);
                }

                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);
    }

    private static IChatClient CreateMockChatClient(
        Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task<ChatResponse>> onGetResponse)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> m, ChatOptions? o, CancellationToken ct) => onGetResponse(m, o, ct));
        return mock.Object;
    }

    private static IChatClient CreateMockStreamingChatClient(
        Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, IAsyncEnumerable<ChatResponseUpdate>> onGetStreamingResponse)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> m, ChatOptions? o, CancellationToken ct) => onGetStreamingResponse(m, o, ct));
        return mock.Object;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableAsync(params ChatResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    /// <summary>
    /// A test AIContextProvider that provides configurable messages, tools, and instructions.
    /// </summary>
    private sealed class TestAIContextProvider : AIContextProvider
    {
        private readonly string _stateKey;
        private readonly IEnumerable<ChatMessage> _provideMessages;
        private readonly string? _provideInstructions;
        private readonly IEnumerable<AITool>? _provideTools;

        public bool InvokedAsyncCalled { get; private set; }

        public InvokedContext? LastInvokedContext { get; private set; }

        public override string StateKey => this._stateKey;

        public TestAIContextProvider(
            string stateKey,
            IEnumerable<ChatMessage>? provideMessages = null,
            string? provideInstructions = null,
            IEnumerable<AITool>? provideTools = null)
        {
            this._stateKey = stateKey;
            this._provideMessages = provideMessages ?? [];
            this._provideInstructions = provideInstructions;
            this._provideTools = provideTools;
        }

        protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            return new ValueTask<AIContext>(new AIContext
            {
                Messages = this._provideMessages,
                Instructions = this._provideInstructions,
                Tools = this._provideTools,
            });
        }

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.InvokedAsyncCalled = true;
            this.LastInvokedContext = context;
            return default;
        }
    }

    /// <summary>
    /// A minimal AITool for testing.
    /// </summary>
    private sealed class TestAITool : AITool;

    #endregion
}
