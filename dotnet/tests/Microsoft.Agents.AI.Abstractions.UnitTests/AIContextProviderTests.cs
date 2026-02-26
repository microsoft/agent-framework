// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AIContextProviderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;
    private static readonly AgentSession s_mockSession = new Mock<AgentSession>().Object;

    #region Basic Tests

    [Fact]
    public async Task InvokedAsync_ReturnsCompletedTaskAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var messages = new ReadOnlyCollection<ChatMessage>([]);

        // Act
        ValueTask task = provider.InvokedAsync(new(s_mockAgent, s_mockSession, messages, []));

        // Assert
        Assert.Equal(default, task);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullMessages()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullMessages()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, null!, []));
    }

    #endregion

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the context provider itself when requesting the exact context provider type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactContextProviderType_ReturnsContextProvider()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(TestAIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService returns the context provider itself when requesting the base AIContextProvider type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIContextProviderType_ReturnsContextProvider()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(AIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService returns null when a service key is provided, even for matching types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(TestAIContextProvider), "some-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService throws ArgumentNullException when serviceType is null.
    /// </summary>
    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => contextProvider.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService<TestAIContextProvider>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    #region InvokingContext Tests

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullAIContext()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, null!));
    }

    [Fact]
    public void InvokingContext_AIContext_ConstructorValueRoundtrips()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, aiContext);

        // Assert
        Assert.Same(aiContext, context.AIContext);
    }

    [Fact]
    public void InvokingContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, aiContext);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokingContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, aiContext);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokingContext_Session_CanBeNull()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act
        var context = new AIContextProvider.InvokingContext(s_mockAgent, null, aiContext);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var aiContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(null!, s_mockSession, aiContext));
    }

    #endregion

    #region InvokedContext Tests

    [Fact]
    public void InvokedContext_ResponseMessages_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var responseMessages = new List<ChatMessage> { new(ChatRole.Assistant, "Response message") };

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, responseMessages);

        // Assert
        Assert.Same(responseMessages, context.ResponseMessages);
    }

    [Fact]
    public void InvokedContext_InvokeException_Roundtrips()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);
        var exception = new InvalidOperationException("Test exception");

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, exception);

        // Assert
        Assert.Same(exception, context.InvokeException);
    }

    [Fact]
    public void InvokedContext_Agent_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, []);

        // Assert
        Assert.Same(s_mockAgent, context.Agent);
    }

    [Fact]
    public void InvokedContext_Session_ReturnsConstructorValue()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, []);

        // Assert
        Assert.Same(s_mockSession, context.Session);
    }

    [Fact]
    public void InvokedContext_Session_CanBeNull()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act
        var context = new AIContextProvider.InvokedContext(s_mockAgent, null, requestMessages, []);

        // Assert
        Assert.Null(context.Session);
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullAgent()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(null!, s_mockSession, requestMessages, []));
    }

    [Fact]
    public void InvokedContext_SuccessConstructor_ThrowsForNullResponseMessages()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, (IEnumerable<ChatMessage>)null!));
    }

    [Fact]
    public void InvokedContext_FailureConstructor_ThrowsForNullException()
    {
        // Arrange
        var requestMessages = new ReadOnlyCollection<ChatMessage>([new(ChatRole.User, "Hello")]);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, requestMessages, (Exception)null!));
    }

    #endregion

    #region InvokingAsync / InvokedAsync Null Check Tests

    [Fact]
    public async Task InvokingAsync_NullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokingAsync(null!).AsTask());
    }

    [Fact]
    public async Task InvokedAsync_NullContext_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => provider.InvokedAsync(null!).AsTask());
    }

    #endregion

    #region InvokingCoreAsync Tests

    [Fact]
    public async Task InvokingCoreAsync_CallsProvideAIContextAndReturnsMergedContextAsync()
    {
        // Arrange
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Context message") };
        var provider = new TestAIContextProvider(provideContext: new AIContext { Messages = providedMessages });
        var inputContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "User input")] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert - input messages + provided messages merged
        var messages = result.Messages!.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Equal("User input", messages[0].Text);
        Assert.Equal("Context message", messages[1].Text);
    }

    [Fact]
    public async Task InvokingCoreAsync_FiltersInputToExternalOnlyByDefaultAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider(captureFilteredContext: true);
        var externalMsg = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMsg = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var contextProviderMsg = new ChatMessage(ChatRole.User, "ContextProvider")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "src");
        var inputContext = new AIContext { Messages = [externalMsg, chatHistoryMsg, contextProviderMsg] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        await provider.InvokingAsync(context);

        // Assert - ProvideAIContextAsync received only External messages
        Assert.NotNull(provider.LastProvidedContext);
        var filteredMessages = provider.LastProvidedContext!.AIContext.Messages!.ToList();
        Assert.Single(filteredMessages);
        Assert.Equal("External", filteredMessages[0].Text);
    }

    [Fact]
    public async Task InvokingCoreAsync_StampsProvidedMessagesWithAIContextProviderSourceAsync()
    {
        // Arrange
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Provided") };
        var provider = new TestAIContextProvider(provideContext: new AIContext { Messages = providedMessages });
        var inputContext = new AIContext { Messages = [] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert
        var messages = result.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[0].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task InvokingCoreAsync_MergesInstructionsAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider(provideContext: new AIContext { Instructions = "Provided instructions" });
        var inputContext = new AIContext { Instructions = "Input instructions" };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert - instructions are joined with newline
        Assert.Equal("Input instructions\nProvided instructions", result.Instructions);
    }

    [Fact]
    public async Task InvokingCoreAsync_MergesToolsAsync()
    {
        // Arrange
        var inputTool = AIFunctionFactory.Create(() => "a", "inputTool");
        var providedTool = AIFunctionFactory.Create(() => "b", "providedTool");
        var provider = new TestAIContextProvider(provideContext: new AIContext { Tools = [providedTool] });
        var inputContext = new AIContext { Tools = [inputTool] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert - both tools present
        var tools = result.Tools!.ToList();
        Assert.Equal(2, tools.Count);
    }

    [Fact]
    public async Task InvokingCoreAsync_UsesCustomProvideInputFilterAsync()
    {
        // Arrange - filter that keeps all messages (not just External)
        var provider = new TestAIContextProvider(
            captureFilteredContext: true,
            provideInputMessageFilter: msgs => msgs);
        var externalMsg = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMsg = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var inputContext = new AIContext { Messages = [externalMsg, chatHistoryMsg] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        await provider.InvokingAsync(context);

        // Assert - ProvideAIContextAsync received ALL messages (custom filter keeps everything)
        Assert.NotNull(provider.LastProvidedContext);
        var filteredMessages = provider.LastProvidedContext!.AIContext.Messages!.ToList();
        Assert.Equal(2, filteredMessages.Count);
    }

    [Fact]
    public async Task InvokingCoreAsync_ReturnsEmptyContextByDefaultAsync()
    {
        // Arrange - provider that doesn't override ProvideAIContextAsync
        var provider = new DefaultAIContextProvider();
        var inputContext = new AIContext { Messages = [new ChatMessage(ChatRole.User, "Hello")] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert - only the input messages (no additional provided)
        var messages = result.Messages!.ToList();
        Assert.Single(messages);
        Assert.Equal("Hello", messages[0].Text);
    }

    [Fact]
    public async Task InvokingCoreAsync_MergesWithOriginalUnfilteredMessagesAsync()
    {
        // Arrange - default filter is External-only, but the MERGED result should include
        // the original unfiltered input messages plus the provided messages
        var providedMessages = new[] { new ChatMessage(ChatRole.System, "Provided") };
        var provider = new TestAIContextProvider(provideContext: new AIContext { Messages = providedMessages });
        var externalMsg = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMsg = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var inputContext = new AIContext { Messages = [externalMsg, chatHistoryMsg] };
        var context = new AIContextProvider.InvokingContext(s_mockAgent, s_mockSession, inputContext);

        // Act
        var result = await provider.InvokingAsync(context);

        // Assert - original 2 input messages + 1 provided message
        var messages = result.Messages!.ToList();
        Assert.Equal(3, messages.Count);
        Assert.Equal("External", messages[0].Text);
        Assert.Equal("History", messages[1].Text);
        Assert.Equal("Provided", messages[2].Text);
    }

    #endregion

    #region InvokedCoreAsync Tests

    [Fact]
    public async Task InvokedCoreAsync_CallsStoreAIContextWithFilteredMessagesAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var externalMessage = new ChatMessage(ChatRole.User, "External");
        var chatHistoryMessage = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var responseMessages = new[] { new ChatMessage(ChatRole.Assistant, "Response") };
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, new[] { externalMessage, chatHistoryMessage }, responseMessages);

        // Act
        await provider.InvokedAsync(context);

        // Assert - default filter keeps only External messages
        Assert.NotNull(provider.LastStoredContext);
        var storedRequest = provider.LastStoredContext!.RequestMessages.ToList();
        Assert.Single(storedRequest);
        Assert.Equal("External", storedRequest[0].Text);
        Assert.Same(responseMessages, provider.LastStoredContext.ResponseMessages);
    }

    [Fact]
    public async Task InvokedCoreAsync_SkipsStorageWhenInvokeExceptionIsNotNullAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, [new ChatMessage(ChatRole.User, "msg")], new InvalidOperationException("Failed"));

        // Act
        await provider.InvokedAsync(context);

        // Assert - StoreAIContextAsync was NOT called
        Assert.Null(provider.LastStoredContext);
    }

    [Fact]
    public async Task InvokedCoreAsync_UsesCustomStoreInputFilterAsync()
    {
        // Arrange - filter that only keeps System messages
        var provider = new TestAIContextProvider(
            storeInputMessageFilter: msgs => msgs.Where(m => m.Role == ChatRole.System));
        var messages = new[]
        {
            new ChatMessage(ChatRole.User, "User msg"),
            new ChatMessage(ChatRole.System, "System msg")
        };
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, messages, [new ChatMessage(ChatRole.Assistant, "Response")]);

        // Act
        await provider.InvokedAsync(context);

        // Assert - only System messages were passed to store
        Assert.NotNull(provider.LastStoredContext);
        var storedRequest = provider.LastStoredContext!.RequestMessages.ToList();
        Assert.Single(storedRequest);
        Assert.Equal("System msg", storedRequest[0].Text);
    }

    [Fact]
    public async Task InvokedCoreAsync_DefaultFilterExcludesNonExternalMessagesAsync()
    {
        // Arrange
        var provider = new TestAIContextProvider();
        var external = new ChatMessage(ChatRole.User, "External");
        var fromHistory = new ChatMessage(ChatRole.User, "History")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "src");
        var fromContext = new ChatMessage(ChatRole.User, "Context")
            .WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "src");
        var context = new AIContextProvider.InvokedContext(s_mockAgent, s_mockSession, [external, fromHistory, fromContext], []);

        // Act
        await provider.InvokedAsync(context);

        // Assert - only External messages kept
        Assert.NotNull(provider.LastStoredContext);
        var storedRequest = provider.LastStoredContext!.RequestMessages.ToList();
        Assert.Single(storedRequest);
        Assert.Equal("External", storedRequest[0].Text);
    }

    #endregion

    private sealed class TestAIContextProvider : AIContextProvider
    {
        private readonly AIContext? _provideContext;
        private readonly bool _captureFilteredContext;

        public InvokedContext? LastStoredContext { get; private set; }

        public InvokingContext? LastProvidedContext { get; private set; }

        public TestAIContextProvider(
            AIContext? provideContext = null,
            bool captureFilteredContext = false,
            Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? provideInputMessageFilter = null,
            Func<IEnumerable<ChatMessage>, IEnumerable<ChatMessage>>? storeInputMessageFilter = null)
            : base(provideInputMessageFilter, storeInputMessageFilter)
        {
            this._provideContext = provideContext;
            this._captureFilteredContext = captureFilteredContext;
        }

        protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            if (this._captureFilteredContext)
            {
                this.LastProvidedContext = context;
            }

            return new(this._provideContext ?? new AIContext());
        }

        protected override ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.LastStoredContext = context;
            return default;
        }
    }

    /// <summary>
    /// A provider that uses only base class defaults (no overrides of ProvideAIContextAsync/StoreAIContextAsync).
    /// </summary>
    private sealed class DefaultAIContextProvider : AIContextProvider;
}
