// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class ChatClientAgentRunOptionsTests
{
    /// <summary>
    /// Verify that ChatClientAgentRunOptions constructor works with null chatOptions.
    /// </summary>
    [Fact]
    public void ConstructorWorksWithNullChatOptions()
    {
        // Act
        var runOptions = new ChatClientAgentRunOptions();

        // Assert
        Assert.Null(runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions ChatOptions property is set and mutable.
    /// </summary>
    [Fact]
    public void ChatOptionsPropertyIsReadOnly()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        var runOptions = new ChatClientAgentRunOptions(chatOptions);
        chatOptions.MaxOutputTokens = 200; // Change the property to verify mutability

        // Act & Assert
        Assert.Same(chatOptions, runOptions.ChatOptions);

        // Verify that the property doesn't have a setter by checking if it's the same instance
        var retrievedOptions = runOptions.ChatOptions!;
        Assert.Same(chatOptions, retrievedOptions);
        Assert.Equal(200, retrievedOptions.MaxOutputTokens); // Ensure the change is reflected
    }

    #region ChatClientFactory Tests

    /// <summary>
    /// Tests that ChatClientFactory is called and transforms the client for RunAsync.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithChatClientFactory_UsesTransformedClientAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();
        var transformedClient = new Mock<IChatClient>();
        var factoryCallCount = 0;

        // Setup the original client to throw if called (should not be used)
        originalClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("Original client should not be called"));

        // Setup the transformed client to return a response
        transformedClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Transformed response")]));

        // Create the factory that transforms the client
        IChatClient ClientFactory(IChatClient client)
        {
            factoryCallCount++;
            Assert.Same(originalClient.Object, client); // Verify original client is passed
            return transformedClient.Object;
        }

        var agent = new ChatClientAgent(originalClient.Object, new ChatClientAgentOptions() { UseProvidedChatClientAsIs = true });
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var options = new ChatClientAgentRunOptions { ChatClientFactory = ClientFactory };

        // Act
        var response = await agent.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.NotNull(response);
        Assert.Equal(1, factoryCallCount); // Factory should be called exactly once
        transformedClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
        originalClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Tests that ChatClientFactory is called and transforms the client for RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithChatClientFactory_UsesTransformedClientAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();
        var transformedClient = new Mock<IChatClient>();
        var factoryCallCount = 0;

        // Setup the original client to throw if called (should not be used)
        originalClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("Original client should not be called"));

        // Setup the transformed client to return streaming responses
        var streamingResponses = new[]
        {
            new ChatResponseUpdate { Contents = [new TextContent("Streaming ")] },
            new ChatResponseUpdate { Contents = [new TextContent("response")] }
        };
        transformedClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(streamingResponses.ToAsyncEnumerable());

        // Create the factory that transforms the client
        IChatClient ClientFactory(IChatClient client)
        {
            factoryCallCount++;
            Assert.Same(originalClient.Object, client); // Verify original client is passed
            return transformedClient.Object;
        }

        var agent = new ChatClientAgent(originalClient.Object, new ChatClientAgentOptions() { UseProvidedChatClientAsIs = true });
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var options = new ChatClientAgentRunOptions { ChatClientFactory = ClientFactory };

        // Act
        var responseUpdates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(messages, null, options, CancellationToken.None))
        {
            responseUpdates.Add(update);
        }

        // Assert
        Assert.NotEmpty(responseUpdates);
        Assert.Equal(1, factoryCallCount); // Factory should be called exactly once
        transformedClient.Verify(c => c.GetStreamingResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
        originalClient.Verify(c => c.GetStreamingResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Tests that without ChatClientFactory, the original client is used for RunAsync.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithoutChatClientFactory_UsesOriginalClientAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();

        originalClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Original response")]));

        var agent = new ChatClientAgent(originalClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act - No ChatClientFactory provided
        var response = await agent.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.NotNull(response);
        originalClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Tests that without ChatClientFactory, the original client is used for RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithoutChatClientFactory_UsesOriginalClientAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();

        var streamingResponses = new[]
        {
            new ChatResponseUpdate { Contents = [new TextContent("Original ")] },
            new ChatResponseUpdate { Contents = [new TextContent("streaming")] }
        };
        originalClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(streamingResponses.ToAsyncEnumerable());

        var agent = new ChatClientAgent(originalClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act - No ChatClientFactory provided
        var responseUpdates = new List<AgentResponseUpdate>();
        await foreach (var update in agent.RunStreamingAsync(messages, null, null, CancellationToken.None))
        {
            responseUpdates.Add(update);
        }

        // Assert
        Assert.NotEmpty(responseUpdates);
        originalClient.Verify(c => c.GetStreamingResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Tests that ChatClientFactory is called for each separate RunAsync call.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleCalls_ChatClientFactoryCalledEachTimeAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();
        var transformedClient = new Mock<IChatClient>();
        var factoryCallCount = 0;

        transformedClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response")]));

        IChatClient ClientFactory(IChatClient client)
        {
            factoryCallCount++;
            return transformedClient.Object;
        }

        var agent = new ChatClientAgent(originalClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var options = new ChatClientAgentRunOptions { ChatClientFactory = ClientFactory };

        // Act - Call RunAsync multiple times
        await agent.RunAsync(messages, null, options, CancellationToken.None);
        await agent.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.Equal(2, factoryCallCount); // Factory should be called for each run
        transformedClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Exactly(2));
    }

    /// <summary>
    /// Tests that subsequent calls without ChatClientFactory use the original client.
    /// </summary>
    [Fact]
    public async Task RunAsync_AfterFactoryCall_WithoutFactory_UsesOriginalClientAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();
        var transformedClient = new Mock<IChatClient>();

        originalClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Original response")]));

        transformedClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Transformed response")]));

        IChatClient ClientFactory(IChatClient client) => transformedClient.Object;

        var agent = new ChatClientAgent(originalClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var optionsWithFactory = new ChatClientAgentRunOptions { ChatClientFactory = ClientFactory };

        // Act - First call with factory, second call without
        await agent.RunAsync(messages, null, optionsWithFactory, CancellationToken.None);
        await agent.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        transformedClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
        originalClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Tests that ChatClientFactory returning null throws an exception.
    /// </summary>
    [Fact]
    public async Task RunAsync_ChatClientFactoryReturnsNull_ThrowsExceptionAsync()
    {
        // Arrange
        var originalClient = new Mock<IChatClient>();

        static IChatClient ClientFactory(IChatClient client) => null!;

        var agent = new ChatClientAgent(originalClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var options = new ChatClientAgentRunOptions { ChatClientFactory = ClientFactory };

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(async () =>
            await agent.RunAsync(messages, null, options, CancellationToken.None));
    }

    #endregion
}
