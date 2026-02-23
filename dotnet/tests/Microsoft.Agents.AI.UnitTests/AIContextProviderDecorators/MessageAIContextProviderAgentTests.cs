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
/// Unit tests for the <see cref="MessageAIContextProviderAgent"/> class and
/// the <see cref="AIAgentBuilder.UseAIContextProviders(MessageAIContextProvider[])"/> builder extension.
/// </summary>
public class MessageAIContextProviderAgentTests
{
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region Constructor Tests

    [Fact]
    public void Constructor_NullInnerAgent_ThrowsArgumentNullException()
    {
        // Arrange
        var provider = new TestProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new MessageAIContextProviderAgent(null!, [provider]));
    }

    [Fact]
    public void Constructor_NullProviders_ThrowsArgumentNullException()
    {
        // Arrange
        var agent = CreateTestAgent();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new MessageAIContextProviderAgent(agent, null!));
    }

    [Fact]
    public void Constructor_EmptyProviders_ThrowsArgumentOutOfRangeException()
    {
        // Arrange
        var agent = CreateTestAgent();

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new MessageAIContextProviderAgent(agent, []));
    }

    #endregion

    #region RunAsync Tests

    [Fact]
    public async Task RunAsync_SingleProvider_EnrichesMessagesAndDelegatesToInnerAgentAsync()
    {
        // Arrange
        var contextMessage = new ChatMessage(ChatRole.System, "Extra context");
        var provider = new TestProvider(provideMessages: [contextMessage]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerAgent = CreateTestAgent(
            runFunc: (messages, _, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert - inner agent received enriched messages (input + provider's message)
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(2, messageList.Count);
        Assert.Equal("Hello", messageList[0].Text);
        Assert.Contains("Extra context", messageList[1].Text);
    }

    [Fact]
    public async Task RunAsync_MultipleProviders_CalledInSequenceAsync()
    {
        // Arrange
        var provider1 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "From provider 1")]);
        var provider2 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "From provider 2")]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerAgent = CreateTestAgent(
            runFunc: (messages, _, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider1, provider2]);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert - inner agent received messages from both providers in sequence
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(3, messageList.Count);
        Assert.Equal("Hello", messageList[0].Text);
        Assert.Contains("From provider 1", messageList[1].Text);
        Assert.Contains("From provider 2", messageList[2].Text);
    }

    [Fact]
    public async Task RunAsync_SequentialProviders_EachReceivesPreviousOutputAsync()
    {
        // Arrange - provider 2 captures the filtered messages it receives in ProvideMessagesAsync.
        // The default filter only includes External messages, so provider 1's stamped messages
        // (marked as AIContextProvider) are filtered out before reaching provider 2's ProvideMessagesAsync.
        // However, the full unfiltered output from provider 1 is passed to provider 2's InvokingAsync,
        // and the inner agent receives the full merged output from both providers.
        IEnumerable<ChatMessage>? provider2ReceivedMessages = null;
        var provider1 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "From provider 1")]);
        var provider2 = new TestProvider(
            provideMessages: [new ChatMessage(ChatRole.System, "From provider 2")],
            onInvoking: messages => provider2ReceivedMessages = messages.ToList());

        var innerAgent = CreateTestAgent(
            runFunc: (_, _, _, _) => Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Response")])));

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider1, provider2]);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert - provider 2's ProvideMessagesAsync received only External messages (filtered)
        Assert.NotNull(provider2ReceivedMessages);
        var received = provider2ReceivedMessages!.ToList();
        Assert.Single(received);
        Assert.Equal("Hello", received[0].Text);
    }

    [Fact]
    public async Task RunAsync_OnSuccess_InvokedAsyncCalledOnAllProvidersAsync()
    {
        // Arrange
        var provider1 = new TestProvider();
        var provider2 = new TestProvider();
        var innerAgent = CreateTestAgent(
            runFunc: (_, _, _, _) => Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Response")])));

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider1, provider2]);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert
        Assert.True(provider1.InvokedAsyncCalled);
        Assert.True(provider2.InvokedAsyncCalled);
        Assert.Null(provider1.LastInvokedContext!.InvokeException);
        Assert.Null(provider2.LastInvokedContext!.InvokeException);
    }

    [Fact]
    public async Task RunAsync_OnFailure_InvokedAsyncCalledWithExceptionAsync()
    {
        // Arrange
        var provider = new TestProvider();
        var expectedException = new InvalidOperationException("Agent failed");
        var innerAgent = CreateTestAgent(
            runFunc: (_, _, _, _) => throw expectedException);

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession));

        Assert.True(provider.InvokedAsyncCalled);
        Assert.Same(expectedException, provider.LastInvokedContext!.InvokeException);
    }

    [Fact]
    public async Task RunAsync_OnSuccess_InvokedContextContainsResponseMessagesAsync()
    {
        // Arrange
        var provider = new TestProvider();
        var responseMessage = new ChatMessage(ChatRole.Assistant, "Response text");
        var innerAgent = CreateTestAgent(
            runFunc: (_, _, _, _) => Task.FromResult(new AgentResponse([responseMessage])));

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert
        Assert.NotNull(provider.LastInvokedContext?.ResponseMessages);
        Assert.Contains(provider.LastInvokedContext!.ResponseMessages!, m => m.Text == "Response text");
    }

    #endregion

    #region RunStreamingAsync Tests

    [Fact]
    public async Task RunStreamingAsync_SingleProvider_EnrichesMessagesAndStreamsAsync()
    {
        // Arrange
        var contextMessage = new ChatMessage(ChatRole.System, "Extra context");
        var provider = new TestProvider(provideMessages: [contextMessage]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerAgent = CreateTestAgent(
            runStreamingFunc: (messages, _, _, _) =>
            {
                capturedMessages = messages;
                return ToAsyncEnumerableAsync(
                    new AgentResponseUpdate(ChatRole.Assistant, "Part1"),
                    new AgentResponseUpdate(ChatRole.Assistant, "Part2"));
            });

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession))
        {
            updates.Add(update);
        }

        // Assert - streaming updates received
        Assert.Equal(2, updates.Count);
        // Assert - inner agent received enriched messages
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(2, messageList.Count);
    }

    [Fact]
    public async Task RunStreamingAsync_OnSuccess_InvokedAsyncCalledAfterAllUpdatesAsync()
    {
        // Arrange
        var provider = new TestProvider();
        var innerAgent = CreateTestAgent(
            runStreamingFunc: (_, _, _, _) => ToAsyncEnumerableAsync(
                new AgentResponseUpdate(ChatRole.Assistant, "Response")));

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act - consume all updates
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession))
        {
        }

        // Assert
        Assert.True(provider.InvokedAsyncCalled);
        Assert.Null(provider.LastInvokedContext!.InvokeException);
    }

    [Fact]
    public async Task RunStreamingAsync_OnSuccess_InvokedContextContainsAccumulatedResponseAsync()
    {
        // Arrange
        var provider = new TestProvider();
        var innerAgent = CreateTestAgent(
            runStreamingFunc: (_, _, _, _) => ToAsyncEnumerableAsync(
                new AgentResponseUpdate(ChatRole.Assistant, "Hello "),
                new AgentResponseUpdate(ChatRole.Assistant, "World")));

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act - consume all updates
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession))
        {
        }

        // Assert - InvokedAsync received the accumulated response messages
        Assert.NotNull(provider.LastInvokedContext?.ResponseMessages);
        var responseMessages = provider.LastInvokedContext!.ResponseMessages!.ToList();
        Assert.True(responseMessages.Count > 0);
    }

    [Fact]
    public async Task RunStreamingAsync_OnFailure_InvokedAsyncCalledWithExceptionAsync()
    {
        // Arrange
        var provider = new TestProvider();
        var expectedException = new InvalidOperationException("Stream failed");
        var innerAgent = CreateTestAgent(
            runStreamingFunc: (_, _, _, _) => throw expectedException);

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider]);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession))
            {
            }
        });

        Assert.True(provider.InvokedAsyncCalled);
        Assert.Same(expectedException, provider.LastInvokedContext!.InvokeException);
    }

    [Fact]
    public async Task RunStreamingAsync_MultipleProviders_CalledInSequenceAsync()
    {
        // Arrange
        var provider1 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "From provider 1")]);
        var provider2 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "From provider 2")]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerAgent = CreateTestAgent(
            runStreamingFunc: (messages, _, _, _) =>
            {
                capturedMessages = messages;
                return ToAsyncEnumerableAsync(new AgentResponseUpdate(ChatRole.Assistant, "Response"));
            });

        var agent = new MessageAIContextProviderAgent(innerAgent, [provider1, provider2]);

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession))
        {
        }

        // Assert
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(3, messageList.Count);
        Assert.Equal("Hello", messageList[0].Text);
        Assert.Contains("From provider 1", messageList[1].Text);
        Assert.Contains("From provider 2", messageList[2].Text);
    }

    #endregion

    #region Builder Extension Tests

    [Fact]
    public async Task UseExtension_CreatesWorkingPipelineAsync()
    {
        // Arrange
        var contextMessage = new ChatMessage(ChatRole.System, "Pipeline context");
        var provider = new TestProvider(provideMessages: [contextMessage]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerAgent = CreateTestAgent(
            runFunc: (messages, _, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var pipeline = new AIAgentBuilder(innerAgent)
            .UseAIContextProviders([provider])
            .Build();

        // Act
        await pipeline.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(2, messageList.Count);
        Assert.Equal("Hello", messageList[0].Text);
        Assert.Contains("Pipeline context", messageList[1].Text);
    }

    [Fact]
    public async Task UseExtension_MultipleProviders_AllAppliedAsync()
    {
        // Arrange
        var provider1 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "P1")]);
        var provider2 = new TestProvider(provideMessages: [new ChatMessage(ChatRole.System, "P2")]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerAgent = CreateTestAgent(
            runFunc: (messages, _, _, _) =>
            {
                capturedMessages = messages;
                return Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Response")]));
            });

        var pipeline = new AIAgentBuilder(innerAgent)
            .UseAIContextProviders([provider1, provider2])
            .Build();

        // Act
        await pipeline.RunAsync([new ChatMessage(ChatRole.User, "Hello")], s_mockSession);

        // Assert
        Assert.NotNull(capturedMessages);
        var messageList = capturedMessages!.ToList();
        Assert.Equal(3, messageList.Count);
    }

    #endregion

    #region Helpers

    private static TestAIAgent CreateTestAgent(
        Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken, Task<AgentResponse>>? runFunc = null,
        Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken, IAsyncEnumerable<AgentResponseUpdate>>? runStreamingFunc = null)
    {
        var agent = new TestAIAgent();
        if (runFunc is not null)
        {
            agent.RunAsyncFunc = runFunc;
        }

        if (runStreamingFunc is not null)
        {
            agent.RunStreamingAsyncFunc = runStreamingFunc;
        }

        return agent;
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(params AgentResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    /// <summary>
    /// A test implementation of <see cref="MessageAIContextProvider"/> that records invocation calls.
    /// </summary>
    private sealed class TestProvider : MessageAIContextProvider
    {
        private readonly IEnumerable<ChatMessage> _provideMessages;
        private readonly Action<IEnumerable<ChatMessage>>? _onInvoking;

        public bool InvokedAsyncCalled { get; private set; }

        public InvokedContext? LastInvokedContext { get; private set; }

        public TestProvider(
            IEnumerable<ChatMessage>? provideMessages = null,
            Action<IEnumerable<ChatMessage>>? onInvoking = null)
        {
            this._provideMessages = provideMessages ?? [];
            this._onInvoking = onInvoking;
        }

        protected override ValueTask<IEnumerable<ChatMessage>> ProvideMessagesAsync(
            InvokingContext context,
            CancellationToken cancellationToken = default)
        {
            this._onInvoking?.Invoke(context.RequestMessages);
            return new ValueTask<IEnumerable<ChatMessage>>(this._provideMessages);
        }

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.InvokedAsyncCalled = true;
            this.LastInvokedContext = context;
            return default;
        }
    }

    #endregion
}
