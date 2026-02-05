// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="StructuredOutputAgent"/> class.
/// </summary>
public sealed class StructuredOutputAgentTests
{
    private readonly Mock<IChatClient> _chatClientMock;
    private readonly TestAIAgent _innerAgent;
    private readonly List<ChatMessage> _testMessages;
    private readonly AgentSession _testSession;
    private readonly AgentResponse _innerAgentResponse;
    private readonly ChatResponse _chatClientResponse;

    public StructuredOutputAgentTests()
    {
        this._chatClientMock = new Mock<IChatClient>();
        this._innerAgent = new TestAIAgent();
        this._testMessages = [new ChatMessage(ChatRole.User, "Test message")];
        this._testSession = new Mock<AgentSession>().Object;
        this._innerAgentResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Inner agent response text")]);
        this._chatClientResponse = new ChatResponse([new ChatMessage(ChatRole.Assistant, "{\"result\": \"structured output\"}")]);

        this._innerAgent.RunAsyncFunc = (_, _, _, _) => Task.FromResult(this._innerAgentResponse);

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._chatClientResponse);
    }

    #region Constructor Tests

    [Fact]
    public void Constructor_WithNullInnerAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgent", () =>
            new StructuredOutputAgent(null!, this._chatClientMock.Object));
    }

    [Fact]
    public void Constructor_WithNullChatClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("chatClient", () =>
            new StructuredOutputAgent(this._innerAgent, null!));
    }

    [Fact]
    public void Constructor_WithValidParameters_Succeeds()
    {
        // Act
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);

        // Assert
        Assert.NotNull(agent);
    }

    [Fact]
    public void Constructor_WithValidParametersAndOptions_Succeeds()
    {
        // Arrange
        StructuredOutputAgentOptions options = new()
        {
            ChatClientSystemMessage = "Custom system message",
            ChatOptions = new ChatOptions()
        };

        // Act
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, options);

        // Assert
        Assert.NotNull(agent);
    }

    #endregion

    #region RunAsync Tests - Response Format Validation

    [Fact]
    public async Task RunAsync_WithNoResponseFormat_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testSession, options: null));

        Assert.Contains("ChatResponseFormatJson", exception.Message);
        Assert.Contains("none was specified", exception.Message);
    }

    [Fact]
    public async Task RunAsync_WithTextResponseFormat_ThrowsNotSupportedExceptionAsync()
    {
        // Arrange
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = ChatResponseFormat.Text };

        // Act & Assert
        NotSupportedException exception = await Assert.ThrowsAsync<NotSupportedException>(
            () => agent.RunAsync(this._testMessages, this._testSession, runOptions));

        Assert.Contains("ChatResponseFormatJson", exception.Message);
    }

    [Fact]
    public async Task RunAsync_WithJsonResponseFormatInRunOptions_SucceedsAsync()
    {
        // Arrange
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act
        AgentResponse result = await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<StructuredOutputAgentResponse>(result);
    }

    [Fact]
    public async Task RunAsync_WithJsonResponseFormatInAgentOptions_SucceedsAsync()
    {
        // Arrange
        StructuredOutputAgentOptions agentOptions = new()
        {
            ChatOptions = new ChatOptions { ResponseFormat = CreateJsonResponseFormat() }
        };
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, agentOptions);

        // Act
        AgentResponse result = await agent.RunAsync(this._testMessages, this._testSession, options: null);

        // Assert
        Assert.NotNull(result);
        Assert.IsType<StructuredOutputAgentResponse>(result);
    }

    [Fact]
    public async Task RunAsync_RunOptionsResponseFormatTakesPrecedenceOverAgentOptions_UsesRunOptionsFormatAsync()
    {
        // Arrange
        ChatResponseFormatJson agentOptionsFormat = CreateJsonResponseFormat();
        ChatResponseFormatJson runOptionsFormat = CreateJsonResponseFormat();

        StructuredOutputAgentOptions agentOptions = new()
        {
            ChatOptions = new ChatOptions { ResponseFormat = agentOptionsFormat }
        };
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, agentOptions);
        AgentRunOptions runOptions = new() { ResponseFormat = runOptionsFormat };

        ChatOptions? capturedChatOptions = null;
        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) =>
                capturedChatOptions = options)
            .ReturnsAsync(this._chatClientResponse);

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Same(runOptionsFormat, capturedChatOptions.ResponseFormat);
    }

    #endregion

    #region RunAsync Tests - Inner Agent Invocation

    [Fact]
    public async Task RunAsync_InvokesInnerAgentWithCorrectParametersAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        AgentSession? capturedSession = null;
        AgentRunOptions? capturedOptions = null;
        CancellationToken capturedCancellationToken = default;
        using CancellationTokenSource cts = new();
        CancellationToken expectedToken = cts.Token;

        this._innerAgent.RunAsyncFunc = (messages, session, options, cancellationToken) =>
        {
            capturedMessages = messages;
            capturedSession = session;
            capturedOptions = options;
            capturedCancellationToken = cancellationToken;
            return Task.FromResult(this._innerAgentResponse);
        };

        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, runOptions, expectedToken);

        // Assert
        Assert.Same(this._testMessages, capturedMessages);
        Assert.Same(this._testSession, capturedSession);
        Assert.Same(runOptions, capturedOptions);
        Assert.Equal(expectedToken, capturedCancellationToken);
    }

    #endregion

    #region RunAsync Tests - Chat Client Invocation

    [Fact]
    public async Task RunAsync_WithoutSystemMessage_SendsOnlyUserMessageToChatClientAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((messages, _, _) =>
                capturedMessages = messages)
            .ReturnsAsync(this._chatClientResponse);

        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.NotNull(capturedMessages);
        List<ChatMessage> messageList = [.. capturedMessages];
        Assert.Single(messageList);
        Assert.Equal(ChatRole.User, messageList[0].Role);
        Assert.Equal(this._innerAgentResponse.Text, messageList[0].Text);
    }

    [Fact]
    public async Task RunAsync_WithSystemMessage_SendsSystemAndUserMessagesToChatClientAsync()
    {
        // Arrange
        const string CustomSystemMessage = "Custom conversion instruction";
        IEnumerable<ChatMessage>? capturedMessages = null;

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((messages, _, _) =>
                capturedMessages = messages)
            .ReturnsAsync(this._chatClientResponse);

        StructuredOutputAgentOptions agentOptions = new()
        {
            ChatClientSystemMessage = CustomSystemMessage,
            ChatOptions = new ChatOptions { ResponseFormat = CreateJsonResponseFormat() }
        };
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, agentOptions);

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, options: null);

        // Assert
        Assert.NotNull(capturedMessages);
        List<ChatMessage> messageList = [.. capturedMessages];
        Assert.Equal(2, messageList.Count);
        Assert.Equal(ChatRole.System, messageList[0].Role);
        Assert.Equal(CustomSystemMessage, messageList[0].Text);
        Assert.Equal(ChatRole.User, messageList[1].Role);
        Assert.Equal(this._innerAgentResponse.Text, messageList[1].Text);
    }

    [Fact]
    public async Task RunAsync_PassesCancellationTokenToChatClientAsync()
    {
        // Arrange
        CancellationToken capturedToken = default;
        using CancellationTokenSource cts = new();
        CancellationToken expectedToken = cts.Token;

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, _, cancellationToken) =>
                capturedToken = cancellationToken)
            .ReturnsAsync(this._chatClientResponse);

        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, runOptions, expectedToken);

        // Assert
        Assert.Equal(expectedToken, capturedToken);
    }

    [Fact]
    public async Task RunAsync_ClonesChatOptionsFromAgentOptionsAsync()
    {
        // Arrange
        const string ModelId = "test-model";
        ChatOptions? capturedChatOptions = null;

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) =>
                capturedChatOptions = options)
            .ReturnsAsync(this._chatClientResponse);

        ChatOptions originalChatOptions = new()
        {
            ResponseFormat = CreateJsonResponseFormat(),
            ModelId = ModelId
        };
        StructuredOutputAgentOptions agentOptions = new()
        {
            ChatOptions = originalChatOptions
        };
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, agentOptions);

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, options: null);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotSame(originalChatOptions, capturedChatOptions);
        Assert.Equal(ModelId, capturedChatOptions.ModelId);
    }

    #endregion

    #region RunAsync Tests - Response

    [Fact]
    public async Task RunAsync_ReturnsStructuredOutputAgentResponseAsync()
    {
        // Arrange
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act
        AgentResponse result = await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.IsType<StructuredOutputAgentResponse>(result);
    }

    [Fact]
    public async Task RunAsync_StructuredOutputResponseContainsOriginalResponseAsync()
    {
        // Arrange
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act
        AgentResponse result = await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        StructuredOutputAgentResponse structuredResponse = Assert.IsType<StructuredOutputAgentResponse>(result);
        Assert.Same(this._innerAgentResponse, structuredResponse.OriginalResponse);
    }

    [Fact]
    public async Task RunAsync_StructuredOutputResponseContainsChatClientResponseDataAsync()
    {
        // Arrange
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act
        AgentResponse result = await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.Equal("{\"result\": \"structured output\"}", result.Text);
    }

    #endregion

    #region Error Handling Tests

    [Fact]
    public async Task RunAsync_InnerAgentThrowsException_PropagatesExceptionAsync()
    {
        // Arrange
        InvalidOperationException expectedException = new("Inner agent error");
        this._innerAgent.RunAsyncFunc = (_, _, _, _) => throw expectedException;

        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act & Assert
        InvalidOperationException actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testSession, runOptions));

        Assert.Same(expectedException, actualException);
    }

    [Fact]
    public async Task RunAsync_ChatClientThrowsException_PropagatesExceptionAsync()
    {
        // Arrange
        InvalidOperationException expectedException = new("Chat client error");

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(expectedException);

        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act & Assert
        InvalidOperationException actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testSession, runOptions));

        Assert.Same(expectedException, actualException);
    }

    [Fact]
    public async Task RunAsync_CancellationRequested_ThrowsOperationCanceledExceptionAsync()
    {
        // Arrange
        using CancellationTokenSource cts = new();
        cts.Cancel();

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException());

        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object);
        AgentRunOptions runOptions = new() { ResponseFormat = CreateJsonResponseFormat() };

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => agent.RunAsync(this._testMessages, this._testSession, runOptions, cts.Token));
    }

    #endregion

    #region ChatOptions Creation Tests

    [Fact]
    public async Task RunAsync_CreatesNewChatOptionsWhenAgentOptionsIsNullAsync()
    {
        // Arrange
        ChatOptions? capturedChatOptions = null;
        ChatResponseFormatJson expectedFormat = CreateJsonResponseFormat();

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) =>
                capturedChatOptions = options)
            .ReturnsAsync(this._chatClientResponse);

        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, options: null);
        AgentRunOptions runOptions = new() { ResponseFormat = expectedFormat };

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Same(expectedFormat, capturedChatOptions.ResponseFormat);
    }

    [Fact]
    public async Task RunAsync_CreatesNewChatOptionsWhenAgentOptionsChatOptionsIsNullAsync()
    {
        // Arrange
        ChatOptions? capturedChatOptions = null;
        ChatResponseFormatJson expectedFormat = CreateJsonResponseFormat();

        this._chatClientMock
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, options, _) =>
                capturedChatOptions = options)
            .ReturnsAsync(this._chatClientResponse);

        StructuredOutputAgentOptions agentOptions = new() { ChatOptions = null };
        StructuredOutputAgent agent = new(this._innerAgent, this._chatClientMock.Object, agentOptions);
        AgentRunOptions runOptions = new() { ResponseFormat = expectedFormat };

        // Act
        await agent.RunAsync(this._testMessages, this._testSession, runOptions);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Same(expectedFormat, capturedChatOptions.ResponseFormat);
    }

    #endregion

    private static ChatResponseFormatJson CreateJsonResponseFormat()
    {
        // Create a simple JSON schema for testing
        const string SchemaJson = """{"type":"object","properties":{"result":{"type":"string"}},"required":["result"]}""";
        using JsonDocument doc = JsonDocument.Parse(SchemaJson);

        return ChatResponseFormat.ForJsonSchema(
            doc.RootElement.Clone(),
            schemaName: "TestSchema",
            schemaDescription: "Test schema for unit tests");
    }
}
