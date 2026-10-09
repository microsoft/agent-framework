// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for ChatClientAgent accepting continuation tokens minted for the underlying <see cref="IChatClient"/>.
/// </summary>
public class ChatClientAgent_RawContinuationTokenTests
{
    private static ResponseContinuationToken CreateRawToken() => ResponseContinuationToken.FromBytes(Encoding.UTF8.GetBytes("{\"responseId\":\"resp_123\",\"sequenceNumber\":7}"));

    [Fact]
    public async Task RunAsync_WithRawChatClientToken_ForwardsTokenToChatClientAndFinalizesOnceAsync()
    {
        // Arrange
        var rawToken = CreateRawToken();
        FakeChatClient chatClient = new() { Response = new ChatResponse([new(ChatRole.Assistant, "done")]) };
        var contextProvider = CreateContextProvider(out var invokedContexts);
        ChatClientAgent agent = new(chatClient, options: new() { AIContextProviders = [contextProvider.Object] });
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync(session, options: new AgentRunOptions { AllowBackgroundResponses = true, ContinuationToken = rawToken });

        // Assert
        Assert.Same(rawToken, chatClient.CapturedOptions!.ContinuationToken);
        Assert.Equal("done", response.Text);
        var history = ((InMemoryChatHistoryProvider)agent.ChatHistoryProvider!).GetMessages(session);
        Assert.Single(history);
        Assert.Equal("done", history[0].Text);
        var invoked = Assert.Single(invokedContexts);
        Assert.Empty(invoked.RequestMessages);
        Assert.Equal("done", Assert.Single(invoked.ResponseMessages!).Text);
    }

    [Fact]
    public async Task RunAsync_WithRawTokenInChatOptions_ForwardsTokenToChatClientAsync()
    {
        // Arrange
        var rawToken = CreateRawToken();
        FakeChatClient chatClient = new() { Response = new ChatResponse([new(ChatRole.Assistant, "done")]) };
        ChatClientAgent agent = new(chatClient);
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync(session, options: new ChatClientAgentRunOptions(new ChatOptions { ContinuationToken = rawToken }));

        // Assert
        Assert.Same(rawToken, chatClient.CapturedOptions!.ContinuationToken);
    }

