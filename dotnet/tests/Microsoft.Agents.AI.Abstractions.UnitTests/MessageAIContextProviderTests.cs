// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="MessageAIContextProvider"/> class.
/// </summary>
public class MessageAIContextProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region InvokingAsync Tests

    [Fact]
    public async Task InvokingAsync_NullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new TestMessageProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokingAsync(null!).AsTask());
    }

    [Fact]
    public async Task InvokingAsync_ReturnsInputAndProvidedMessagesAsync()
    {
        // Arrange
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Context message") };
        var provider = new TestMessageProvider(provideMessages: providedMessages);
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "User input")]);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert - input messages + provided messages merged
        Assert.Equal(2, result.Count);
        Assert.Equal("User input", result[0].Text);
        Assert.Equal("Context message", result[1].Text);
    }

    [Fact]
    public async Task InvokingAsync_ReturnsOnlyInputMessages_WhenNoMessagesProvidedAsync()
    {
        // Arrange
        var provider = new DefaultMessageProvider();
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "Hello")]);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal("Hello", result[0].Text);
    }

    [Fact]
    public async Task InvokingAsync_StampsProvidedMessagesWithAIContextProviderSourceAsync()
    {
        // Arrange
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Provided") };
        var provider = new TestMessageProvider(provideMessages: providedMessages);
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, []);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert
        Assert.Single(result);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, result[0].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task InvokingAsync_FiltersInputToExternalOnlyByDefaultAsync()
    {
        // Arrange
        var provider = new TestMessageProvider(captureFilteredContext: true);
        var externalMsg = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMsg = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var contextProviderMsg = new ChatMessage(ChatRole.User, "ContextProvider")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "src");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [externalMsg, chatHistoryMsg, contextProviderMsg]);

        // Act
        await provider.InvokingAsync(context);

        // Assert - ProvideMessagesAsync received only External messages
        Assert.NotNull(provider.LastFilteredContext);
        var filteredMessages = provider.LastFilteredContext!.RequestMessages.ToList();
        Assert.Single(filteredMessages);
        Assert.Equal("External", filteredMessages[0].Text);
    }

    [Fact]
    public async Task InvokingAsync_UsesCustomProvideInputFilterAsync()
    {
        // Arrange - filter that keeps all messages (not just External)
        var provider = new TestMessageProvider(
            captureFilteredContext: true,
            provideInputMessageFilter: msgs => msgs);
        var externalMsg = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMsg = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [externalMsg, chatHistoryMsg]);

        // Act
        await provider.InvokingAsync(context);

        // Assert - ProvideMessagesAsync received ALL messages (custom filter keeps everything)
        Assert.NotNull(provider.LastFilteredContext);
        var filteredMessages = provider.LastFilteredContext!.RequestMessages.ToList();
        Assert.Equal(2, filteredMessages.Count);
    }

    [Fact]
    public async Task InvokingAsync_MergesWithOriginalUnfilteredMessagesAsync()
    {
        // Arrange - default filter is External-only, but the MERGED result should include
        // the original unfiltered input messages plus the provided messages
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Provided") };
        var provider = new TestMessageProvider(provideMessages: providedMessages);
        var externalMsg = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMsg = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, [externalMsg, chatHistoryMsg]);

        // Act
        var result = (await provider.InvokingAsync(context)).ToList();

        // Assert - original 2 input messages + 1 provided message
        Assert.Equal(3, result.Count);
        Assert.Equal("External", result[0].Text);
        Assert.Equal("History", result[1].Text);
        Assert.Equal("Provided", result[2].Text);
    }

    #endregion

    #region ProvideAIContextAsync Tests

    [Fact]
    public async Task ProvideAIContextAsync_PreservesInstructionsAndToolsAsync()
    {
        // Arrange
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Context") };
        var provider = new TestMessageProvider(provideMessages: providedMessages);
        var inputTool = AIFunctionFactory.Create(() => "a", "inputTool");
        var inputContext = new AIContext
        {
            Messages = [new ChatMessage(ChatRole.User, "Hello")],
            Instructions = "Be helpful",
            Tools = [inputTool]
        };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert - instructions and tools are preserved
        Assert.Equal("Be helpful", result.Instructions);
        Assert.NotNull(result.Tools);
        Assert.Single(result.Tools!);
        Assert.Equal("inputTool", result.Tools!.First().Name);

        // Messages include original input + provided messages (with stamping)
        var messages = result.Messages!.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Equal("Hello", messages[0].Text);
        Assert.Equal("Context", messages[1].Text);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[1].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task ProvideAIContextAsync_PreservesNullInstructionsAndToolsAsync()
    {
        // Arrange
        var provider = new DefaultMessageProvider();
        var inputContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert
        Assert.Null(result.Instructions);
        Assert.Null(result.Tools);
        var messages = result.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
    }

    #endregion

    #region InvokingContext Tests

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullAgent()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new MessageAIContextProvider.InvokingContext(null!, s_mockSession, []));
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullRequestMessages()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokingContext_Constructor_AllowsNullSession()
    {
        // Act
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, null, []);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokingContext_Properties_Roundtrip()
    {
        // Arrange
        var messages = new List<ChatMessage> { new(ChatRole.User, "Hello") };

        // Act
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, messages);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
        Assert.Same(s_mockSession, context.Session);
        Assert.Same(messages, context.RequestMessages);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterThrowsForNull()
    {
        // Arrange
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, []);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => context.RequestMessages = null!);
    }

    [Fact]
    public void InvokingContext_RequestMessages_SetterAcceptsValidValue()
    {
        // Arrange
        var context = new MessageAIContextProvider.InvokingContext(s_mockAgent, s_mockSession, []);
        var newMessages = new List<ChatMessage> { new(ChatRole.User, "Updated") };

        // Act
        context.RequestMessages = newMessages;

        // Assert
        Assert.Same(newMessages, context.RequestMessages);
    }

    #endregion

    #region GetService Tests

    [Fact]
    public void GetService_ReturnsProviderForMessageAIContextProviderType()
    {
        // Arrange
        var provider = new TestMessageProvider();

        // Act & Assert
        Assert.Same(provider, provider.GetService(typeof(MessageAIContextProvider)));
        Assert.Same(provider, provider.GetService(typeof(AIContextProvider)));
        Assert.Same(provider, provider.GetService(typeof(TestMessageProvider)));
    }

    #endregion

    #region Test helpers

    private sealed class TestMessageProvider : MessageAIContextProvider
    {
        private readonly IEnumerable<ChatMessage>? _provideMessages;
        private readonly bool _captureFilteredContext;

        public InvokingContext? LastFilteredContext { get; private set; }

        public TestMessageProvider(
            IEnumerable<ChatMessage>? provideMessages = null,
            bool captureFilteredContext = false,
            Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter = null,
            Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
            : base(provideInputMessageFilter, storeInputMessageFilter)
        {
            this._provideMessages = provideMessages;
            this._captureFilteredContext = captureFilteredContext;
        }

        protected override ValueTask<IEnumerable<ChatMessage>> ProvideMessagesAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            if (this._captureFilteredContext)
            {
                this.LastFilteredContext = context;
            }

            return new(this._provideMessages ?? []);
        }
    }

    /// <summary>
    /// A provider that uses only base class defaults (no overrides of ProvideMessagesAsync).
    /// </summary>
    private sealed class DefaultMessageProvider : MessageAIContextProvider;

    #endregion
}
