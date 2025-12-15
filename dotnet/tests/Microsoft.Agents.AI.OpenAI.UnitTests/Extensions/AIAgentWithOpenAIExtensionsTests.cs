// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;
using ChatRole = Microsoft.Extensions.AI.ChatRole;
using OpenAIChatMessage = OpenAI.Chat.ChatMessage;
using TextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.OpenAI.UnitTests.Extensions;

/// <summary>
/// Unit tests for the <see cref="AIAgentWithOpenAIExtensions"/> class.
/// </summary>
public sealed class AIAgentWithOpenAIExtensionsTests
{
    /// <summary>
    /// Verify that RunAsync throws ArgumentNullException when agent is null.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithNullAgent_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        AIAgent? agent = null;
        var messages = new List<OpenAIChatMessage>
        {
            OpenAIChatMessage.CreateUserMessage("Test message")
        };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(
            () => agent!.RunAsync(messages));

        Assert.Equal("agent", exception.ParamName);
    }

    /// <summary>
    /// Verify that RunAsync throws ArgumentNullException when messages is null.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        IEnumerable<OpenAIChatMessage>? messages = null;

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentNullException>(
            () => mockAgent.Object.RunAsync(messages!));

        Assert.Equal("messages", exception.ParamName);
    }

    /// <summary>
    /// Verify that the RunAsync extension method calls the underlying agent's RunAsync with converted messages and parameters.
    /// </summary>
    [Fact]
    public async Task RunAsync_CallsUnderlyingAgentAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var mockThread = new Mock<AgentThread>();
        var options = new AgentRunOptions();
        var cancellationToken = new CancellationToken(false);
        const string TestMessageText = "Hello, assistant!";
        const string ResponseText = "This is the assistant's response.";
        var openAiMessages = new List<OpenAIChatMessage>
        {
            OpenAIChatMessage.CreateUserMessage(TestMessageText)
        };

        var responseMessage = new ChatMessage(ChatRole.Assistant, [new TextContent(ResponseText)]);

        mockAgent
            .Setup(a => a.RunAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<AgentThread?>(), It.IsAny<AgentRunOptions?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new AgentRunResponse([responseMessage]));

        // Act
        var result = await mockAgent.Object.RunAsync(openAiMessages, mockThread.Object, options, cancellationToken);

        // Assert
        mockAgent.Verify(
            a => a.RunAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs =>
                    msgs.ToList().Count == 1 &&
                    msgs.ToList()[0].Text == TestMessageText),
                mockThread.Object,
                options,
                cancellationToken),
            Times.Once);

        Assert.NotNull(result);
        Assert.NotEmpty(result.Content);
        Assert.Equal(ResponseText, result.Content.Last().Text);
    }

    /// <summary>
    /// Verify that RunStreamingAsync throws ArgumentNullException when agent is null.
    /// </summary>
    [Fact]
    public void RunStreamingAsync_WithNullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgent? agent = null;
        var messages = new List<OpenAIChatMessage>
        {
            OpenAIChatMessage.CreateUserMessage("Test message")
        };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(
            "agent",
            () => agent!.RunStreamingAsync(messages));
    }

    /// <summary>
    /// Verify that RunStreamingAsync throws ArgumentNullException when messages is null.
    /// </summary>
    [Fact]
    public void RunStreamingAsync_WithNullMessages_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        IEnumerable<OpenAIChatMessage>? messages = null;

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(
            () => mockAgent.Object.RunStreamingAsync(messages!));

        Assert.Equal("messages", exception.ParamName);
    }

    /// <summary>
    /// Verify that the RunStreamingAsync extension method calls the underlying agent's RunStreamingAsync with converted messages and parameters.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_CallsUnderlyingAgentAsync()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var mockThread = new Mock<AgentThread>();
        var options = new AgentRunOptions();
        var cancellationToken = new CancellationToken(false);
        const string TestMessageText = "Hello, assistant!";
        const string ResponseText1 = "This is ";
        const string ResponseText2 = "the assistant's response.";
        var openAiMessages = new List<OpenAIChatMessage>
        {
            OpenAIChatMessage.CreateUserMessage(TestMessageText)
        };

        var responseUpdates = new List<AgentRunResponseUpdate>
        {
            new(ChatRole.Assistant, ResponseText1),
            new(ChatRole.Assistant, ResponseText2)
        };

        mockAgent
            .Setup(a => a.RunStreamingAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<AgentThread?>(), It.IsAny<AgentRunOptions?>(), It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(responseUpdates));

        // Act
        var result = mockAgent.Object.RunStreamingAsync(openAiMessages, mockThread.Object, options, cancellationToken);
        var updateCount = 0;
        await foreach (var update in result)
        {
            updateCount++;
        }

        // Assert
        mockAgent.Verify(
            a => a.RunStreamingAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs =>
                    msgs.ToList().Count == 1 &&
                    msgs.ToList()[0].Text == TestMessageText),
                mockThread.Object,
                options,
                cancellationToken),
            Times.Once);

        Assert.True(updateCount > 0, "Expected at least one streaming update");
    }

    /// <summary>
    /// Helper method to convert a list of AgentRunResponseUpdate to an async enumerable.
    /// </summary>
    private static async IAsyncEnumerable<AgentRunResponseUpdate> ToAsyncEnumerableAsync(IEnumerable<AgentRunResponseUpdate> updates)
    {
        foreach (var update in updates)
        {
            yield return await Task.FromResult(update);
        }
    }
}
