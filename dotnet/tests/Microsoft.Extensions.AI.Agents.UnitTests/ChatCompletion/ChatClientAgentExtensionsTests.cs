// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentExtensionsTests
{
    #region RunAsync with IReadOnlyCollection<ChatMessage> Tests

    /// <summary>
    /// Verify that RunAsync extension method with messages works with valid parameters.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesWorksWithValidParametersAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test message") };

        // Act & Assert - Should not throw
        var result = await ChatClientAgentExtensions.RunAsync(agent, messages);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verify that RunAsync extension method with messages throws ArgumentNullException when agent is null.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesThrowsArgumentNullExceptionWhenAgentIsNullAsync()
    {
        // Arrange
        ChatClientAgent agent = null!;
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            ChatClientAgentExtensions.RunAsync(agent, messages));
        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunAsync extension method with messages throws ArgumentNullException when messages is null.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesThrowsArgumentNullExceptionWhenMessagesIsNullAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            ChatClientAgentExtensions.RunAsync(agent, (IReadOnlyCollection<ChatMessage>)null!));
        Assert.Equal("messages", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunAsync extension method with messages works with ChatOptions parameter.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesWorksWithChatOptionsAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act - Call extension method (should not throw)
        var result = await ChatClientAgentExtensions.RunAsync(agent, messages, chatOptions: chatOptions);

        // Assert - Extension method completed successfully
        Assert.NotNull(result);
        Assert.Single(result.Messages);
    }

    /// <summary>
    /// Verify that RunAsync extension method with messages passes Instructions correctly.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesPassesInstructionsCorrectlyAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        List<ChatOptions> capturedChatOptions = [];
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
            {
                capturedChatOptions.Add(opts);
                capturedMessages.AddRange(msgs);
            })
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "base instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };
        var runOptions = new AgentRunOptions();

        // Act
        await ChatClientAgentExtensions.RunAsync(agent, messages, agentRunOptions: runOptions);

        // Assert
        Assert.Contains(capturedMessages, m => m.Text == "base instructions" && m.Role == ChatRole.System);
        Assert.Contains(capturedMessages, m => m.Text == "test" && m.Role == ChatRole.User);
        Assert.All(capturedChatOptions, Assert.Null);
    }

    /// <summary>
    /// Verify that RunAsync extension method with messages works with thread parameter.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesWorksWithThreadParameterAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };
        var thread = agent.GetNewThread();

        // Act
        var result = await ChatClientAgentExtensions.RunAsync(agent, messages, thread: thread);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync extension method with messages respects cancellation token.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithMessagesRespectsCancellationTokenAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ThrowsAsync(new OperationCanceledException());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() => ChatClientAgentExtensions.RunAsync(agent, messages, cancellationToken: cts.Token));
    }

    #endregion

    #region RunAsync with string prompt Tests

    /// <summary>
    /// Verify that RunAsync extension method with prompt calls the underlying agent method correctly.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptCallsUnderlyingAgentMethodAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act
        var result = await ChatClientAgentExtensions.RunAsync(agent, TestPrompt);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        Assert.Equal("response", result.Messages[0].Text);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt throws ArgumentNullException when agent is null.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptThrowsArgumentNullExceptionWhenAgentIsNullAsync()
    {
        // Arrange
        ChatClientAgent agent = null!;
        const string TestPrompt = "test prompt";

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            ChatClientAgentExtensions.RunAsync(agent, TestPrompt));
        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt throws ArgumentNullException when prompt is null.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptThrowsArgumentNullExceptionWhenPromptIsNullAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(() =>
            ChatClientAgentExtensions.RunAsync(agent, (string)null!));
        Assert.Equal("prompt", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt throws ArgumentException when prompt is whitespace.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptThrowsArgumentExceptionWhenPromptIsWhitespaceAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            ChatClientAgentExtensions.RunAsync(agent, "   "));
        Assert.Equal("prompt", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt converts prompt to ChatMessage correctly.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptConvertsPromptToChatMessageCorrectlyAsync()
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
        const string TestPrompt = "test prompt";

        // Act
        await ChatClientAgentExtensions.RunAsync(agent, TestPrompt);

        // Assert
        Assert.Contains(capturedMessages, m => m.Text == "test prompt" && m.Role == ChatRole.User);
        Assert.Contains(capturedMessages, m => m.Text == "test instructions" && m.Role == ChatRole.System);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt passes ChatOptions correctly.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptPassesChatOptionsCorrectlyAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 200 };
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 200),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act
        await ChatClientAgentExtensions.RunAsync(agent, TestPrompt, chatOptions: chatOptions);

        // Assert
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 200),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt passes AgentRunOptions correctly.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptPassesAgentRunOptionsCorrectlyAsync()
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
        const string TestPrompt = "test prompt";
        var runOptions = new AgentRunOptions();

        // Act
        await ChatClientAgentExtensions.RunAsync(agent, TestPrompt, agentRunOptions: runOptions);

        // Assert
        Assert.Contains(capturedMessages, m => m.Text == "base instructions" && m.Role == ChatRole.System);
        Assert.Contains(capturedMessages, m => m.Text == "test prompt" && m.Role == ChatRole.User);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt works with thread parameter.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptWorksWithThreadParameterAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";
        var thread = agent.GetNewThread();

        // Act
        var result = await ChatClientAgentExtensions.RunAsync(agent, TestPrompt, thread: thread);

        // Assert
        Assert.NotNull(result);
        Assert.Single(result.Messages);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunAsync extension method with prompt respects cancellation token.
    /// </summary>
    [Fact]
    public async Task RunAsyncWithPromptRespectsCancellationTokenAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ThrowsAsync(new OperationCanceledException());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() => agent.RunAsync(TestPrompt, cancellationToken: cts.Token));
    }

    #endregion

    #region RunStreamingAsync with IReadOnlyCollection<ChatMessage> Tests

    /// <summary>
    /// Verify that RunStreamingAsync extension method with messages calls the underlying agent method correctly.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithMessagesCallsUnderlyingAgentMethodAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
            [
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "Hello"),
                new ChatResponseUpdate(role: ChatRole.Assistant, content: " World"),
            ];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test message") };

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, messages))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.Equal("Hello", updates[0].Text);
        Assert.Equal(" World", updates[1].Text);
        mockService.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with messages throws ArgumentNullException when agent is null.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithMessagesThrowsArgumentNullExceptionWhenAgentIsNullAsync()
    {
        // Arrange
        ChatClientAgent agent = null!;
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, messages))
            {
                // Should not reach here
            }
        });
        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with messages throws ArgumentNullException when messages is null.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithMessagesThrowsArgumentNullExceptionWhenMessagesIsNullAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, (IReadOnlyCollection<ChatMessage>)null!))
            {
                // Should not reach here
            }
        });
        Assert.Equal("messages", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with messages passes ChatOptions correctly.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithMessagesPassesChatOptionsCorrectlyAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        ChatResponseUpdate[] returnUpdates = [new ChatResponseUpdate(role: ChatRole.Assistant, content: "response")];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 100),
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, messages, chatOptions: chatOptions))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        mockService.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 100),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with messages works with thread parameter.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithMessagesWorksWithThreadParameterAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates = [new ChatResponseUpdate(role: ChatRole.Assistant, content: "response")];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };
        var thread = agent.GetNewThread();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, messages, thread: thread))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        mockService.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with messages respects cancellation token.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithMessagesRespectsCancellationTokenAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Throws(new OperationCanceledException());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(async () =>
        {
            await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, messages, cancellationToken: cts.Token))
            {
                // Should not reach here
            }
        });
    }

    #endregion

    #region RunStreamingAsync with string prompt Tests

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt calls the underlying agent method correctly.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptCallsUnderlyingAgentMethodAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates =
            [
                new ChatResponseUpdate(role: ChatRole.Assistant, content: "Hello"),
                new ChatResponseUpdate(role: ChatRole.Assistant, content: " World"),
            ];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, TestPrompt))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.Equal("Hello", updates[0].Text);
        Assert.Equal(" World", updates[1].Text);
        mockService.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt throws ArgumentNullException when agent is null.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptThrowsArgumentNullExceptionWhenAgentIsNullAsync()
    {
        // Arrange
        ChatClientAgent agent = null!;
        const string TestPrompt = "test prompt";

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, TestPrompt))
            {
                // Should not reach here
            }
        });
        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt throws ArgumentNullException when prompt is null.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptThrowsArgumentNullExceptionWhenPromptIsNullAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, (string)null!))
            {
                // Should not reach here
            }
        });
        Assert.Equal("prompt", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt throws ArgumentException when prompt is whitespace.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptThrowsArgumentExceptionWhenPromptIsWhitespaceAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatClientAgent agent = new(chatClient, new() { Instructions = "test instructions" });

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(async () =>
        {
            await foreach (var update in ChatClientAgentExtensions.RunStreamingAsync(agent, "   "))
            {
                // Should not reach here
            }
        });
        Assert.Equal("prompt", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt converts prompt to ChatMessage correctly.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptConvertsPromptToChatMessageCorrectlyAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates = [new ChatResponseUpdate(role: ChatRole.Assistant, content: "response")];

        Mock<IChatClient> mockService = new();
        List<ChatMessage> capturedMessages = [];
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedMessages.AddRange(msgs))
            .Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(TestPrompt))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        Assert.Contains(capturedMessages, m => m.Text == "test prompt" && m.Role == ChatRole.User);
        Assert.Contains(capturedMessages, m => m.Text == "test instructions" && m.Role == ChatRole.System);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt passes ChatOptions correctly.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptPassesChatOptionsCorrectlyAsync()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 200 };
        ChatResponseUpdate[] returnUpdates = [new ChatResponseUpdate(role: ChatRole.Assistant, content: "response")];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 200),
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(TestPrompt, chatOptions: chatOptions))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        mockService.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.Is<ChatOptions>(opts => opts.MaxOutputTokens == 200),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt works with thread parameter.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptWorksWithThreadParameterAsync()
    {
        // Arrange
        ChatResponseUpdate[] returnUpdates = [new ChatResponseUpdate(role: ChatRole.Assistant, content: "response")];

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Returns(returnUpdates.ToAsyncEnumerable());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";
        var thread = agent.GetNewThread();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(TestPrompt, thread: thread))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);
        mockService.Verify(
            x => x.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verify that RunStreamingAsync extension method with prompt respects cancellation token.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWithPromptRespectsCancellationTokenAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).Throws(new OperationCanceledException());

        ChatClientAgent agent = new(mockService.Object, new() { Instructions = "test instructions" });
        const string TestPrompt = "test prompt";

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(async () =>
        {
            await foreach (var update in agent.RunStreamingAsync(TestPrompt, cancellationToken: cts.Token))
            {
                // Should not reach here
            }
        });
    }

    #endregion
}