    [Fact]
    public async Task RunAsync_WithRawToken_AndInputMessages_ThrowsAsync()
    {
        // Arrange
        FakeChatClient chatClient = new() { Response = new ChatResponse([new(ChatRole.Assistant, "done")]) };
        ChatClientAgent agent = new(chatClient);
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync("hi", session, options: new AgentRunOptions { ContinuationToken = CreateRawToken() }));
    }

    [Fact]
    public async Task RunStreamingAsync_WithRawChatClientToken_ForwardsTokenAndFinalizesOnceAsync()
    {
        // Arrange
        var rawToken = CreateRawToken();
        var nextToken = ResponseContinuationToken.FromBytes(new byte[] { 9, 9 });
        FakeChatClient chatClient = new()
        {
            Updates =
            [
                new ChatResponseUpdate(ChatRole.Assistant, "do") { ContinuationToken = nextToken },
                new ChatResponseUpdate(ChatRole.Assistant, "ne"),
            ]
        };
        var contextProvider = CreateContextProvider(out var invokedContexts);
        ChatClientAgent agent = new(chatClient, options: new() { AIContextProviders = [contextProvider.Object] });
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync(session, options: new AgentRunOptions { AllowBackgroundResponses = true, ContinuationToken = rawToken }))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Same(rawToken, chatClient.CapturedOptions!.ContinuationToken);
        var wrapped = Assert.IsType<ChatClientAgentContinuationToken>(updates[0].ContinuationToken);
        Assert.Same(nextToken, wrapped.InnerToken);
        Assert.Null(updates[1].ContinuationToken);
        var history = ((InMemoryChatHistoryProvider)agent.ChatHistoryProvider!).GetMessages(session);
        Assert.Single(history);
        Assert.Equal("done", history[0].Text);
        var invoked = Assert.Single(invokedContexts);
        Assert.Empty(invoked.RequestMessages);
        Assert.Equal("done", Assert.Single(invoked.ResponseMessages!).Text);
    }

    [Fact]
    public async Task RunStreamingAsync_WithSerializedAgentToken_RestoresInnerTokenInputMessagesAndUpdatesAsync()
    {
        // Arrange
        var innerToken = CreateRawToken();
        var envelope = new ChatClientAgentContinuationToken(innerToken)
        {
            InputMessages = [new ChatMessage(ChatRole.User, "question")],
            ResponseUpdates = [new ChatResponseUpdate(ChatRole.Assistant, "par")],
        };
        var serialized = ResponseContinuationToken.FromBytes(envelope.ToBytes());
        FakeChatClient chatClient = new() { Updates = [new ChatResponseUpdate(ChatRole.Assistant, "tial")] };
        ChatClientAgent agent = new(chatClient);
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act
        await foreach (var _ in agent.RunStreamingAsync(session, options: new AgentRunOptions { ContinuationToken = serialized }))
        {
        }

        // Assert
        Assert.Equal(innerToken.ToBytes().ToArray(), chatClient.CapturedOptions!.ContinuationToken!.ToBytes().ToArray());
        var history = ((InMemoryChatHistoryProvider)agent.ChatHistoryProvider!).GetMessages(session);
        Assert.Equal(2, history.Count);
        Assert.Equal("question", history[0].Text);
        Assert.Equal("partial", history[1].Text);
    }

    [Fact]
    public async Task RunAsync_WithMalformedAgentToken_ThrowsAsync()
    {
        // Arrange
        var malformed = ResponseContinuationToken.FromBytes(Encoding.UTF8.GetBytes("{\"type\":\"chatClientAgentContinuationToken\"}"));
        FakeChatClient chatClient = new() { Response = new ChatResponse([new(ChatRole.Assistant, "done")]) };
        ChatClientAgent agent = new(chatClient);
        var session = (ChatClientAgentSession)await agent.CreateSessionAsync();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => agent.RunAsync(session, options: new AgentRunOptions { ContinuationToken = malformed }));
        Assert.Null(chatClient.CapturedOptions);
    }

    [Fact]
    public void FromToken_WithRawToken_WrapsTokenAsIs()
    {
        // Arrange
        var rawToken = CreateRawToken();

        // Act
        var result = ChatClientAgentContinuationToken.FromToken(rawToken);

        // Assert
        Assert.Same(rawToken, result.InnerToken);
        Assert.Null(result.InputMessages);
        Assert.Null(result.ResponseUpdates);
    }

    [Theory]
    [InlineData("not json at all")]
    [InlineData("{\"type\":\"somethingElse\",\"id\":1}")]
    [InlineData("{\"responseId\":\"x\"}")]
    [InlineData("[1,2,3]")]
    [InlineData("")]
    public void FromToken_WithNonAgentPayload_WrapsTokenAsIs(string payload)
    {
        // Arrange
        var rawToken = ResponseContinuationToken.FromBytes(Encoding.UTF8.GetBytes(payload));

        // Act
        var result = ChatClientAgentContinuationToken.FromToken(rawToken);

        // Assert
        Assert.Same(rawToken, result.InnerToken);
    }

    [Fact]
    public void FromToken_WithAgentTokenMissingInnerToken_Throws()
    {
        // Arrange
        var malformed = ResponseContinuationToken.FromBytes(Encoding.UTF8.GetBytes("{\"type\":\"chatClientAgentContinuationToken\"}"));

        // Act & Assert
        Assert.Throws<ArgumentException>(() => ChatClientAgentContinuationToken.FromToken(malformed));
    }

    private static Mock<AIContextProvider> CreateContextProvider(out List<AIContextProvider.InvokedContext> invokedContexts)
    {
        List<AIContextProvider.InvokedContext> captured = [];
        invokedContexts = captured;

        Mock<AIContextProvider> mock = new(null, null, null);
        mock.SetupGet(p => p.StateKeys).Returns(["RawTokenTestProvider"]);
        mock.Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(() => new ValueTask<AIContext>(new AIContext()));
        mock.Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Callback<AIContextProvider.InvokedContext, CancellationToken>((ctx, _) => captured.Add(ctx))
            .Returns(() => new ValueTask());
        return mock;
    }

    private sealed class FakeChatClient : IChatClient
    {
        public ChatResponse? Response { get; set; }

        public IList<ChatResponseUpdate> Updates { get; set; } = [];

        public ChatOptions? CapturedOptions { get; private set; }

        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.CapturedOptions = options;
            return Task.FromResult(this.Response!);
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.CapturedOptions = options;
            await Task.Yield();
            foreach (var update in this.Updates)
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

        public void Dispose()
        {
        }
    }
}
