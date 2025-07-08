// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentTests
{
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
                new()
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
        Assert.Equal("AgentInvokingChatClient", agent.ChatClient.GetType().Name);
    }

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
            new(mockService.Object, new()
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
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], chatOptions: chatOptions);

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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
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
    public async Task RunAsyncIncludesBaseInstructionsAsync()
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "base instructions" });
        var runOptions = new AgentRunOptions();

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: runOptions);

        // Assert
        Assert.Contains(capturedMessages, m => m.Text == "base instructions" && m.Role == ChatRole.System);
        Assert.Contains(capturedMessages, m => m.Text == "test" && m.Role == ChatRole.User);
    }

    /// <summary>
    /// Verify that RunAsync sets AuthorName on all response messages.
    /// </summary>
    [Fact]
    public async Task RunAsyncSetsAuthorNameOnAllResponseMessagesAsync()
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions", Name = "TestAgent" });

        // Act
        var result = await agent.RunAsync([new(ChatRole.User, "test")]);

        // Assert
        Assert.All(result.Messages, msg => Assert.Equal("TestAgent", msg.AuthorName));
    }

    /// <summary>
    /// Verify that RunAsync works with existing thread and retrieves messages from IMessagesRetrievableThread.
    /// </summary>
    [Fact]
    public async Task RunAsyncRetrievesMessagesFromThreadWhenThreadImplementsIMessagesRetrievableThreadAsync()
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        // Create a thread using the agent's GetNewThread method
        var thread = agent.GetNewThread();

        // Act
        await agent.RunAsync([new(ChatRole.User, "new message")], thread: thread);

        // Assert
        // Should contain: instructions + new message
        Assert.Contains(capturedMessages, m => m.Text == "test instructions");
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = null });

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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        // Act
        await agent.RunAsync([]);

        // Assert
        // Should only contain the instructions
        Assert.Single(capturedMessages);
        Assert.Equal("test instructions", capturedMessages[0].Text);
        Assert.Equal(ChatRole.System, capturedMessages[0].Role);
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new("ConvId");

        // Act & Assert
        await agent.RunAsync([new(ChatRole.User, "test")], thread, chatOptions: chatOptions);
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new("ThreadId");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread, chatOptions: chatOptions));
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new("ConvId");

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], thread, chatOptions: chatOptions);

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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });

        ChatClientAgentThread thread = new("ConvId");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync([new(ChatRole.User, "test")], thread));
    }

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
        ChatClientAgent agent = new(chatClient, null);

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
        ChatClientAgent agent = new(chatClient, null);

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
        ChatClientAgent agent = new(chatClient, null);

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
        ChatClientAgent agent = new(chatClient, null);

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

    #region ChatOptions Property Tests

    /// <summary>
    /// Verify that ChatOptions property returns null when agent options are null.
    /// </summary>
    [Fact]
    public void ChatOptionsReturnsNullWhenAgentOptionsAreNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, null);

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

        ChatClientAgent agent = new(mockService.Object, new()
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
    }

    /// <summary>
    /// Verify that ChatOptions merging works when request has ChatOptions but agent doesn't.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesRequestOptionsWhenAgentHasNoneAsync()
    {
        // Arrange
        var requestChatOptions = new ChatOptions { MaxOutputTokens = 200, Temperature = 0.3f };
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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, chatOptions: requestChatOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(requestChatOptions, capturedChatOptions); // Should be the same instance since no merging needed
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.3f, capturedChatOptions.Temperature);
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
            AdditionalProperties = new AdditionalPropertiesDictionary() { ["key"] = "agent-value" }
        };
        var requestChatOptions = new ChatOptions
        {
            MaxOutputTokens = 200,
            Temperature = 0.3f,
            AdditionalProperties = new AdditionalPropertiesDictionary() { ["key"] = "request-value" }
            // TopP and ModelId not set, should use agent values
        };
        var expectedChatOptionsMerge = new ChatOptions
        {
            MaxOutputTokens = 200, // Request value takes priority
            Temperature = 0.3f, // Request value takes priority
            AdditionalProperties = new AdditionalPropertiesDictionary() { ["key"] = "request-value" }, // Request value takes priority
            TopP = 0.9f, // Agent value used when request doesn't specify
            ModelId = "agent-model" // Agent value used when request doesn't specify
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

        ChatClientAgent agent = new(mockService.Object, new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, chatOptions: requestChatOptions);

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

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
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

        ChatClientAgent agent = new(mockService.Object, new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, chatOptions: requestChatOptions);

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
            MaxOutputTokens = 100
            // No Tools specified
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

        ChatClientAgent agent = new(mockService.Object, new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, chatOptions: requestChatOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Single(capturedChatOptions.Tools);
        Assert.Contains(agentTool, capturedChatOptions.Tools); // Should contain the agent's tool
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

        ChatClientAgent agent = new(mockService.Object, new()
        {
            Instructions = "test instructions",
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, chatOptions: requestChatOptions);

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
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent =
            new(mockService.Object, new()
            {
                Instructions = "test instructions"
            });

        // Act
        var result = await agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "Hello")]).ToArrayAsync();

        // Assert
        Assert.Equal(2, result.Length);
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

    #endregion
}
