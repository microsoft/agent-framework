// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

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
                    Instructions = "test instructions",
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
                Instructions = "test instructions"
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
        ChatClientAgent agent = new(chatClient, options: new() { Instructions = "test instructions" });

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

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

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

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "base instructions" });
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

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions", Name = authorName });

        // Act
        var result = await agent.RunAsync([new(ChatRole.User, "test")]);

        // Assert
        Assert.All(result.Messages, msg => Assert.Equal(authorName, msg.AuthorName));
    }

    /// <summary>
    /// Verify that RunAsync works with existing thread and can retreive messages if the thread has a MessageStore.
    /// </summary>
    [Fact]
    public async Task RunAsyncRetrievesMessagesFromThreadWhenThreadStoresMessagesThreadAsync()
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

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

        // Create a thread using the agent's GetNewThread method
        var thread = agent.GetNewThread();

        // Act
        await agent.RunAsync([new(ChatRole.User, "new message")], thread: thread);

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

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = null });

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

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

        // Act
        await agent.RunAsync([]);

        // Assert
        // Should only contain the instructions
        Assert.Empty(capturedMessages);
    }

    /// <summary>
    /// Verify that RunAsync does not throw when providing a thread with a ThreadId and a Conversationid
    /// via ChatOptions and the two are the same.
    /// </summary>
    [Fact]
    public async Task RunAsyncDoesNotThrowWhenSpecifyingTwoSameThreadIdsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { ConversationId = "ConvId" };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.ConversationId == "ConvId"),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new() { ConversationId = "ConvId" };

        // Act & Assert
        var response = await agent.RunAsync([new(ChatRole.User, "test")], thread, options: new ChatClientAgentRunOptions(chatOptions));
        Assert.NotNull(response);
    }

    /// <summary>
    /// Verify that RunAsync throws when providing a thread with a ThreadId and a Conversationid
    /// via ChatOptions and the two are different.
    /// </summary>
    [Fact]
    public async Task RunAsyncThrowsWhenSpecifyingTwoDifferentThreadIdsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { ConversationId = "ConvId" };
        Mock<IChatClient> mockService = new();

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new() { ConversationId = "ThreadId" };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread, options: new ChatClientAgentRunOptions(chatOptions)));
    }

    /// <summary>
    /// Verify that RunAsync clones the ChatOptions when providing a thread with a ThreadId and a ChatOptions.
    /// </summary>
    [Fact]
    public async Task RunAsyncClonesChatOptionsToAddThreadIdAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 100 && opts.ConversationId == "ConvId"),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new() { ConversationId = "ConvId" };

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], thread, options: new ChatClientAgentRunOptions(chatOptions));

        // Assert
        Assert.Null(chatOptions.ConversationId);
    }

    /// <summary>
    /// Verify that RunAsync throws if a thread is provided that uses a conversation id already, but the service does not return one on invoke.
    /// </summary>
    [Fact]
    public async Task RunAsyncThrowsForMissingConversationIdWithConversationIdThreadAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new() { ConversationId = "ConvId" };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread));
    }

    /// <summary>
    /// Verify that RunAsync sets the ConversationId on the thread when the service returns one.
    /// </summary>
    [Fact]
    public async Task RunAsyncSetsConversationIdOnThreadWhenReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "test instructions" });
        ChatClientAgentThread thread = new();

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], thread);

        // Assert
        Assert.Equal("ConvId", thread.ConversationId);
    }

    /// <summary>
    /// Verify that RunAsync uses the ChatMessageStore factory when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsyncUsesChatMessageStoreWhenNoConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));
        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, ChatMessageStore>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>())).Returns(new InMemoryChatMessageStore());
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = agent.GetNewThread() as ChatClientAgentThread;
        await agent.RunAsync([new(ChatRole.User, "test")], thread);

        // Assert
        var messageStore = Assert.IsType<InMemoryChatMessageStore>(thread!.MessageStore);
        Assert.Equal(2, messageStore.Count);
        Assert.Equal("test", messageStore[0].Text);
        Assert.Equal("response", messageStore[1].Text);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>()), Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync doesn't use the ChatMessageStore factory when the chat client returns a conversation id.
    /// </summary>
    [Fact]
    public async Task RunAsyncIgnoresChatMessageStoreWhenConversationIdReturnedByChatClientAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ConversationId = "ConvId" });
        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, ChatMessageStore>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>())).Returns(new InMemoryChatMessageStore());
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = agent.GetNewThread() as ChatClientAgentThread;
        await agent.RunAsync([new(ChatRole.User, "test")], thread);

        // Assert
        Assert.Equal("ConvId", thread!.ConversationId);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>()), Times.Never);
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

        var mockProvider = new Mock<AIContextProvider>();
        mockProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = aiContextProviderMessages,
                Instructions = "context provider instructions",
                Tools = [AIFunctionFactory.Create(() => { }, "context provider function")]
            });
        mockProvider
            .Setup(p => p.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "base instructions", AIContextProviderFactory = _ => mockProvider.Object, ChatOptions = new() { Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        var thread = agent.GetNewThread() as ChatClientAgentThread;
        await agent.RunAsync(requestMessages, thread);

        // Assert
        // Should contain: base instructions, context message, user message, base function, context function
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal("base instructions\ncontext provider instructions", capturedInstructions);
        Assert.Equal("context provider message", capturedMessages[0].Text);
        Assert.Equal(ChatRole.System, capturedMessages[0].Role);
        Assert.Equal("user message", capturedMessages[1].Text);
        Assert.Equal(ChatRole.User, capturedMessages[1].Role);
        Assert.Equal(2, capturedTools.Count);
        Assert.Contains(capturedTools, t => t.Name == "base function");
        Assert.Contains(capturedTools, t => t.Name == "context provider function");

        // Verify that the thread was updated with the input, ai context and response messages
        var messageStore = Assert.IsType<InMemoryChatMessageStore>(thread!.MessageStore);
        Assert.Equal(3, messageStore.Count);
        Assert.Equal("user message", messageStore[0].Text);
        Assert.Equal("context provider message", messageStore[1].Text);
        Assert.Equal("response", messageStore[2].Text);

        mockProvider.Verify(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider.Verify(p => p.InvokedAsync(It.Is<AIContextProvider.InvokedContext>(x =>
            x.RequestMessages == requestMessages &&
            x.AIContextProviderMessages == aiContextProviderMessages &&
            x.ResponseMessages == responseMessages &&
            x.InvokeException == null), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync invokes any provided AIContextProvider when the downstream GetResponse call fails.
    /// </summary>
    [Fact]
    public async Task RunAsyncInvokesAIContextProviderWhenGetResponseFailsAsync()
    {
        // Arrange
        ChatMessage[] requestMessages = [new(ChatRole.User, "user message")];
        ChatMessage[] responseMessages = [new(ChatRole.Assistant, "response")];
        ChatMessage[] aiContextProviderMessages = [new(ChatRole.System, "context provider message")];
        Mock<IChatClient> mockService = new();
        mockService
            .Setup(s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("downstream failure"));

        var mockProvider = new Mock<AIContextProvider>();
        mockProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = aiContextProviderMessages,
            });
        mockProvider
            .Setup(p => p.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "base instructions", AIContextProviderFactory = _ => mockProvider.Object, ChatOptions = new() { Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(requestMessages));

        // Assert
        mockProvider.Verify(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider.Verify(p => p.InvokedAsync(It.Is<AIContextProvider.InvokedContext>(x =>
            x.RequestMessages == requestMessages &&
            x.AIContextProviderMessages == aiContextProviderMessages &&
            x.ResponseMessages == null &&
            x.InvokeException is InvalidOperationException), It.IsAny<CancellationToken>()), Times.Once);
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

        var mockProvider = new Mock<AIContextProvider>();
        mockProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext());

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "base instructions", AIContextProviderFactory = _ => mockProvider.Object, ChatOptions = new() { Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

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
        mockProvider.Verify(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion

    #region RunAsync Structured Output Tests

    /// <summary>
    /// Verify the invocation of <see cref="ChatClientAgent"/> with specified type parameter is
    /// propagated to the underlying <see cref="IChatClient"/> call and the expected structured output is returned.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithTypeParameterInvokesChatClientMethodForStructuredOutputAsync()
    {
        // Arrange
        Animal expectedSO = new() { Id = 1, FullName = "Tigger", Species = Species.Tiger };

        Mock<IChatClient> mockService = new();
        mockService.Setup(s => s
            .GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(expectedSO, JsonContext2.Default.Animal)))
            {
                ResponseId = "test",
            });

        ChatClientAgent agent = new(mockService.Object, options: new());

        // Act
        AgentRunResponse<Animal> agentRunResponse = await agent.RunAsync<Animal>(messages: [new(ChatRole.User, "Hello")], serializerOptions: JsonContext2.Default.Options);

        // Assert
        Assert.Single(agentRunResponse.Messages);

        Assert.NotNull(agentRunResponse.Result);
        Assert.Equal(expectedSO.Id, agentRunResponse.Result.Id);
        Assert.Equal(expectedSO.FullName, agentRunResponse.Result.FullName);
        Assert.Equal(expectedSO.Species, agentRunResponse.Result.Species);
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
        var metadata = new ChatClientAgentOptions { Instructions = "You are a helpful assistant" };
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
        var metadata = new ChatClientAgentOptions { Instructions = null };
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
    /// Verify that ChatOptions property returns null when no params are provided that require a ChatOptions instance.
    /// </summary>
    [Fact]
    public void ChatOptionsReturnsNullWhenConstructorToolsNotProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, instructions: "TestInstructions", name: "TestName", description: "TestDescription");

        // Act & Assert
        Assert.Equal("TestInstructions", agent.Instructions);
        Assert.Equal("TestName", agent.Name);
        Assert.Equal("TestDescription", agent.Description);
        Assert.Null(agent.ChatOptions);
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

    #region ChatOptions Merging Tests

    /// <summary>
    /// Verify that ChatOptions merging works when agent has ChatOptions but request doesn't.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesAgentOptionsWhenRequestHasNoneAsync()
    {
        // Arrange
        var agentChatOptions = new ChatOptions { MaxOutputTokens = 100, Temperature = 0.7f };
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal(100, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.7f, capturedChatOptions.Temperature);
        Assert.Equal("test instructions", capturedChatOptions.Instructions);
    }

    [Fact]
    public async Task ChatOptionsMergingUsesAgentOptionsConstructorWhenRequestHasNoneAsync()
    {
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
                s => s.GetResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(),
                    It.IsAny<ChatOptions>(),
                    It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new("test instructions"));
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal("test instructions", capturedChatOptions.Instructions);
    }

    /// <summary>
    /// Verify that ChatOptions merging works when request has ChatOptions but agent doesn't.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesRequestOptionsWhenAgentHasNoneAsync()
    {
        // Arrange
        var requestChatOptions = new ChatOptions { MaxOutputTokens = 200, Temperature = 0.3f, Instructions = "test instructions" };
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(requestChatOptions, capturedChatOptions); // Should be the same instance since no merging needed
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.3f, capturedChatOptions.Temperature);
        Assert.Equal("test instructions", capturedChatOptions.Instructions);
    }

    /// <summary>
    /// Verify that ChatOptions merging prioritizes request options over agent options.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingPrioritizesRequestOptionsOverAgentOptionsAsync()
    {
        // Arrange
        var agentChatOptions = new ChatOptions
        {
            MaxOutputTokens = 100,
            Temperature = 0.7f,
            TopP = 0.9f,
            ModelId = "agent-model",
            AdditionalProperties = new AdditionalPropertiesDictionary { ["key"] = "agent-value" }
        };
        var requestChatOptions = new ChatOptions
        {
            // TopP and ModelId not set, should use agent values
            MaxOutputTokens = 200,
            Temperature = 0.3f,
            AdditionalProperties = new AdditionalPropertiesDictionary { ["key"] = "request-value" },
            Instructions = "request instructions"
        };
        var expectedChatOptionsMerge = new ChatOptions
        {
            MaxOutputTokens = 200, // Request value takes priority
            Temperature = 0.3f, // Request value takes priority
            AdditionalProperties = new AdditionalPropertiesDictionary { ["key"] = "request-value" }, // Request value takes priority
            TopP = 0.9f, // Agent value used when request doesn't specify
            ModelId = "agent-model", // Agent value used when request doesn't specify
            Instructions = "test instructions\nrequest instructions" // Request is in addition to agent instructions
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(expectedChatOptionsMerge, capturedChatOptions); // Should be the same instance (modified in place)
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens); // Request value takes priority
        Assert.Equal(0.3f, capturedChatOptions.Temperature); // Request value takes priority
        Assert.NotNull(capturedChatOptions.AdditionalProperties);
        Assert.Equal("request-value", capturedChatOptions.AdditionalProperties["key"]); // Request value takes priority
        Assert.Equal(0.9f, capturedChatOptions.TopP); // Agent value used when request doesn't specify
        Assert.Equal("agent-model", capturedChatOptions.ModelId); // Agent value used when request doesn't specify
    }

    /// <summary>
    /// Verify that ChatOptions merging returns null when both agent and request have no ChatOptions.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingReturnsNullWhenBothAgentAndRequestHaveNoneAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages);

        // Assert
        Assert.Null(capturedChatOptions);
    }

    /// <summary>
    /// Verify that ChatOptions merging concatenates Tools from agent and request.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingConcatenatesToolsFromAgentAndRequestAsync()
    {
        // Arrange
        var agentTool = AIFunctionFactory.Create(() => "agent tool");
        var requestTool = AIFunctionFactory.Create(() => "request tool");

        var agentChatOptions = new ChatOptions
        {
            Tools = [agentTool]
        };
        var requestChatOptions = new ChatOptions
        {
            Tools = [requestTool]
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Equal(2, capturedChatOptions.Tools.Count);

        // Request tools should come first, then agent tools
        Assert.Contains(requestTool, capturedChatOptions.Tools);
        Assert.Contains(agentTool, capturedChatOptions.Tools);
    }

    /// <summary>
    /// Verify that ChatOptions merging uses agent Tools when request has no Tools.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesAgentToolsWhenRequestHasNoToolsAsync()
    {
        // Arrange
        var agentTool = AIFunctionFactory.Create(() => "agent tool");

        var agentChatOptions = new ChatOptions
        {
            Tools = [agentTool]
        };
        var requestChatOptions = new ChatOptions
        {
            // No Tools specified
            MaxOutputTokens = 100
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Single(capturedChatOptions.Tools);
        Assert.Contains(agentTool, capturedChatOptions.Tools); // Should contain the agent's tool
    }

    /// <summary>
    /// Verify that ChatOptions merging uses RawRepresentationFactory from request first, with fallback to agent.
    /// </summary>
    [Theory]
    [InlineData("MockAgentSetting", "MockRequestSetting", "MockRequestSetting")]
    [InlineData("MockAgentSetting", null, "MockAgentSetting")]
    [InlineData(null, "MockRequestSetting", "MockRequestSetting")]
    public async Task ChatOptionsMergingUsesRawRepresentationFactoryWithFallbackAsync(string? agentSetting, string? requestSetting, string expectedSetting)
    {
        // Arrange
        var agentChatOptions = new ChatOptions
        {
            RawRepresentationFactory = _ => agentSetting
        };
        var requestChatOptions = new ChatOptions
        {
            RawRepresentationFactory = _ => requestSetting
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.RawRepresentationFactory);
        Assert.Equal(expectedSetting, capturedChatOptions.RawRepresentationFactory(null!));
    }

    /// <summary>
    /// Verify that ChatOptions merging handles all scalar properties correctly.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingHandlesAllScalarPropertiesCorrectlyAsync()
    {
        // Arrange
        var agentChatOptions = new ChatOptions
        {
            MaxOutputTokens = 100,
            Temperature = 0.7f,
            TopP = 0.9f,
            TopK = 50,
            PresencePenalty = 0.1f,
            FrequencyPenalty = 0.2f,
            Instructions = "agent instructions",
            ModelId = "agent-model",
            Seed = 12345,
            ConversationId = "agent-conversation",
            AllowMultipleToolCalls = true,
            StopSequences = ["agent-stop"]
        };
        var requestChatOptions = new ChatOptions
        {
            MaxOutputTokens = 200,
            Temperature = 0.3f,
            Instructions = "request instructions",

            // Other properties not set, should use agent values
            StopSequences = ["request-stop"]
        };

        var expectedChatOptionsMerge = new ChatOptions
        {
            MaxOutputTokens = 200,
            Temperature = 0.3f,

            // Agent value used when request doesn't specify
            TopP = 0.9f,
            TopK = 50,
            PresencePenalty = 0.1f,
            FrequencyPenalty = 0.2f,
            Instructions = "test instructions\nrequest instructions",
            ModelId = "agent-model",
            Seed = 12345,
            ConversationId = "agent-conversation",
            AllowMultipleToolCalls = true,

            // Merged StopSequences
            StopSequences = ["request-stop", "agent-stop"]
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(expectedChatOptionsMerge, capturedChatOptions); // Should be the equivalent instance (modified in place)

        // Request values should take priority
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.3f, capturedChatOptions.Temperature);

        // Merge StopSequences
        Assert.Equal(["request-stop", "agent-stop"], capturedChatOptions.StopSequences);

        // Agent values should be used when request doesn't specify
        Assert.Equal(0.9f, capturedChatOptions.TopP);
        Assert.Equal(50, capturedChatOptions.TopK);
        Assert.Equal(0.1f, capturedChatOptions.PresencePenalty);
        Assert.Equal(0.2f, capturedChatOptions.FrequencyPenalty);
        Assert.Equal("agent-model", capturedChatOptions.ModelId);
        Assert.Equal(12345, capturedChatOptions.Seed);
        Assert.Equal("agent-conversation", capturedChatOptions.ConversationId);
        Assert.Equal(true, capturedChatOptions.AllowMultipleToolCalls);
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions 1"
        });

        var chatClientAgent2 = new ChatClientAgent(mockChatClient2.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions 2"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
            Instructions = "Test instructions"
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
                Instructions = "test instructions"
            });

        // Act
        var updates = agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")]);
        List<AgentRunResponseUpdate> result = [];
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
    /// Verify that RunStreamingAsync uses the ChatMessageStore factory when the chat client returns no conversation id.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncUsesChatMessageStoreWhenNoConversationIdReturnedByChatClientAsync()
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
        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, ChatMessageStore>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>())).Returns(new InMemoryChatMessageStore());
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = agent.GetNewThread() as ChatClientAgentThread;
        await agent.RunStreamingAsync([new(ChatRole.User, "test")], thread).ToListAsync();

        // Assert
        var messageStore = Assert.IsType<InMemoryChatMessageStore>(thread!.MessageStore);
        Assert.Equal(2, messageStore.Count);
        Assert.Equal("test", messageStore[0].Text);
        Assert.Equal("what?", messageStore[1].Text);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>()), Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync doesn't use the ChatMessageStore factory when the chat client returns a conversation id.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncIgnoresChatMessageStoreWhenConversationIdReturnedByChatClientAsync()
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
        Mock<Func<ChatClientAgentOptions.ChatMessageStoreFactoryContext, ChatMessageStore>> mockFactory = new();
        mockFactory.Setup(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>())).Returns(new InMemoryChatMessageStore());
        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            Instructions = "test instructions",
            ChatMessageStoreFactory = mockFactory.Object
        });

        // Act
        ChatClientAgentThread? thread = agent.GetNewThread() as ChatClientAgentThread;
        await agent.RunStreamingAsync([new(ChatRole.User, "test")], thread).ToListAsync();

        // Assert
        Assert.Equal("ConvId", thread!.ConversationId);
        mockFactory.Verify(f => f(It.IsAny<ChatClientAgentOptions.ChatMessageStoreFactoryContext>()), Times.Never);
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

        var mockProvider = new Mock<AIContextProvider>();
        mockProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = aiContextProviderMessages,
                Instructions = "context provider instructions",
                Tools = [AIFunctionFactory.Create(() => { }, "context provider function")]
            });
        mockProvider
            .Setup(p => p.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "base instructions", AIContextProviderFactory = _ => mockProvider.Object, ChatOptions = new() { Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        var thread = agent.GetNewThread() as ChatClientAgentThread;
        var updates = agent.RunStreamingAsync(requestMessages, thread);
        _ = await updates.ToAgentRunResponseAsync();

        // Assert
        // Should contain: base instructions, context message, user message, base function, context function
        Assert.Equal(2, capturedMessages.Count);
        Assert.Equal("base instructions\ncontext provider instructions", capturedInstructions);
        Assert.Equal("context provider message", capturedMessages[0].Text);
        Assert.Equal(ChatRole.System, capturedMessages[0].Role);
        Assert.Equal("user message", capturedMessages[1].Text);
        Assert.Equal(ChatRole.User, capturedMessages[1].Role);
        Assert.Equal(2, capturedTools.Count);
        Assert.Contains(capturedTools, t => t.Name == "base function");
        Assert.Contains(capturedTools, t => t.Name == "context provider function");

        // Verify that the thread was updated with the input, ai context and response messages
        var messageStore = Assert.IsType<InMemoryChatMessageStore>(thread!.MessageStore);
        Assert.Equal(3, messageStore.Count);
        Assert.Equal("user message", messageStore[0].Text);
        Assert.Equal("context provider message", messageStore[1].Text);
        Assert.Equal("response", messageStore[2].Text);

        mockProvider.Verify(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider.Verify(p => p.InvokedAsync(It.Is<AIContextProvider.InvokedContext>(x =>
            x.RequestMessages == requestMessages &&
            x.AIContextProviderMessages == aiContextProviderMessages &&
            x.ResponseMessages!.Count() == 1 &&
            x.ResponseMessages!.ElementAt(0).Text == "response" &&
            x.InvokeException == null), It.IsAny<CancellationToken>()), Times.Once);
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

        var mockProvider = new Mock<AIContextProvider>();
        mockProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = aiContextProviderMessages,
            });
        mockProvider
            .Setup(p => p.InvokedAsync(It.IsAny<AIContextProvider.InvokedContext>(), It.IsAny<CancellationToken>()))
            .Returns(new ValueTask());

        ChatClientAgent agent = new(mockService.Object, options: new() { Instructions = "base instructions", AIContextProviderFactory = _ => mockProvider.Object, ChatOptions = new() { Tools = [AIFunctionFactory.Create(() => { }, "base function")] } });

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            var updates = agent.RunStreamingAsync(requestMessages);
            await updates.ToAgentRunResponseAsync();
        });

        // Assert
        mockProvider.Verify(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()), Times.Once);
        mockProvider.Verify(p => p.InvokedAsync(It.Is<AIContextProvider.InvokedContext>(x =>
            x.RequestMessages == requestMessages &&
            x.AIContextProviderMessages == aiContextProviderMessages &&
            x.ResponseMessages == null &&
            x.InvokeException is InvalidOperationException), It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion

    #region GetNewThread Tests

    [Fact]
    public void GetNewThreadUsesAIContextProviderFactoryIfProvided()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var mockContextProvider = new Mock<AIContextProvider>();
        var factoryCalled = false;
        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            Instructions = "Test instructions",
            AIContextProviderFactory = _ =>
            {
                factoryCalled = true;
                return mockContextProvider.Object;
            }
        });

        // Act
        var thread = agent.GetNewThread();

        // Assert
        Assert.True(factoryCalled, "AIContextProviderFactory was not called.");
        Assert.IsType<ChatClientAgentThread>(thread);
        var typedThread = (ChatClientAgentThread)thread;
        Assert.Same(mockContextProvider.Object, typedThread.AIContextProvider);
    }

    #endregion

    #region Background Responses Tests

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunAsyncPropagatesBackgroundResponsesPropertiesToChatClientAsync(bool providePropsViaChatOptions)
    {
        // Arrange
        object continuationToken = new();
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ContinuationToken = null });

        AgentRunOptions agentRunOptions;

        if (providePropsViaChatOptions)
        {
            ChatOptions chatOptions = new()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };

            agentRunOptions = new ChatClientAgentRunOptions(chatOptions);
        }
        else
        {
            agentRunOptions = new AgentRunOptions()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };
        }

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentThread thread = new();

        // Act
        await agent.RunAsync(thread, options: agentRunOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.True(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunAsyncPrioritizesBackgroundResponsesPropertiesFromAgentRunOptionsOverOnesFromChatOptionsAsync()
    {
        // Arrange
        object continuationToken1 = new();
        object continuationToken2 = new();
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]) { ContinuationToken = null });

        ChatOptions chatOptions = new()
        {
            AllowBackgroundResponses = true,
            ContinuationToken = continuationToken1
        };

        ChatClientAgentRunOptions agentRunOptions = new(chatOptions)
        {
            AllowBackgroundResponses = false,
            ContinuationToken = continuationToken2
        };

        ChatClientAgent agent = new(mockChatClient.Object);

        // Act
        await agent.RunAsync(options: agentRunOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.False(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken2, capturedChatOptions.ContinuationToken);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RunStreamingAsyncPropagatesBackgroundResponsesPropertiesToChatClientAsync(bool providePropsViaChatOptions)
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh"),
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "at?"),
        ];

        object continuationToken = new();
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        AgentRunOptions agentRunOptions;

        if (providePropsViaChatOptions)
        {
            ChatOptions chatOptions = new()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };

            agentRunOptions = new ChatClientAgentRunOptions(chatOptions);
        }
        else
        {
            agentRunOptions = new AgentRunOptions()
            {
                AllowBackgroundResponses = true,
                ContinuationToken = continuationToken
            };
        }

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentThread thread = new();

        // Act
        await foreach (var _ in agent.RunStreamingAsync(thread, options: agentRunOptions))
        {
        }

        // Assert
        Assert.NotNull(capturedChatOptions);

        Assert.True(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunStreamingAsyncPrioritizesBackgroundResponsesPropertiesFromAgentRunOptionsOverOnesFromChatOptionsAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh"),
        ];

        object continuationToken1 = new();
        object continuationToken2 = new();
        ChatOptions? capturedChatOptions = null;
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((m, co, ct) => capturedChatOptions = co)
            .Returns(ToAsyncEnumerableAsync(returnUpdates));

        ChatOptions chatOptions = new()
        {
            AllowBackgroundResponses = true,
            ContinuationToken = continuationToken1
        };

        ChatClientAgentRunOptions agentRunOptions = new(chatOptions)
        {
            AllowBackgroundResponses = false,
            ContinuationToken = continuationToken2
        };

        ChatClientAgent agent = new(mockChatClient.Object);

        // Act
        await foreach (var _ in agent.RunStreamingAsync(options: agentRunOptions))
        {
        }

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.False(capturedChatOptions.AllowBackgroundResponses);
        Assert.Same(continuationToken2, capturedChatOptions.ContinuationToken);
    }

    [Fact]
    public async Task RunAsyncPropagatesContinuationTokenFromChatResponseToAgentRunResponseAsync()
    {
        // Arrange
        object continuationToken = new();
        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "partial")]) { ContinuationToken = continuationToken });

        ChatClientAgent agent = new(mockChatClient.Object);
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { AllowBackgroundResponses = true });

        ChatClientAgentThread thread = new();

        // Act
        var response = await agent.RunAsync([new(ChatRole.User, "hi")], thread, options: runOptions);

        // Assert
        Assert.Same(continuationToken, response.ContinuationToken);
    }

    [Fact]
    public async Task RunStreamingAsyncPropagatesContinuationTokensFromUpdatesAsync()
    {
        // Arrange
        object token1 = new();
        ChatResponseUpdate[] expectedUpdates =
        [
            new ChatResponseUpdate(ChatRole.Assistant, "pa") { ContinuationToken = token1 },
            new ChatResponseUpdate(ChatRole.Assistant, "rt") { ContinuationToken = null } // terminal
        ];

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(expectedUpdates));

        ChatClientAgent agent = new(mockChatClient.Object);

        ChatClientAgentThread thread = new();

        // Act
        var actualUpdates = new List<AgentRunResponseUpdate>();
        await foreach (var u in agent.RunStreamingAsync([new(ChatRole.User, "hi")], thread, options: new ChatClientAgentRunOptions(new ChatOptions { AllowBackgroundResponses = true })))
        {
            actualUpdates.Add(u);
        }

        // Assert
        Assert.Equal(2, actualUpdates.Count);
        Assert.Same(token1, actualUpdates[0].ContinuationToken);
        Assert.Null(actualUpdates[1].ContinuationToken); // last update has null token
    }

    [Fact]
    public async Task RunAsyncThrowsWhenMessagesProvidedWithContinuationTokenAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { ContinuationToken = new() };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(inputMessages, options: runOptions));

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenMessagesProvidedWithContinuationTokenAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { ContinuationToken = new() };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(inputMessages, options: runOptions))
            {
                // Should not reach here
            }
        });

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAsyncSkipsThreadMessagePopulationWithContinuationTokenAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];

        // Create a mock message store that would normally provide messages
        var mockMessageStore = new Mock<ChatMessageStore>();
        mockMessageStore
            .Setup(ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync([new(ChatRole.User, "Message from message store")]);

        // Create a mock AI context provider that would normally provide context
        var mockContextProvider = new Mock<AIContextProvider>();
        mockContextProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = [new(ChatRole.System, "Message from AI context")],
                Instructions = "context instructions"
            });

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "continued response")]));

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a thread with both message store and AI context provider
        ChatClientAgentThread thread = new()
        {
            MessageStore = mockMessageStore.Object,
            AIContextProvider = mockContextProvider.Object
        };

        AgentRunOptions runOptions = new() { ContinuationToken = new() };

        // Act
        await agent.RunAsync([], thread, options: runOptions);

        // Assert

        // With continuation token, thread message population should be skipped
        Assert.Empty(capturedMessages);

        // Verify that message store was never called due to continuation token
        mockMessageStore.Verify(
            ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()),
            Times.Never);

        // Verify that AI context provider was never called due to continuation token
        mockContextProvider.Verify(
            p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncSkipsThreadMessagePopulationWithContinuationTokenAsync()
    {
        // Arrange
        List<ChatMessage> capturedMessages = [];

        // Create a mock message store that would normally provide messages
        var mockMessageStore = new Mock<ChatMessageStore>();
        mockMessageStore
            .Setup(ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync([new(ChatRole.User, "Message from message store")]);

        // Create a mock AI context provider that would normally provide context
        var mockContextProvider = new Mock<AIContextProvider>();
        mockContextProvider
            .Setup(p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AIContext
            {
                Messages = [new(ChatRole.System, "Message from AI context")],
                Instructions = "context instructions"
            });

        Mock<IChatClient> mockChatClient = new();
        mockChatClient
            .Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .Returns(ToAsyncEnumerableAsync([new ChatResponseUpdate(role: ChatRole.Assistant, content: "continued response")]));

        ChatClientAgent agent = new(mockChatClient.Object);

        // Create a thread with both message store and AI context provider
        ChatClientAgentThread thread = new()
        {
            MessageStore = mockMessageStore.Object,
            AIContextProvider = mockContextProvider.Object
        };

        AgentRunOptions runOptions = new() { ContinuationToken = new() };

        // Act
        await agent.RunStreamingAsync([], thread, options: runOptions).ToListAsync();

        // Assert

        // With continuation token, thread message population should be skipped
        Assert.Empty(capturedMessages);

        // Verify that message store was never called due to continuation token
        mockMessageStore.Verify(
            ms => ms.GetMessagesAsync(It.IsAny<CancellationToken>()),
            Times.Never);

        // Verify that AI context provider was never called due to continuation token
        mockContextProvider.Verify(
            p => p.InvokingAsync(It.IsAny<AIContextProvider.InvokingContext>(), It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunAsyncThrowsWhenNoThreadProvideForBackgroundResponsesAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { AllowBackgroundResponses = true };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(inputMessages, options: runOptions));

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task RunStreamingAsyncThrowsWhenNoThreadProvideForBackgroundResponsesAsync()
    {
        // Arrange
        Mock<IChatClient> mockChatClient = new();

        ChatClientAgent agent = new(mockChatClient.Object);

        AgentRunOptions runOptions = new() { AllowBackgroundResponses = true };

        IEnumerable<ChatMessage> inputMessages = [new ChatMessage(ChatRole.User, "test message")];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(inputMessages, options: runOptions))
            {
                // Should not reach here
            }
        });

        // Verify that the IChatClient was never called due to early validation
        mockChatClient.Verify(
            c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
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

    private sealed class Animal
    {
        public int Id { get; set; }
        public string? FullName { get; set; }
        public Species Species { get; set; }
    }

    private enum Species
    {
        Bear,
        Tiger,
        Walrus,
    }

    [JsonSourceGenerationOptions(UseStringEnumConverter = true, PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(Animal))]
    private sealed partial class JsonContext2 : JsonSerializerContext;
}
