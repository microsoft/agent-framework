// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for the ChatClientExtensions class.
/// </summary>
public sealed class ChatClientExtensionsTests
{
    [Fact]
    public void CreateAIAgent_WithBasicParameters_CreatesAgent()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();

        // Act
        var agent = chatClientMock.Object.CreateAIAgent(
            instructions: "Test instructions",
            name: "TestAgent",
            description: "Test description"
        );

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("Test description", agent.Description);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    [Fact]
    public void CreateAIAgent_WithTools_SetsToolsInOptions()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        var tools = new List<AITool> { new Mock<AITool>().Object };

        // Act
        var agent = chatClientMock.Object.CreateAIAgent(tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.ChatOptions);
        Assert.Equal(tools, agent.ChatOptions.Tools);
    }

    [Fact]
    public void CreateAIAgent_WithOptions_CreatesAgentWithOptions()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        var options = new ChatClientAgentOptions
        {
            Name = "AgentWithOptions",
            Description = "Desc",
            ChatOptions = new() { Instructions = "Instr" },
            UseProvidedChatClientAsIs = true
        };

        // Act
        var agent = chatClientMock.Object.CreateAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("AgentWithOptions", agent.Name);
        Assert.Equal("Desc", agent.Description);
        Assert.Equal("Instr", agent.Instructions);
        Assert.Same(chatClientMock.Object, agent.ChatClient);
    }

    [Fact]
    public void CreateAIAgent_WithNullClient_Throws()
    {
        // Arrange
        IChatClient chatClient = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => chatClient.CreateAIAgent(instructions: "instructions"));
    }

    [Fact]
    public void CreateAIAgent_WithNullClientAndOptions_Throws()
    {
        // Arrange
        IChatClient chatClient = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => chatClient.CreateAIAgent(options: new() { ChatOptions = new() { Instructions = "instructions" } }));
    }
}
