// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentTests
{
    /// <summary>
    /// Verify the invocation and response of <see cref="ChatClientAgent"/>.
    /// </summary>
    [Fact]
    public void VerifyChatCompletionAgentDefinition()
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
        Assert.Same(chatClient, agent.ChatClient);
        Assert.Equal(ChatRole.System, agent.InstructionsRole);
    }

    /// <summary>
    /// Verify the invocation and response of <see cref="ChatClientAgent"/>.
    /// </summary>
    [Fact]
    public async Task VerifyChatCompletionAgentInvocationAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "what?")]));

        ChatClientAgent agent =
            new(mockService.Object, new()
            {
                Instructions = "test instructions"
            });

        // Act
        ChatResponse result = await agent.RunAsync([]);

        // Assert
        Assert.Single(result.Messages);

        mockService.Verify(
            x =>
                x.GetResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(),
                    It.IsAny<ChatOptions>(),
                    It.IsAny<CancellationToken>()),
            Times.Once);
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
        ChatResponse result = await agent.RunAsync([new(ChatRole.User, "Where are you?")]);

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
    /// Verify the streaming invocation and response of <see cref="ChatClientAgent"/>.
    /// </summary>
    [Fact(Skip = "Not implemented yet")]
    public async Task VerifyChatClientAgentStreamingAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
        [
            new ChatResponseUpdate(role: ChatRole.Assistant, content: "wh"),
            new ChatResponseUpdate(role: null, content: "at?"),
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
        ChatResponseUpdate[] result = await agent.RunStreamingAsync([]).ToArrayAsync();

        // Assert
        Assert.Equal(2, result.Length);

        mockService.Verify(
            x =>
                x.GetStreamingResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(),
                    It.IsAny<ChatOptions>(),
                    It.IsAny<CancellationToken>()),
            Times.Once);
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
        var runOptions = new ChatClientAgentRunOptions { ChatOptions = chatOptions };

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: runOptions);

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
    /// Verify that RunAsync includes additional instructions when provided in options.
    /// </summary>
    [Fact]
    public async Task RunAsyncIncludesAdditionalInstructionsWhenProvidedInOptionsAsync()
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
        var runOptions = new AgentRunOptions { AdditionalInstructions = "additional instructions" };

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: runOptions);

        // Assert
        Assert.Contains(capturedMessages, m => m.Text == "base instructions" && m.Role == ChatRole.System);
        Assert.Contains(capturedMessages, m => m.Text == "additional instructions" && m.Role == ChatRole.System);
        Assert.Contains(capturedMessages, m => m.Text == "test" && m.Role == ChatRole.User);
    }

    /// <summary>
    /// Verify that RunAsync calls OnIntermediateMessage callback for each response message.
    /// </summary>
    [Fact]
    public async Task RunAsyncCallsOnIntermediateMessageForEachResponseMessageAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        var responseMessages = new[]
        {
            new ChatMessage(ChatRole.Assistant, "first response"),
            new ChatMessage(ChatRole.Assistant, "second response")
        };
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse(responseMessages));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions", Name = "TestAgent" });

        var callbackMessages = new List<ChatMessage>();
        var runOptions = new AgentRunOptions
        {
            OnIntermediateMessage = msg =>
            {
                callbackMessages.Add(msg);
                return Task.CompletedTask;
            }
        };

        // Act
        await agent.RunAsync([new(ChatRole.User, "test")], options: runOptions);

        // Assert
        Assert.Equal(2, callbackMessages.Count);
        Assert.Equal("first response", callbackMessages[0].Text);
        Assert.Equal("second response", callbackMessages[1].Text);
        Assert.All(callbackMessages, msg => Assert.Equal("TestAgent", msg.AuthorName));
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

        // Create a thread using the agent's CreateThreadAsync method
        var thread = await agent.CreateThreadAsync();

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
}
