// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable S3717 // Track use of "NotImplementedException"

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;
using Moq.Protected;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgent"/> class.
/// </summary>
public class AIAgentTests
{
    private readonly Mock<AIAgent> _agentMock;
    private readonly Mock<AgentThread> _agentThreadMock;
    private readonly AgentRunResponse _invokeResponse;
    private readonly List<AgentRunResponseUpdate> _invokeStreamingResponses = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentTests"/> class.
    /// </summary>
    public AIAgentTests()
    {
        this._agentThreadMock = new Mock<AgentThread>(MockBehavior.Strict);

        this._invokeResponse = new AgentRunResponse(new ChatMessage(ChatRole.Assistant, "Hi"));
        this._invokeStreamingResponses.Add(new AgentRunResponseUpdate(ChatRole.Assistant, "Hi"));

        this._agentMock = new Mock<AIAgent> { CallBase = true };
        this._agentMock
            .Setup(x => x.RunAsync(
                It.IsAny<IReadOnlyCollection<ChatMessage>>(),
                this._agentThreadMock.Object,
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._invokeResponse);
        this._agentMock
            .Setup(x => x.RunStreamingAsync(
                It.IsAny<IReadOnlyCollection<ChatMessage>>(),
                this._agentThreadMock.Object,
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(this._invokeStreamingResponses));
    }

    /// <summary>
    /// Tests that invoking without a message calls the mocked invoke method with an empty array.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeWithoutMessageCallsMockedInvokeWithEmptyArrayAsync()
    {
        // Arrange
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        var response = await this._agentMock.Object.RunAsync(this._agentThreadMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 0),
                this._agentThreadMock.Object,
                options,
                cancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Tests that invoking with a string message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeWithStringMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        const string Message = "Hello, Agent!";
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        var response = await this._agentMock.Object.RunAsync(Message, this._agentThreadMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 1 && messages.First().Text == Message),
                this._agentThreadMock.Object,
                options,
                cancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Tests that invoking with a single message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeWithSingleMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.User, "Hello, Agent!");
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        var response = await this._agentMock.Object.RunAsync(message, this._agentThreadMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 1 && messages.First() == message),
                this._agentThreadMock.Object,
                options,
                cancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Tests that invoking streaming without a message calls the mocked invoke method with an empty array.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeStreamingWithoutMessageCallsMockedInvokeWithEmptyArrayAsync()
    {
        // Arrange
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(this._agentThreadMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunStreamingAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 0),
                this._agentThreadMock.Object,
                options,
                cancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Tests that invoking streaming with a string message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeStreamingWithStringMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        const string Message = "Hello, Agent!";
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(Message, this._agentThreadMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunStreamingAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 1 && messages.First().Text == Message),
                this._agentThreadMock.Object,
                options,
                cancellationToken),
            Times.Once);
    }

    /// <summary>
    /// Tests that invoking streaming with a single message calls the mocked invoke method with the message in the ICollection of messages.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    [Fact]
    public async Task InvokeStreamingWithSingleMessageCallsMockedInvokeWithMessageInCollectionAsync()
    {
        // Arrange
        var message = new ChatMessage(ChatRole.User, "Hello, Agent!");
        var options = new AgentRunOptions();
        var cancellationToken = default(CancellationToken);

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(message, this._agentThreadMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunStreamingAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 1 && messages.First() == message),
                this._agentThreadMock.Object,
                options,
                cancellationToken),
            Times.Once);
    }

    [Fact]
    public void ValidateAgentIDIsIdempotent()
    {
        var agent = new MockAgent();

        string id = agent.Id;
        Assert.NotNull(id);
        Assert.Equal(id, agent.Id);
    }

    [Fact]
    public async Task NotifyThreadOfNewMessagesNotifiesThreadAsync()
    {
        var cancellationToken = default(CancellationToken);

        var messages = new[] { new ChatMessage(ChatRole.User, "msg1"), new ChatMessage(ChatRole.User, "msg2") };

        var threadMock = new Mock<TestAgentThread> { CallBase = true };
        threadMock.SetupAllProperties();

        await MockAgent.NotifyThreadOfNewMessagesAsync(threadMock.Object, messages, cancellationToken);

        threadMock.Protected().Verify("MessagesReceivedAsync", Times.Once(), messages, cancellationToken);
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the agent itself when requesting the exact agent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactAgentType_ReturnsAgent()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(MockAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService returns the agent itself when requesting the base AIAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentType_ReturnsAgent()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(AIAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(string));

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
        var agent = new MockAgent();

        // Act
        var result = agent.GetService(typeof(MockAgent), "some-key");

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
        var agent = new MockAgent();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => agent.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService<MockAgent>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var agent = new MockAgent();

        // Act
        var result = agent.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    /// <summary>
    /// Typed mock thread.
    /// </summary>
    public abstract class TestAgentThread : AgentThread;

    private sealed class MockAgent : AIAgent
    {
        public static new Task NotifyThreadOfNewMessagesAsync(AgentThread thread, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken) =>
            AIAgent.NotifyThreadOfNewMessagesAsync(thread, messages, cancellationToken);

        public override AgentThread GetNewThread()
            => throw new NotImplementedException();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => throw new NotImplementedException();

        public override Task<AgentRunResponse> RunAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> values)
    {
        await Task.Yield();
        foreach (var update in values)
        {
            yield return update;
        }
    }
}
