// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

public partial class ChatClientAgentTests
{
    #region Constructor Tests

    /// <summary>
    /// Verify the invocation and response of <see cref="ChatClientAgent"/>.
    /// </summary>
    [Fact]
    public void VerifyChatClientAgentDefinition()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent =
            new(chatClient,
                options: new()
                {
                    Id = "test-agent-id",
                    Name = "test name",
                    Description = "test description",
                    ChatOptions = new() { Instructions = "test instructions" },
                });

        // Assert
        Assert.NotNull(agent.Id);
        Assert.Equal("test-agent-id", agent.Id);
        Assert.Equal("test name", agent.Name);
        Assert.Equal("test description", agent.Description);
        Assert.Equal("test instructions", agent.Instructions);
        Assert.NotNull(agent.ChatClient);
        Assert.Equal("FunctionInvokingChatClient", agent.ChatClient.GetType().Name);
    }

    /// <summary>
    /// Verify that the constructor throws when two AIContextProviders use the same StateKey.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenDuplicateAIContextProviderStateKeys()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var provider1 = new TestAIContextProvider("SharedKey");
        var provider2 = new TestAIContextProvider("SharedKey");

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() =>
            new ChatClientAgent(chatClient, options: new()
            {
                AIContextProviders = [provider1, provider2]
            }));

        Assert.Contains("SharedKey", ex.Message);
    }

    /// <summary>
    /// Verify that the constructor throws when an AIContextProvider uses the same StateKey as the default InMemoryChatHistoryProvider
    /// and no explicit ChatHistoryProvider is configured.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenAIContextProviderStateKeyClashesWithDefaultInMemoryChatHistoryProvider()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var contextProvider = new TestAIContextProvider(nameof(InMemoryChatHistoryProvider));

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() =>
            new ChatClientAgent(chatClient, options: new()
            {
                AIContextProviders = [contextProvider]
            }));

        Assert.Contains(nameof(InMemoryChatHistoryProvider), ex.Message);
    }

    /// <summary>
    /// Verify that the constructor throws when a ChatHistoryProvider uses the same StateKey as an AIContextProvider.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenChatHistoryProviderStateKeyClashesWithAIContextProvider()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var contextProvider = new TestAIContextProvider("SharedKey");
        var historyProvider = new TestChatHistoryProvider("SharedKey");

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() =>
            new ChatClientAgent(chatClient, options: new()
            {
                AIContextProviders = [contextProvider],
                ChatHistoryProvider = historyProvider
            }));

        Assert.Contains("SharedKey", ex.Message);
        Assert.Contains(nameof(ChatHistoryProvider), ex.Message);
    }

    /// <summary>
    /// Verify that the constructor succeeds when all providers use unique StateKeys.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithUniqueProviderStateKeys()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var contextProvider1 = new TestAIContextProvider("Key1");
        var contextProvider2 = new TestAIContextProvider("Key2");
        var historyProvider = new TestChatHistoryProvider("Key3");

        // Act & Assert - should not throw
        _ = new ChatClientAgent(chatClient, options: new()
        {
            AIContextProviders = [contextProvider1, contextProvider2],
            ChatHistoryProvider = historyProvider
        });
    }

    /// <summary>
    /// Verify that RunAsync throws when an override ChatHistoryProvider's StateKey clashes with an AIContextProvider.
    /// </summary>
    [Fact]
    public async Task RunAsync_ThrowsWhenOverrideChatHistoryProviderStateKeyClashesWithAIContextProviderAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        var contextProvider = new TestAIContextProvider("SharedKey");
        var overrideHistoryProvider = new TestChatHistoryProvider("SharedKey");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            AIContextProviders = [contextProvider]
        });

        // Act & Assert
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        AdditionalPropertiesDictionary additionalProperties = new();
        additionalProperties.Add<ChatHistoryProvider>(overrideHistoryProvider);

        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            agent.RunAsync([new(ChatRole.User, "test")], session, options: new AgentRunOptions { AdditionalProperties = additionalProperties }));

        Assert.Contains("SharedKey", ex.Message);
    }

    /// <summary>
    /// Verify that RunAsync succeeds when an override ChatHistoryProvider uses the same StateKey as the default ChatHistoryProvider.
    /// </summary>
    [Fact]
    public async Task RunAsync_SucceedsWhenOverrideChatHistoryProviderSharesKeyWithDefaultAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        var defaultHistoryProvider = new TestChatHistoryProvider("SameKey");
        var overrideHistoryProvider = new TestChatHistoryProvider("SameKey");

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatHistoryProvider = defaultHistoryProvider
        });

        // Act & Assert - should not throw
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        AdditionalPropertiesDictionary additionalProperties = new();
        additionalProperties.Add<ChatHistoryProvider>(overrideHistoryProvider);

        await agent.RunAsync([new(ChatRole.User, "test")], session, options: new AgentRunOptions { AdditionalProperties = additionalProperties });
    }

    #endregion

    #region RunAsync Tests

    /// <summary>
    /// Verify the invocation and response of <see cref="ChatClientAgent"/> using <see cref="IChatClient"/>.
    /// </summary>
    [Fact]
    public async Task VerifyChatClientAgentInvocationAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "I'm here!")]));

        ChatClientAgent agent =
            new(mockService.Object, options: new()
            {
                ChatOptions = new() { Instructions = "base instructions" },
            });

        // Act
        var result = await agent.RunAsync([new(ChatRole.User, "Where are you?")]);

        // Assert
        Assert.Single(result.Messages);

        mockService.Verify(
            x =>
                x.GetResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(),
                    It.IsAny<ChatOptions>(),
                    It.IsAny<CancellationToken>()),
            Times.Once);

        Assert.Single(result.Messages);
        Assert.Collection(result.Messages,
            message =>
            {
                Assert.Equal(ChatRole.Assistant, message.Role);
                Assert.Equal("I'm here!", message.Text);
            });
    }

    /// <summary>
    /// Verify that RunAsync throws ArgumentNullException when messages parameter is null.
    /// </summary>
    [Fact]
    public async Task RunAsyncThrowsArgumentNullExceptionWhenMessagesIsNullAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => agent.RunAsync((IReadOnlyCollection<ChatMessage>)null!));
    }

    /// <summary>
    /// Verify that RunAsync passes ChatOptions when using ChatClientAgentRunOptions.
    /// </summary>
    [Fact]
    public async Task RunAsyncPassesChatOptionsWhenUsingChatClientAgentRunOptionsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 100),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: new ChatClientAgentRunOptions(chatOptions));

        // Assert
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 100),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync passes null ChatOptions when using regular AgentRunOptions.
    /// </summary>
    [Fact]
    public async Task RunAsyncPassesNullChatOptionsWhenUsingRegularAgentRunOptionsAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                null,
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object);
        var runOptions = new AgentRunOptions();

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: runOptions);

        // Assert
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                null,
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync includes base instructions in messages.
    /// </summary>
    [Fact]
    public async Task RunAsyncIncludesBaseInstructionsInOptionsAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(x => x.Instructions == "base instructions"),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "base instructions" } });
        var runOptions = new AgentRunOptions();

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: runOptions);

        // Assert
        Assert.Contains(capturedMessages, m => m.Text == "test" && m.Role == ChatRole.User);
    }

    /// <summary>
    /// Verify that RunAsync sets AuthorName on all response messages.
    /// </summary>
    [Theory]
    [InlineData("TestAgent")]
    [InlineData(null)]
    public async Task RunAsyncSetsAuthorNameOnAllResponseMessagesAsync(string? authorName)
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        var responseMessages = new[]
        {
            new ChatMessage(ChatRole.Assistant, "response 1"),
            new ChatMessage(ChatRole.Assistant, "response 2")
        };
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse(responseMessages));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" }, Name = authorName });

        // Act
        var result = await agent.RunAsync([new(ChatRole.User, "test")]);

        // Assert
        Assert.All(result.Messages, msg => Assert.Equal(authorName, msg.AuthorName));
    }

    /// <summary>
    /// Verify that RunAsync works with existing session and can retreive messages if the session has a ChatHistoryProvider.
    /// </summary>
    [Fact]
    public async Task RunAsyncRetrievesMessagesFromSessionWhenSessionHasChatHistoryProviderAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        // Create a session using the agent's CreateSessionAsync method
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new(ChatRole.User, "new message")], session: session);

        // Assert
        // Should contain: new message
        Assert.Contains(capturedMessages, m => m.Text == "new message");
    }

    /// <summary>
    /// Verify that RunAsync works without instructions.
    /// </summary>
    [Fact]
    public async Task RunAsyncWorksWithoutInstructionsWhenInstructionsAreNullOrEmptyAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = null } });

        // Act
        await agent.RunAsync([new(ChatRole.User, "test message")]);

        // Assert
        // Should only contain the user message, no system instructions
        Assert.Single(capturedMessages);
        Assert.Equal("test message", capturedMessages[0].Text);
        Assert.Equal(ChatRole.User, capturedMessages[0].Role);
    }

    /// <summary>
    /// Verify that RunAsync works with empty message collection.
    /// </summary>
    [Fact]
    public async Task RunAsyncWorksWithEmptyMessagesWhenNoMessagesProvidedAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });

        // Act
        await agent.RunAsync([]);

        // Assert
        // Should only contain the instructions
        Assert.Empty(capturedMessages);
    }

    /// <summary>
    /// Verify that RunAsync invokes any provided AIContextProvider and uses the result.
    /// </summary>
    [Fact]
    public async Task RunAsyncInvokesAIContextProviderAndUsesResultAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatMessage[] responseMessages = [new(ChatRole.Assistant, "response")];
        ChatMessage[] aiContextProviderMessages = [new(ChatRole.System, "context provider message")];
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        string capturedInstructions = string.Empty;
        List<AITool> capturedTools = [];
        mockService
            .Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
            {
                capturedMessages.AddRange(msgs);
                capturedInstructions = opts.Instructions ?? string.Empty;
                if (opts.Tools is not null)
                {
                    capturedTools.AddRange(opts.Tools);
                }
            })
            .ReturnsAsync(new ChatResponse(responseMessages));

        var mockProvider = new Mock<AIContextProvider>(null, null);
        mockProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat(aiContextProviderMessages),
                    Instructions = ctx.AIContext.Instructions + "\ncontext provider instructions",
                    Tools = (ctx.AIContext.Tools ?? []).Concat(new[] { AIFunctionFactory.Create(() => { }, "context provider function") })
                }));
        mockProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new() { AIContextProviders = [mockProvider.Object], ChatOptions = new() { Instructions = "base instructions", Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync(requestMessages, session);

        // Assert
        // Should contain: base instructions, user message, context message, base function, context function
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal("base instructions\ncontext provider instructions", capturedInstructions);
        Assert.Equal("user message", capturedMessages[0].Text);
        Assert.Equal(ChatRole.User, capturedMessages[0].Role);
        Assert.Equal("context provider message", capturedMessages[1].Text);
        Assert.Equal(ChatRole.System, capturedMessages[1].Role);
        Assert.Equal(2, capturedTools.Count);
        Assert.Contains(capturedTools, t => t.Name == "base function");
        Assert.Contains(capturedTools, t => t.Name == "context provider function");

        // Verify that the session was updated with the ai context provider, input and response messages
        var chatHistoryProvider = agent.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(chatHistoryProvider);
        var messages = chatHistoryProvider.GetMessages(session);
        Assert.Equal(3, messages.Count);
        Assert.Equal("user message", messages[0].Text);
        Assert.Equal("context provider message", messages[1].Text);
        Assert.Equal("response", messages[2].Text);

        mockProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.RequestMessages.Count() == requestMessages.Length + aiContextProviderMessages.Length &&
                x.ResponseMessages == responseMessages &&
                x.InvokeException == null), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunAsync invokes any provided AIContextProvider when the downstream GetResponse call fails.
    /// </summary>
    [Fact]
    public async Task RunAsyncInvokesAIContextProviderWhenGetResponseFailsAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatMessage[] aiContextProviderMessages = [new(ChatRole.System, "context provider message")];
        Mock<IChatClient> mockService = new();
        mockService
            .Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("downstream failure"));

        var mockProvider = new Mock<AIContextProvider>(null, null);
        mockProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat(aiContextProviderMessages),
                }));
        mockProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new() { AIContextProviders = [mockProvider.Object], ChatOptions = new() { Instructions = "base instructions", Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(requestMessages));

        // Assert
        mockProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.RequestMessages.Count() == requestMessages.Length + aiContextProviderMessages.Length &&
                x.ResponseMessages == null &&
                x.InvokeException is InvalidOperationException), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunAsync invokes any provided AIContextProvider and succeeds even when the AIContext is empty.
    /// </summary>
    [Fact]
    public async Task RunAsyncInvokesAIContextProviderAndSucceedsWithEmptyAIContextAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        string capturedInstructions = string.Empty;
        List<AITool> capturedTools = [];
        mockService
            .Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
            {
                capturedMessages.AddRange(msgs);
                capturedInstructions = opts.Instructions ?? string.Empty;
                if (opts.Tools is not null)
                {
                    capturedTools.AddRange(opts.Tools);
                }
            })
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        var mockProvider = new Mock<AIContextProvider>(null, null);
        mockProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Instructions = ctx.AIContext.Instructions,
                    Messages = ctx.AIContext.Messages,
                    Tools = ctx.AIContext.Tools
                }));

        ChatClientAgent agent = new(mockService.Object, options: new() { AIContextProviders = [mockProvider.Object], ChatOptions = new() { Instructions = "base instructions", Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        await agent.RunAsync([new(ChatRole.User, "user message")]);

        // Assert
        // Should contain: base instructions, user message, base function
        Assert.Single(capturedMessages);
        Assert.Equal("base instructions", capturedInstructions);
        Assert.Equal("user message", capturedMessages[0].Text);
        Assert.Equal(ChatRole.User, capturedMessages[0].Role);
        Assert.Single(capturedTools);
        Assert.Contains(capturedTools, t => t.Name == "base function");
        mockProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunAsync invokes multiple AIContextProviders in sequence, each receiving the accumulated context.
    /// </summary>
    [Fact]
    public async Task RunAsyncInvokesMultipleAIContextProvidersInOrderAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatMessage[] responseMessages = [new(ChatRole.Assistant, "response")];
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        string capturedInstructions = string.Empty;
        List<AITool> capturedTools = [];
        mockService
            .Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
            {
                capturedMessages.AddRange(msgs);
                capturedInstructions = opts.Instructions ?? string.Empty;
                if (opts.Tools is not null)
                {
                    capturedTools.AddRange(opts.Tools);
                }
            })
            .ReturnsAsync(new ChatResponse(responseMessages));

        // Provider 1: adds a system message and a tool
        var mockProvider1 = new Mock<AIContextProvider>(null, null);
        mockProvider1.SetupGet(p => p.StateKey).Returns("Provider1");
        mockProvider1
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat([new ChatMessage(ChatRole.System, "provider1 context")]).ToList(),
                    Instructions = ctx.AIContext.Instructions + "\nprovider1 instructions",
                    Tools = (ctx.AIContext.Tools ?? []).Concat([AIFunctionFactory.Create(() => { }, "provider1 function")]).ToList()
                }));
        mockProvider1
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        // Provider 2: adds another system message and verifies it receives accumulated context from provider 1
        AIContext? provider2ReceivedContext = null;
        var mockProvider2 = new Mock<AIContextProvider>(null, null);
        mockProvider2.SetupGet(p => p.StateKey).Returns("Provider2");
        mockProvider2
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
            {
                provider2ReceivedContext = ctx.AIContext;
                return new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat([new ChatMessage(ChatRole.System, "provider2 context")]).ToList(),
                    Instructions = ctx.AIContext.Instructions + "\nprovider2 instructions",
                    Tools = (ctx.AIContext.Tools ?? []).Concat([AIFunctionFactory.Create(() => { }, "provider2 function")]).ToList()
                });
            });
        mockProvider2
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            AIContextProviders = [mockProvider1.Object, mockProvider2.Object],
            ChatOptions = new() { Instructions = "base instructions", Tools = [AIFunctionFactory.Create(() => { }, "base function")] }
        });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunAsync(requestMessages, session);

        // Assert
        // Provider 2 should have received accumulated context from provider 1
        Assert.NotNull(provider2ReceivedContext);
        Assert.Contains(provider2ReceivedContext.Messages!, m => m.Text == "provider1 context");
        Assert.Contains("provider1 instructions", provider2ReceivedContext.Instructions);

        // Final captured messages should contain user message + both provider contexts
        Assert.Equal(3, capturedMessages.Count);
        Assert.Equal("user message", capturedMessages[0].Text);
        Assert.Equal("provider1 context", capturedMessages[1].Text);
        Assert.Equal("provider2 context", capturedMessages[2].Text);

        // Instructions should be accumulated
        Assert.Equal("base instructions\nprovider1 instructions\nprovider2 instructions", capturedInstructions);

        // Tools should contain base + both provider tools
        Assert.Equal(3, capturedTools.Count);
        Assert.Contains(capturedTools, t => t.Name == "base function");
        Assert.Contains(capturedTools, t => t.Name == "provider1 function");
        Assert.Contains(capturedTools, t => t.Name == "provider2 function");

        // Both providers should have been invoked
        mockProvider1
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider2
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());

        // Both providers should have been notified of success
        mockProvider1
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.ResponseMessages == responseMessages &&
                x.InvokeException == null), ItExpr.IsAny<CancellationToken>());
        mockProvider2
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.ResponseMessages == responseMessages &&
                x.InvokeException == null), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunAsync invokes InvokedCoreAsync on all AIContextProviders when the downstream GetResponse call fails.
    /// </summary>
    [Fact]
    public async Task RunAsyncInvokesMultipleAIContextProvidersOnFailureAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        Mock<IChatClient> mockService = new();
        mockService
            .Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("downstream failure"));

        var mockProvider1 = new Mock<AIContextProvider>(null, null);
        mockProvider1.SetupGet(p => p.StateKey).Returns("Provider1");
        mockProvider1
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = ctx.AIContext.Messages?.ToList(),
                    Instructions = ctx.AIContext.Instructions,
                    Tools = ctx.AIContext.Tools
                }));
        mockProvider1
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        var mockProvider2 = new Mock<AIContextProvider>(null, null);
        mockProvider2.SetupGet(p => p.StateKey).Returns("Provider2");
        mockProvider2
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = ctx.AIContext.Messages?.ToList(),
                    Instructions = ctx.AIContext.Instructions,
                    Tools = ctx.AIContext.Tools
                }));
        mockProvider2
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            AIContextProviders = [mockProvider1.Object, mockProvider2.Object],
            ChatOptions = new() { Instructions = "base instructions" }
        });

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(requestMessages));

        // Assert - both providers should have been notified of the failure
        mockProvider1
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider2
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());

        mockProvider1
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.InvokeException is InvalidOperationException), ItExpr.IsAny<CancellationToken>());
        mockProvider2
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.InvokeException is InvalidOperationException), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunStreamingAsync invokes multiple AIContextProviders in sequence.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncInvokesMultipleAIContextProvidersAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatResponseUpdate[] responseUpdates = [new(ChatRole.Assistant, "response")];
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        string capturedInstructions = string.Empty;
        mockService
            .Setup(s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
            {
                capturedMessages.AddRange(msgs);
                capturedInstructions = opts.Instructions ?? string.Empty;
            })
            .Returns(ToAsyncEnumerableAsync(responseUpdates));

        var mockProvider1 = new Mock<AIContextProvider>(null, null);
        mockProvider1.SetupGet(p => p.StateKey).Returns("Provider1");
        mockProvider1
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat([new ChatMessage(ChatRole.System, "provider1 context")]).ToList(),
                    Instructions = ctx.AIContext.Instructions + "\nprovider1 instructions",
                    Tools = ctx.AIContext.Tools
                }));
        mockProvider1
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        var mockProvider2 = new Mock<AIContextProvider>(null, null);
        mockProvider2.SetupGet(p => p.StateKey).Returns("Provider2");
        mockProvider2
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat([new ChatMessage(ChatRole.System, "provider2 context")]).ToList(),
                    Instructions = ctx.AIContext.Instructions + "\nprovider2 instructions",
                    Tools = ctx.AIContext.Tools
                }));
        mockProvider2
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(
            mockService.Object,
            options: new()
            {
                ChatOptions = new() { Instructions = "base instructions" },
                AIContextProviders = [mockProvider1.Object, mockProvider2.Object]
            });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var updates = agent.RunStreamingAsync(requestMessages, session);
        _ = await updates.ToAgentResponseAsync();

        // Assert
        Assert.Equal(3, capturedMessages.Count);
        Assert.Equal("user message", capturedMessages[0].Text);
        Assert.Equal("provider1 context", capturedMessages[1].Text);
        Assert.Equal("provider2 context", capturedMessages[2].Text);
        Assert.Equal("base instructions\nprovider1 instructions\nprovider2 instructions", capturedInstructions);

        // Both providers should have been invoked and notified
        mockProvider1
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider2
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider1
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.InvokeException == null), ItExpr.IsAny<CancellationToken>());
        mockProvider2
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.InvokeException == null), ItExpr.IsAny<CancellationToken>());
    }

    #endregion

    #region Property Override Tests

    /// <summary>
    /// Verify that Id property returns metadata Id when provided, otherwise falls back to base implementation.
    /// </summary>
    [Fact]
    public void IdReturnsMetadataIdWhenMetadataProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { Id = "custom-agent-id" };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Equal("custom-agent-id", agent.Id);
    }

    /// <summary>
    /// Verify that Id property falls back to base implementation when metadata is null.
    /// </summary>
    [Fact]
    public void IdFallsBackToBaseImplementationWhenMetadataIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient);

        // Act & Assert
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);

        // Base implementation returns a GUID, so it should be parseable as a GUID
        Assert.True(Guid.TryParse(agent.Id, out _));
    }

    /// <summary>
    /// Verify that Id property falls back to base implementation when metadata Id is null.
    /// </summary>
    [Fact]
    public void IdFallsBackToBaseImplementationWhenMetadataIdIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { Id = null };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);

        // Base implementation returns a GUID, so it should be parseable as a GUID
        Assert.True(Guid.TryParse(agent.Id, out _));
    }

    /// <summary>
    /// Verify that Name property returns metadata Name when provided.
    /// </summary>
    [Fact]
    public void NameReturnsMetadataNameWhenMetadataProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { Name = "Test Agent" };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Equal("Test Agent", agent.Name);
    }

    /// <summary>
    /// Verify that Name property returns null when metadata is null.
    /// </summary>
    [Fact]
    public void NameReturnsNullWhenMetadataIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient);

        // Act & Assert
        Assert.Null(agent.Name);
    }

    /// <summary>
    /// Verify that Name property returns null when metadata Name is null.
    /// </summary>
    [Fact]
    public void NameReturnsNullWhenMetadataNameIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { Name = null };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Null(agent.Name);
    }

    /// <summary>
    /// Verify that Description property returns metadata Description when provided.
    /// </summary>
    [Fact]
    public void DescriptionReturnsMetadataDescriptionWhenMetadataProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { Description = "A helpful test agent" };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Equal("A helpful test agent", agent.Description);
    }

    /// <summary>
    /// Verify that Description property returns null when metadata is null.
    /// </summary>
    [Fact]
    public void DescriptionReturnsNullWhenMetadataIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient);

        // Act & Assert
        Assert.Null(agent.Description);
    }

    /// <summary>
    /// Verify that Description property returns null when metadata Description is null.
    /// </summary>
    [Fact]
    public void DescriptionReturnsNullWhenMetadataDescriptionIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { Description = null };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Null(agent.Description);
    }

    /// <summary>
    /// Verify that Instructions property returns metadata Instructions when provided.
    /// </summary>
    [Fact]
    public void InstructionsReturnsMetadataInstructionsWhenMetadataProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { ChatOptions = new() { Instructions = "You are a helpful assistant" } };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Equal("You are a helpful assistant", agent.Instructions);
    }

    /// <summary>
    /// Verify that Instructions property returns null when metadata is null.
    /// </summary>
    [Fact]
    public void InstructionsReturnsNullWhenMetadataIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient);

        // Act & Assert
        Assert.Null(agent.Instructions);
    }

    /// <summary>
    /// Verify that Instructions property returns null when metadata Instructions is null.
    /// </summary>
    [Fact]
    public void InstructionsReturnsNullWhenMetadataInstructionsIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var metadata = new ChatClientAgentOptions { ChatOptions = new() { Instructions = null } };
        ChatClientAgent agent = new(chatClient, metadata);

        // Act & Assert
        Assert.Null(agent.Instructions);
    }

    #endregion

    #region Options params Constructor Tests

    /// <summary>
    /// Checks that all params are set correctly when using the constructor with optional parameters.
    /// </summary>
    [Fact]
    public void ConstructorUsesOptionalParams()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, instructions: "TestInstructions", name: "TestName", description: "TestDescription", tools: [AIFunctionFactory.Create(() => { })]);

        // Act & Assert
        Assert.Equal("TestInstructions", agent.Instructions);
        Assert.Equal("TestName", agent.Name);
        Assert.Equal("TestDescription", agent.Description);
        Assert.NotNull(agent.ChatOptions);
        Assert.NotNull(agent.ChatOptions.Tools);
        Assert.Single(agent.ChatOptions.Tools!);
    }

    /// <summary>
    /// Verify that ChatOptions is created with instructions when instructions are provided and no tools are provided.
    /// </summary>
    [Fact]
    public void ChatOptionsCreatedWithInstructionsEvenWhenConstructorToolsNotProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, instructions: "TestInstructions", name: "TestName", description: "TestDescription");

        // Act & Assert
        Assert.Equal("TestInstructions", agent.Instructions);
        Assert.Equal("TestName", agent.Name);
        Assert.Equal("TestDescription", agent.Description);
        Assert.NotNull(agent.ChatOptions);
        Assert.Equal("TestInstructions", agent.ChatOptions.Instructions);
    }

    #endregion

    #region Options Constructor Tests

    /// <summary>
    /// Checks that the various properties on <see cref="ChatClientAgent"/> are null or defaulted when not provided to the constructor.
    /// </summary>
    [Fact]
    public void OptionsPropertiesNullOrDefaultWhenNotProvidedToConstructor()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, options: null);

        // Act & Assert
        Assert.NotNull(agent.Id);
        Assert.Null(agent.Instructions);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
        Assert.Null(agent.ChatOptions);
    }

    #endregion

    #region ChatOptions Property Tests

    /// <summary>
    /// Verify that ChatOptions property returns null when agent options are null.
    /// </summary>
    [Fact]
    public void ChatOptionsReturnsNullWhenAgentOptionsAreNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient);

        // Act & Assert
        Assert.Null(agent.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatOptions property returns null when agent options ChatOptions is null.
    /// </summary>
    [Fact]
    public void ChatOptionsReturnsNullWhenAgentOptionsChatOptionsIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var agentOptions = new ChatClientAgentOptions { ChatOptions = null };
        ChatClientAgent agent = new(chatClient, agentOptions);

        // Act & Assert
        Assert.Null(agent.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatOptions property returns a cloned copy when agent options have ChatOptions.
    /// </summary>
    [Fact]
    public void ChatOptionsReturnsClonedCopyWhenAgentOptionsHaveChatOptions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var originalChatOptions = new ChatOptions { MaxOutputTokens = 100, Temperature = 0.5f };
        var agentOptions = new ChatClientAgentOptions { ChatOptions = originalChatOptions };
        ChatClientAgent agent = new(chatClient, agentOptions);

        // Act
        var returnedChatOptions = agent.ChatOptions;

        // Assert
        Assert.NotNull(returnedChatOptions);
        Assert.NotSame(originalChatOptions, returnedChatOptions); // Should be a different instance (cloned)
        Assert.Equal(originalChatOptions.MaxOutputTokens, returnedChatOptions.MaxOutputTokens);
        Assert.Equal(originalChatOptions.Temperature, returnedChatOptions.Temperature);
    }

    #endregion

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns AIAgentMetadata when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsMetadata()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var metadata = new ChatClientMetadata("test-provider");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(metadata);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "test-agent-id",
            Name = "TestAgent",
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var agentMetadata = (AIAgentMetadata)result;
        Assert.Equal("test-provider", agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that GetService returns IChatClient when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingIChatClient_ReturnsChatClient()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService<IChatClient>();

        // Assert
        Assert.NotNull(result);
        Assert.IsType<IChatClient>(result, exactMatch: false);

        // Note: The result will be the AgentInvokedChatClient wrapper, not the original mock
        Assert.Equal("FunctionInvokingChatClient", result.GetType().Name);
    }

    /// <summary>
    /// Verify that GetService returns IChatClient when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingChatClientAgent_ReturnsChatClientAgent()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(result);

        Assert.Same(result, agent);
    }

    /// <summary>
    /// Verify that GetService delegates to the underlying ChatClient for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceType_DelegatesToChatClient()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var customService = new object();
        mockChatClient.Setup(c => c.GetService(typeof(string), null))
            .Returns(customService);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(string));

        // Assert
        Assert.Same(customService, result);
        mockChatClient.Verify(c => c.GetService(typeof(string), null), Times.Once);
    }

    /// <summary>
    /// Verify that GetService returns null for unknown service types when ChatClient returns null.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceTypeWithNullFromChatClient_ReturnsNull()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetService(typeof(string), null))
            .Returns((object?)null);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(string));

        // Assert
        Assert.Null(result);
        mockChatClient.Verify(c => c.GetService(typeof(string), null), Times.Once);
    }

    /// <summary>
    /// Verify that GetService with serviceKey parameter delegates correctly to ChatClient.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_DelegatesToChatClient()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var customService = new object();
        const string ServiceKey = "test-key";
        mockChatClient.Setup(c => c.GetService(typeof(string), ServiceKey))
            .Returns(customService);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(string), ServiceKey);

        // Assert
        Assert.Same(customService, result);
        mockChatClient.Verify(c => c.GetService(typeof(string), ServiceKey), Times.Once);
    }

    /// <summary>
    /// Verify that GetService returns AIAgentMetadata with correct provider name from ChatClientMetadata.
    /// </summary>
    [Theory]
    [InlineData("openai")]
    [InlineData("azure")]
    [InlineData("anthropic")]
    [InlineData(null)]
    public void GetService_RequestingAIAgentMetadata_ReturnsMetadataWithCorrectProviderName(string? providerName)
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = providerName is not null ? new ChatClientMetadata(providerName) : null;
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var agentMetadata = (AIAgentMetadata)result;
        Assert.Equal(providerName, agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that ChatClientAgent returns correct AIAgentMetadata based on ChatClientMetadata.
    /// </summary>
    [Theory]
    [InlineData("openai", "openai")]
    [InlineData("azure", "azure")]
    [InlineData("anthropic", "anthropic")]
    [InlineData(null, null)]
    public void GetService_RequestingAIAgentMetadata_ReturnsCorrectAIAgentMetadataBasedOnProvider(string? chatClientProviderName, string? expectedProviderName)
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = chatClientProviderName is not null ? new ChatClientMetadata(chatClientProviderName) : null;
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Id = "test-agent-id",
            Name = "TestAgent",
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var agentMetadata = (AIAgentMetadata)result;
        Assert.Equal(expectedProviderName, agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that ChatClientAgent metadata is consistent across multiple calls.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsConsistentMetadata()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientMetadata = new ChatClientMetadata("test-provider");
        mockChatClient.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata);

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result1 = agent.GetService(typeof(AIAgentMetadata));
        var result2 = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result1);
        Assert.NotNull(result2);
        Assert.Same(result1, result2); // Should return the same instance
        Assert.IsType<AIAgentMetadata>(result1);
        var agentMetadata = (AIAgentMetadata)result1;
        Assert.Equal("test-provider", agentMetadata.ProviderName);
    }

    /// <summary>
    /// Verify that AIAgentMetadata structure is consistent across different ChatClientAgent configurations.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_StructureIsConsistentAcrossConfigurations()
    {
        // Arrange
        var mockChatClient1 = new Mock<IChatClient>();
        var chatClientMetadata1 = new ChatClientMetadata("openai");
        mockChatClient1.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata1);

        var mockChatClient2 = new Mock<IChatClient>();
        var chatClientMetadata2 = new ChatClientMetadata("azure");
        mockChatClient2.Setup(c => c.GetService(typeof(ChatClientMetadata), null))
            .Returns(chatClientMetadata2);

        var chatClientAgent1 = new ChatClientAgent(mockChatClient1.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions 1" }
        });

        var chatClientAgent2 = new ChatClientAgent(mockChatClient2.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions 2" }
        });

        // Act
        var metadata1 = chatClientAgent1.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;
        var metadata2 = chatClientAgent2.GetService(typeof(AIAgentMetadata)) as AIAgentMetadata;

        // Assert
        Assert.NotNull(metadata1);
        Assert.NotNull(metadata2);

        // Both should have the same type and structure
        Assert.Equal(typeof(AIAgentMetadata), metadata1.GetType());
        Assert.Equal(typeof(AIAgentMetadata), metadata2.GetType());

        // Both should have ProviderName property
        Assert.NotNull(metadata1.ProviderName);
        Assert.NotNull(metadata2.ProviderName);

        // Provider names should be different
        Assert.Equal("openai", metadata1.ProviderName);
        Assert.Equal("azure", metadata2.ProviderName);
        Assert.NotEqual(metadata1.ProviderName, metadata2.ProviderName);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting ChatClientAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingChatClientAgentType_ReturnsBaseImplementation()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(ChatClientAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);

        // Verify that the ChatClient's GetService was not called for this type since base.GetService() handled it
        mockChatClient.Verify(c => c.GetService(typeof(ChatClientAgent), null), Times.Never);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting AIAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentType_ReturnsBaseImplementation()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act
        var result = agent.GetService(typeof(AIAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);

        // Verify that the ChatClient's GetService was not called for this type since base.GetService() handled it
        mockChatClient.Verify(c => c.GetService(typeof(AIAgent), null), Times.Never);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first but continues to derived logic when base returns null.
    /// For IChatClient, it returns the agent's own ChatClient regardless of service key.
    /// </summary>
    [Fact]
    public void GetService_RequestingIChatClientWithServiceKey_ReturnsOwnChatClient()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act - Request IChatClient with a service key (base.GetService will return null due to serviceKey)
        var result = agent.GetService(typeof(IChatClient), "some-key");

        // Assert
        Assert.NotNull(result);
        Assert.IsType<IChatClient>(result, exactMatch: false);

        // Verify that the ChatClient's GetService was NOT called because IChatClient is handled by the agent itself
        mockChatClient.Verify(c => c.GetService(typeof(IChatClient), "some-key"), Times.Never);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first but continues to underlying ChatClient when base returns null and it's not IChatClient or AIAgentMetadata.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceWithServiceKey_CallsUnderlyingChatClient()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetService(typeof(string), "some-key")).Returns("test-result");
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            ChatOptions = new() { Instructions = "Test instructions" }
        });

        // Act - Request string with a service key (base.GetService will return null due to serviceKey)
        var result = agent.GetService(typeof(string), "some-key");

        // Assert
        Assert.NotNull(result);
        Assert.Equal("test-result", result);

        // Verify that the ChatClient's GetService was called after base.GetService() returned null
        mockChatClient.Verify(c => c.GetService(typeof(string), "some-key"), Times.Once);
    }

    #endregion

    #region RunStreamingAsync Tests

    /// <summary>
    /// Verify the streaming invocation and response of <see cref="ChatClientAgent"/>.
    /// </summary>
    [Fact]
    public async Task VerifyChatClientAgentStreamingAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
            [
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh"),
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "at?"),
            ];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(ToAsyncEnumerableAsync(returnUpdates));

        ChatClientAgent agent =
            new(mockService.Object, options: new()
            {
                ChatOptions = new() { Instructions = "test instructions" }
            });

        // Act
        var updates = agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")]);
        List<AgentResponseUpdate> result = [];
        await foreach (var update in updates)
        {
            result.Add(update);
        }

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("wh", result[0].Text);
        Assert.Equal("at?", result[1].Text);

        mockService.Verify(
            x =>
                x.GetStreamingResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(),
                    It.IsAny<ChatOptions>(),
                    It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync uses the ChatHistoryProvider factory when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncUsesChatHistoryProviderWhenNoConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatResponseUpdate[] returnUpdates =
            [
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh"),
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "at?"),
            ];
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(ToAsyncEnumerableAsync(returnUpdates));
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = new InMemoryChatHistoryProvider()
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunStreamingAsync([new(ChatRole.User, "test")], session).ToListAsync();

        // Assert
        var chatHistoryProvider = Assert.IsType<InMemoryChatHistoryProvider>(agent.GetService(typeof(ChatHistoryProvider)));
        var historyMessages = chatHistoryProvider.GetMessages(session);
        Assert.Equal(2, historyMessages.Count);
        Assert.Equal("test", historyMessages[0].Text);
        Assert.Equal("what?", historyMessages[1].Text);
    }

    /// <summary>
    /// Verify that RunStreamingAsync includes chat history in messages sent to the chat client on subsequent calls.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncIncludesChatHistoryInMessagesToChatClientAsync()
    {
        // Arrange
        List<IEnumerable<ChatMessage>> capturedMessages = [];
        Mock<IChatClient> mockService = new();
        ChatResponseUpdate[] returnUpdates =
            [
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "response"),
            ];
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(returnUpdates))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((msgs, _, _) => capturedMessages.Add(msgs.ToList()));
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
        });

        // Act
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        await agent.RunStreamingAsync([new(ChatRole.User, "first")], session).ToListAsync();
        await agent.RunStreamingAsync([new(ChatRole.User, "second")], session).ToListAsync();

        // Assert - the second call should include chat history (first user message + first response) plus the new message
        Assert.Equal(2, capturedMessages.Count);
        var secondCallMessages = capturedMessages[1].ToList();
        Assert.Equal(3, secondCallMessages.Count);
        Assert.Equal("first", secondCallMessages[0].Text);
        Assert.Equal("response", secondCallMessages[1].Text);
        Assert.Equal("second", secondCallMessages[2].Text);
    }

    /// <summary>
    /// Verify that RunStreamingAsync throws when a <see cref="ChatHistoryProvider"/> is provided and the chat client returns a conversation id.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncThrowsWhenChatHistoryProviderProvidedAndConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatResponseUpdate[] returnUpdates =
            [
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh") { ConversationId = "ConvId" },
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "at?") { ConversationId = "ConvId" },
            ];
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(ToAsyncEnumerableAsync(returnUpdates));
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = new() { Instructions = "test instructions" },
            ChatHistoryProvider = new InMemoryChatHistoryProvider()
        });

        // Act & Assert
        ChatClientAgentSession? session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await agent.RunStreamingAsync([new(ChatRole.User, "test")], session).ToListAsync());
        Assert.Equal("Only ConversationId or ChatHistoryProvider may be used, but not both. The service returned a conversation id indicating server-side chat history management, but the agent has a ChatHistoryProvider configured.", exception.Message);
    }

    /// <summary>
    /// Verify that RunStreamingAsync invokes any provided AIContextProvider and uses the result.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncInvokesAIContextProviderAndUsesResultAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatResponseUpdate[] responseUpdates = [new(ChatRole.Assistant, "response")];
        ChatMessage[] aiContextProviderMessages = [new(ChatRole.System, "context provider message")];
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        string capturedInstructions = string.Empty;
        List<AITool> capturedTools = [];
        mockService
            .Setup(s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
            {
                capturedMessages.AddRange(msgs);
                capturedInstructions = opts.Instructions ?? string.Empty;
                if (opts.Tools is not null)
                {
                    capturedTools.AddRange(opts.Tools);
                }
            })
            .Returns(ToAsyncEnumerableAsync(responseUpdates));

        var mockProvider = new Mock<AIContextProvider>(null, null);
        mockProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat(aiContextProviderMessages),
                    Instructions = ctx.AIContext.Instructions + "\ncontext provider instructions",
                    Tools = (ctx.AIContext.Tools ?? []).Concat(new[] { AIFunctionFactory.Create(() => { }, "context provider function") })
                }));
        mockProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(
            mockService.Object,
            options: new()
            {
                ChatOptions = new() { Instructions = "base instructions", Tools = [AIFunctionFactory.Create(() => { }, "base function")] },
                AIContextProviders = [mockProvider.Object]
            });

        // Act
        var session = await agent.CreateSessionAsync() as ChatClientAgentSession;
        var updates = agent.RunStreamingAsync(requestMessages, session);
        _ = await updates.ToAgentResponseAsync();

        // Assert
        // Should contain: base instructions, user message, context message, base function, context function
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal("base instructions\ncontext provider instructions", capturedInstructions);
        Assert.Equal("user message", capturedMessages[0].Text);
        Assert.Equal(ChatRole.User, capturedMessages[0].Role);
        Assert.Equal("context provider message", capturedMessages[1].Text);
        Assert.Equal(ChatRole.System, capturedMessages[1].Role);
        Assert.Equal(2, capturedTools.Count);
        Assert.Contains(capturedTools, t => t.Name == "base function");
        Assert.Contains(capturedTools, t => t.Name == "context provider function");

        // Verify that the session was updated with the input, ai context provider, and response messages
        var chatHistoryProvider = agent.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(chatHistoryProvider);
        var historyMessages2 = chatHistoryProvider.GetMessages(session);
        Assert.Equal(3, historyMessages2.Count);
        Assert.Equal("user message", historyMessages2[0].Text);
        Assert.Equal("context provider message", historyMessages2[1].Text);
        Assert.Equal("response", historyMessages2[2].Text);

        mockProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.RequestMessages.Count() == requestMessages.Length + aiContextProviderMessages.Length &&
                x.ResponseMessages!.Count() == 1 &&
                x.ResponseMessages!.ElementAt(0).Text == "response" &&
                x.InvokeException == null), ItExpr.IsAny<CancellationToken>());
    }

    /// <summary>
    /// Verify that RunStreamingAsync invokes any provided AIContextProvider when the downstream GetStreamingResponse call fails.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncInvokesAIContextProviderWhenGetResponseFailsAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatMessage[] aiContextProviderMessages = [new(ChatRole.System, "context provider message")];
        Mock<IChatClient> mockService = new();
        mockService
            .Setup(s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("downstream failure"));

        var mockProvider = new Mock<AIContextProvider>(null, null);
        mockProvider
            .Protected()
            .Setup<ValueTask<AIContext>>("InvokingCoreAsync", ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns((AIContextProvider.InvokingContext ctx, CancellationToken _) =>
                new ValueTask<AIContext>(new AIContext
                {
                    Messages = (ctx.AIContext.Messages ?? []).Concat(aiContextProviderMessages),
                }));
        mockProvider
            .Protected()
            .Setup<ValueTask>("InvokedCoreAsync", ItExpr.IsAny<AIContextProvider.InvokedContext>(), ItExpr.IsAny<CancellationToken>())
            .Returns(new ValueTask());

        ChatClientAgent agent = new(
            mockService.Object,
            options: new()
            {
                ChatOptions = new() { Instructions = "base instructions", Tools = [AIFunctionFactory.Create(() => { }, "base function")] },
                AIContextProviders = [mockProvider.Object]
            });

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            var updates = agent.RunStreamingAsync(requestMessages);
            await updates.ToAgentResponseAsync();
        });

        // Assert
        mockProvider
            .Protected()
            .Verify<ValueTask<AIContext>>("InvokingCoreAsync", Times.Once(), ItExpr.IsAny<AIContextProvider.InvokingContext>(), ItExpr.IsAny<CancellationToken>());
        mockProvider
            .Protected()
            .Verify<ValueTask>("InvokedCoreAsync", Times.Once(), ItExpr.Is<AIContextProvider.InvokedContext>(x =>
                x.RequestMessages.Count() == requestMessages.Length + aiContextProviderMessages.Length &&
                x.ResponseMessages == null &&
                x.InvokeException is InvalidOperationException), ItExpr.IsAny<CancellationToken>());
    }

    #endregion

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> values)
    {
        await Task.Yield();
        foreach (var update in values)
        {
            yield return update;
        }
    }

    [JsonSourceGenerationOptions(UseStringEnumConverter = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(Animal))]
    private sealed partial class JsonContext2 : JsonSerializerContext;

    private sealed class TestAIContextProvider(string stateKey) : AIContextProvider
    {
        public override string StateKey => stateKey;

        protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(context.AIContext);
    }

    private sealed class TestChatHistoryProvider(string stateKey) : ChatHistoryProvider
    {
        public override string StateKey => stateKey;

        protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default)
            => new(context.RequestMessages);

        protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
            => default;
    }
}
