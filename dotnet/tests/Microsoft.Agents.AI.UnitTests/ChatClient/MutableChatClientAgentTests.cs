// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public sealed class MutableChatClientAgentTests
{
    #region Constructor Tests

    /// <summary>
    /// Verify the invocation and response of <see cref="MutableChatClientAgent"/>.
    /// </summary>
    [Fact]
    public void VerifyMutableChatClientAgentDefinition()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        MutableChatClientAgent agent =
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
    }

    /// <summary>
    /// Verify that MutableChatClientAgent creates empty options when none are provided.
    /// </summary>
    [Fact]
    public void VerifyMutableChatClientAgentCreatesEmptyOptionsWhenNoneProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        MutableChatClientAgent agent = new(chatClient, options: null);

        // Assert
        Assert.Null(agent.Instructions);
        Assert.Null(agent.ChatOptions);
    }

    #endregion

    #region Mutability Tests

    /// <summary>
    /// Verify that Instructions can be modified after construction.
    /// </summary>
    [Fact]
    public void VerifyInstructionsCanBeModified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        MutableChatClientAgent agent = new(chatClient, instructions: "initial instructions");

        // Act
        string? initialInstructions = agent.Instructions;
        agent.Instructions = "modified instructions";
        string? modifiedInstructions = agent.Instructions;

        // Assert
        Assert.Equal("initial instructions", initialInstructions);
        Assert.Equal("modified instructions", modifiedInstructions);
    }

    /// <summary>
    /// Verify that Instructions can be set to null.
    /// </summary>
    [Fact]
    public void VerifyInstructionsCanBeSetToNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        MutableChatClientAgent agent = new(chatClient, instructions: "initial instructions");

        // Act
        agent.Instructions = null;

        // Assert
        Assert.Null(agent.Instructions);
    }

    /// <summary>
    /// Verify that ChatOptions can be modified after construction.
    /// </summary>
    [Fact]
    public void VerifyChatOptionsCanBeModified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatOptions initialOptions = new() { Temperature = 0.5f };
        MutableChatClientAgent agent = new(chatClient, options: new() { ChatOptions = initialOptions });

        // Act
        ChatOptions? retrievedInitialOptions = agent.ChatOptions;
        agent.ChatOptions = new() { Temperature = 0.9f };
        ChatOptions? retrievedModifiedOptions = agent.ChatOptions;

        // Assert
        Assert.NotNull(retrievedInitialOptions);
        Assert.Equal(0.5f, retrievedInitialOptions.Temperature);
        Assert.NotNull(retrievedModifiedOptions);
        Assert.Equal(0.9f, retrievedModifiedOptions.Temperature);
    }

    /// <summary>
    /// Verify that ChatOptions can be set to null.
    /// </summary>
    [Fact]
    public void VerifyChatOptionsCanBeSetToNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        ChatOptions initialOptions = new() { Temperature = 0.5f };
        MutableChatClientAgent agent = new(chatClient, options: new() { ChatOptions = initialOptions });

        // Act
        agent.ChatOptions = null;

        // Assert
        Assert.Null(agent.ChatOptions);
    }

    /// <summary>
    /// Verify that modified instructions are used in agent invocations.
    /// </summary>
    [Fact]
    public async Task VerifyModifiedInstructionsAreUsedInInvocations()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "Response")]));

        MutableChatClientAgent agent = new(mockService.Object, instructions: "initial instructions");

        // Act
        agent.Instructions = "modified instructions";
        var result = await agent.RunAsync([new(ChatRole.User, "Test message")]);

        // Assert
        Assert.Single(result.Messages);
        mockService.Verify(
            x => x.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    #endregion

    #region Base Class Behavior Tests

    /// <summary>
    /// Verify that MutableChatClientAgent properly invokes the chat client.
    /// </summary>
    [Fact]
    public async Task VerifyMutableChatClientAgentInvocationAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>())).ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "I'm here!")]));

        MutableChatClientAgent agent =
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

    #endregion
}
