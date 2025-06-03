// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="Agent"/> class.
/// </summary>
public class AgentTests
{
    private readonly Mock<Agent> _agentMock;
    private readonly Mock<AgentThread> _agentThreadMock;
    private readonly ChatResponse _invokeResponse = new();
    private readonly List<ChatResponseUpdate> _invokeStreamingResponses = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentTests"/> class.
    /// </summary>
    public AgentTests()
    {
        this._agentThreadMock = new Mock<AgentThread>(MockBehavior.Strict);

        this._invokeResponse = new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hi"));
        this._invokeStreamingResponses.Add(new ChatResponseUpdate(ChatRole.Assistant, "Hi"));

        this._agentMock = new Mock<Agent>() { CallBase = true };
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
            .Returns(this._invokeStreamingResponses.ToAsyncEnumerable());
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
        var cancellationToken = new CancellationToken();

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
        var message = "Hello, Agent!";
        var options = new AgentRunOptions();
        var cancellationToken = new CancellationToken();

        // Act
        var response = await this._agentMock.Object.RunAsync(message, this._agentThreadMock.Object, options, cancellationToken);
        Assert.Equal(this._invokeResponse, response);

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 1 && messages.First().Text == message),
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
        var cancellationToken = new CancellationToken();

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
        var cancellationToken = new CancellationToken();

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
        var message = "Hello, Agent!";
        var options = new AgentRunOptions();
        var cancellationToken = new CancellationToken();

        // Act
        await foreach (var response in this._agentMock.Object.RunStreamingAsync(message, this._agentThreadMock.Object, options, cancellationToken))
        {
            // Assert
            Assert.Contains(response, this._invokeStreamingResponses);
        }

        // Verify that the mocked method was called with the expected parameters
        this._agentMock.Verify(
            x => x.RunStreamingAsync(
                It.Is<IReadOnlyCollection<ChatMessage>>(messages => messages.Count == 1 && messages.First().Text == message),
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
        var cancellationToken = new CancellationToken();

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
}
